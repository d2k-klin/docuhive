"""Rent and service charges for private landlords in Germany.

The arithmetic is in statement.py; this file stores what the landlord enters, proposes bills from
the archive as costs (nothing counts until confirmed), keeps the rent ledger, and issues each
statement as a locked document together with the bills it rests on. It divides; it does not
decide what may be passed on.
"""

import csv
import io
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from docuhive.sdk import (
    ActionError,
    Registry,
    Result,
    User,
    ai,
    documents,
    mail,
    profiles,
    reminders,
    render,
    retention,
    services,
)
from pydantic import BaseModel
from sqlalchemy import text

from . import statement as st


class CostType(BaseModel):
    cost_type: str


def norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def setup(registry: Registry) -> None:  # noqa: C901 - one plugin, many small parts
    def q(sql: str, **params) -> list[dict]:  # type: ignore[no-untyped-def]
        with registry.db.session() as s:
            return [dict(r) for r in s.execute(text(sql), params).mappings()]

    def one(sql: str, **params) -> Any:  # type: ignore[no-untyped-def]
        with registry.db.session() as s:
            return s.execute(text(sql), params).scalar()

    def run(sql: str, **params) -> None:  # type: ignore[no-untyped-def]
        with registry.db.session() as s:
            s.execute(text(sql), params)

    types = lambda: {t["id"]: t for t in registry.rules("cost-types.yaml")["types"]}  # noqa: E731

    def mine(user: User) -> list[dict]:
        return q("SELECT * FROM properties WHERE owner_id = :u ORDER BY name", u=user.id)

    def prop(user: User, property_id: object) -> dict:
        found = [p for p in mine(user) if str(p["id"]) == str(property_id)]
        if not found:
            raise ActionError("This property is not yours.")
        return found[0]

    def tenancy(user: User, tenancy_id: object) -> dict:
        rows = q(
            "SELECT t.*, u.property_id, u.name AS unit FROM tenancies t JOIN units u ON "
            "u.id = t.unit_id WHERE t.id = :i",
            i=int(tenancy_id or 0),
        )
        if not rows:
            raise ActionError("This tenancy does not exist.")
        prop(user, rows[0]["property_id"])
        return rows[0]

    def year_of(p: dict, year: int) -> tuple[date, date]:
        start = date(year, p["year_start_month"], 1)
        nxt = date(year + 1, p["year_start_month"], 1)
        return start, nxt - timedelta(days=1)

    def keys_of(property_id: int) -> dict[str, dict]:
        out = {k: {"key": t["key"], "passable": t["passable"]} for k, t in types().items()}
        for row in q("SELECT * FROM allocation WHERE property_id = :p", p=property_id):
            out[row["cost_type"]] = {"key": row["key"], "passable": row["passable"]}
        return out

    # Setting up --------------------------------------------------------------------------------

    @registry.action("save_property")
    def save_property(user: User, params: dict) -> Result:
        name = str(params.get("name") or "").strip()
        values = {k: params.get(k) or "" for k in ("street", "postcode", "city")}
        values["profile"] = int(params["profile_id"]) if params.get("profile_id") else None
        if params.get("property"):
            p = prop(user, params["property"])
            run(
                "UPDATE properties SET name = coalesce(nullif(:n, ''), name), street = :street, "
                "postcode = :postcode, city = :city, profile_id = :profile WHERE id = :i",
                n=name,
                i=p["id"],
                **values,
            )
            return Result(message="Saved.")
        if not name:
            return Result(errors={"name": "Name the property, for example its street"})
        run(
            "INSERT INTO properties (owner_id, name, street, postcode, city, profile_id) VALUES "
            "(:u, :n, :street, :postcode, :city, :profile)",
            u=user.id,
            n=name,
            **values,
        )
        return Result(message=f"“{name}” added. Now add its flats.")

    @registry.action("save_unit")
    def save_unit(user: User, params: dict) -> Result:
        p = prop(user, params.get("property"))
        try:
            area = Decimal(str(params.get("area")))
        except ArithmeticError:
            return Result(errors={"area": "The living space in m²"})
        if not params.get("name") or area <= 0:
            return Result(errors={"name": "Name the flat and give its living space"})
        run(
            "INSERT INTO units (property_id, name, area) VALUES (:p, :n, :a)",
            p=p["id"],
            n=params["name"],
            a=area,
        )
        return Result(message="Flat added.")

    @registry.action("save_tenancy")
    def save_tenancy(user: User, params: dict) -> Result:
        unit = q("SELECT * FROM units WHERE id = :i", i=int(params.get("unit") or 0))
        if not unit:
            return Result(errors={"unit": "Choose the flat"})
        prop(user, unit[0]["property_id"])
        if not params.get("tenant_name") or not params.get("start_date"):
            return Result(errors={"tenant_name": "The tenant's name and the start are needed"})
        start = date.fromisoformat(params["start_date"])
        end = date.fromisoformat(params["end_date"]) if params.get("end_date") else None
        with registry.db.session() as s:
            tid = s.execute(
                text(
                    "INSERT INTO tenancies (unit_id, tenant_name, tenant_email, start_date, "
                    "end_date, rent, "
                    "advance, deposit) VALUES (:u, :n, :e, :s, :end, :r, :a, :d) RETURNING id"
                ),
                {
                    "u": unit[0]["id"],
                    "n": params["tenant_name"],
                    "e": params.get("tenant_email") or None,
                    "s": start,
                    "end": end,
                    "r": Decimal(str(params.get("rent") or 0)),
                    "a": Decimal(str(params.get("advance") or 0)),
                    "d": Decimal(str(params["deposit"])) if params.get("deposit") else None,
                },
            ).scalar_one()
            s.execute(
                text("INSERT INTO persons (tenancy_id, since, persons) VALUES (:t, :s, :p)"),
                {"t": tid, "s": start, "p": int(params.get("persons") or 1)},
            )
        return Result(message="Tenancy added.")

    @registry.action("change_tenancy")
    def change_tenancy(user: User, params: dict) -> str:
        """Moving out, or a change in the number of persons from a date."""
        t = tenancy(user, params.get("tenancy"))
        if params.get("end_date"):
            run(
                "UPDATE tenancies SET end_date = :e WHERE id = :i",
                e=date.fromisoformat(params["end_date"]),
                i=t["id"],
            )
        if params.get("persons") and params.get("since"):
            run(
                "INSERT INTO persons (tenancy_id, since, persons) VALUES (:t, :s, :p) ON CONFLICT "
                "(tenancy_id, since) DO UPDATE SET persons = :p",
                t=t["id"],
                s=date.fromisoformat(params["since"]),
                p=int(params["persons"]),
            )
        return "Saved."

    @registry.action("save_key")
    def save_key(user: User, params: dict) -> str:
        p = prop(user, params.get("property"))
        if params.get("cost_type") not in types():
            raise ActionError("Choose a cost type.")
        run(
            "INSERT INTO allocation (property_id, cost_type, key, passable) VALUES (:p, :c, :k, "
            ":x) "
            "ON CONFLICT (property_id, cost_type) DO UPDATE SET key = :k, passable = :x",
            p=p["id"],
            c=params["cost_type"],
            k=params.get("key") or "area",
            x=bool(params.get("passable")),
        )
        return "Saved. The statements use this key from now on."

    # Bills in ------------------------------------------------------------------------------------

    def guess_type(doc) -> str | None:  # type: ignore[no-untyped-def]
        known = types()
        words = f"{doc.title or ''} {doc.correspondent or ''}".lower()
        for t in known.values():
            if any(w in words for w in t["words"]):
                return t["id"]
        before = one(
            "SELECT c.cost_type FROM cost_items c WHERE c.state = 'confirmed' AND "
            "c.document_id IN (SELECT id FROM public.documents WHERE correspondent_id = "
            "(SELECT correspondent_id FROM public.documents WHERE id = :d)) LIMIT 1",
            d=doc.id,
        )
        if before:
            return before

        def listed(answer: CostType) -> CostType:
            if answer.cost_type not in known:
                raise ValueError("Choose an id from the list")
            return answer

        try:
            return ai.ask(
                "cost-type",
                CostType,
                document=doc,
                validate=listed,
                variables={
                    "types": "\n".join(f"{k}: {t['label']}" for k, t in known.items()),
                    "sender": doc.correspondent or "",
                },
            ).cost_type
        except ai.Unavailable:
            return None

    @registry.on("document.classified")
    def classified(event) -> None:  # type: ignore[no-untyped-def]
        doc = documents.get(event.document_id)
        if event.document_type != "invoice" or not (doc.category or "").startswith("housing"):
            return
        props = q("SELECT * FROM properties WHERE owner_id = :o", o=doc.owner_id)
        if not props or one("SELECT 1 FROM cost_items WHERE document_id = :d", d=doc.id):
            return
        words = norm(f"{doc.title} {documents.content(doc.id, 3000)}")
        target = next(
            (p for p in props if norm(p["street"]) and norm(p["street"]) in words), props[0]
        )
        total = doc.facts.get("amount_total")
        if total is None:
            return
        start = doc.facts.get("period_start")
        end = doc.facts.get("period_end")
        day = doc.document_date or doc.added_at.date()
        run(
            "INSERT INTO cost_items (property_id, cost_type, document_id, amount, period_from, "
            "period_to) VALUES (:p, :c, :d, :a, :f, :t)",
            p=target["id"],
            c=guess_type(doc),
            d=doc.id,
            a=Decimal(total.value),
            f=date.fromisoformat(start.value) if start else day,
            t=date.fromisoformat(end.value) if end else day,
        )

    @registry.action("confirm_cost")
    def confirm_cost(user: User, params: dict) -> Result:
        item = q(
            "SELECT * FROM cost_items WHERE id = :i",
            i=int(params.get("id") or params.get("item") or 0),
        )
        if not item:
            raise ActionError("This bill is not in your costs.")
        prop(user, item[0]["property_id"])
        cost_type = params.get("cost_type") or item[0]["cost_type"]
        if cost_type not in types():
            return Result(errors={"cost_type": "Choose the cost type"})
        run(
            "UPDATE cost_items SET cost_type = :c, state = 'confirmed', unit_id = :u, "
            "period_from = coalesce(:f, period_from), period_to = coalesce(:t, period_to) WHERE id "
            "= :i",
            c=cost_type,
            u=int(params["unit_id"]) if params.get("unit_id") else None,
            f=date.fromisoformat(params["period_from"]) if params.get("period_from") else None,
            t=date.fromisoformat(params["period_to"]) if params.get("period_to") else None,
            i=item[0]["id"],
        )
        return Result(message="Confirmed.")

    @registry.action("record_consumption")
    def record_consumption(user: User, params: dict) -> str:
        t = tenancy(user, params.get("tenancy"))
        run(
            "INSERT INTO consumption (property_id, year, cost_type, tenancy_id, value) VALUES "
            "(:p, :y, :c, :t, :v) ON CONFLICT (property_id, year, cost_type, tenancy_id) DO UPDATE "
            "SET value = :v",
            p=t["property_id"],
            y=int(params["year"]),
            c=params.get("cost_type") or "heating",
            t=t["id"],
            v=Decimal(str(params["value"])),
        )
        return "Saved."

    # Rent ledger ---------------------------------------------------------------------------------

    @registry.every(timedelta(days=1), "ledger")
    def ledger(payload, ctx) -> None:  # type: ignore[no-untyped-def]
        """Each running tenancy owes rent and advances for the current month."""
        month = date.today().replace(day=1)
        run(
            "INSERT INTO rent_ledger (tenancy_id, month, due) SELECT id, :m, rent + advance FROM "
            "tenancies WHERE start_date <= :end AND (end_date IS NULL OR end_date >= :m) "
            "ON CONFLICT DO NOTHING",
            m=month,
            end=(month + timedelta(days=32)).replace(day=1) - timedelta(days=1),
        )

    @registry.action("received")
    def received(user: User, params: dict) -> str:
        t = tenancy(user, params.get("tenancy_id"))
        month = date.fromisoformat(str(params["month"])[:10]).replace(day=1)
        run(
            "UPDATE rent_ledger SET received = due, received_on = :d WHERE tenancy_id = :t AND "
            "month = :m",
            d=date.today(),
            t=t["id"],
            m=month,
        )
        return "Marked as paid."

    @registry.action("fill_from_bank")
    def fill_from_bank(user: User, params: dict) -> str:
        """With the bank plugin: payments from the tenant of the due amount mark the month paid."""
        if not services.available("bank.transactions"):
            raise ActionError("The bank plugin is not on.")
        found = 0
        for row in q(
            "SELECT l.*, t.tenant_name FROM rent_ledger l JOIN tenancies t ON t.id = "
            "l.tenancy_id JOIN units u ON u.id = t.unit_id JOIN properties p ON p.id = "
            "u.property_id WHERE p.owner_id = :o AND l.received < l.due",
            o=user.id,
        ):
            for tx in services.get("bank.transactions")(user, counterparty=row["tenant_name"]):
                month = tx["booking_date"].replace(day=1)
                if Decimal(str(tx["amount"])) == row["due"] and month == row["month"]:
                    run(
                        "UPDATE rent_ledger SET received = due, received_on = :d, transaction_id = "
                        ":x "
                        "WHERE tenancy_id = :t AND month = :m",
                        d=tx["booking_date"],
                        x=tx["id"],
                        t=row["tenancy_id"],
                        m=row["month"],
                    )
                    found += 1
                    break
        return f"{found} months found on your statements."

    # Statements ----------------------------------------------------------------------------------

    def inputs(t: dict, year: int) -> tuple:
        p = q("SELECT * FROM properties WHERE id = :p", p=t["property_id"])[0]
        span = year_of(p, year)
        units = [
            st.Unit(
                u["id"], u["name"], u["area"], {k: Decimal(str(v)) for k, v in u["shares"].items()}
            )
            for u in q("SELECT * FROM units WHERE property_id = :p", p=p["id"])
        ]
        tenancies = []
        for row in q(
            "SELECT t.* FROM tenancies t JOIN units u ON u.id = t.unit_id WHERE u.property_id = :p",
            p=p["id"],
        ):
            persons = [
                (r["since"], r["persons"])
                for r in q(
                    "SELECT * FROM persons WHERE tenancy_id = :t ORDER BY since", t=row["id"]
                )
            ]
            tenancies.append(
                st.Tenancy(
                    row["id"],
                    row["unit_id"],
                    row["start_date"],
                    row["end_date"],
                    persons,
                    row["advance"],
                )
            )
        costs = [
            st.Cost(
                c["cost_type"],
                st.split(c["amount"], (c["period_from"], c["period_to"]), span),
                c["unit_id"],
                c["document_id"],
            )
            for c in q(
                "SELECT * FROM cost_items WHERE property_id = :p AND state = 'confirmed' "
                "AND period_to >= :s AND period_from <= :e",
                p=p["id"],
                s=span[0],
                e=span[1],
            )
        ]
        consumption = {
            (r["cost_type"], r["tenancy_id"]): r["value"]
            for r in q(
                "SELECT * FROM consumption WHERE property_id = :p AND year = :y", p=p["id"], y=year
            )
        }
        target = next(x for x in tenancies if x.id == t["id"])
        return p, span, target, units, tenancies, costs, consumption

    def draft(user: User, params: dict) -> tuple[dict, dict, dict]:
        t = tenancy(user, params.get("tenancy"))
        year = int(params.get("year") or date.today().year - 1)
        p, span, target, units, tenancies, costs, consumption = inputs(t, year)
        result = st.compute(target, span, units, tenancies, costs, keys_of(p["id"]), consumption)
        return t, p, result | {"year": year, "span": span}

    @registry.data("statement")
    def statement_lines(user: User, params: dict) -> list[dict]:
        if not params.get("tenancy"):
            return []  # nothing chosen yet: the page shows its empty state
        _, _, result = draft(user, params)
        labels = {k: v["label"] for k, v in types().items()}
        out = [
            {
                "cost": labels.get(line["cost_type"], line["cost_type"]),
                "basis": line["basis"],
                "total": {"value": line["total"], "currency": "EUR"},
                "share": {"value": line["amount"], "currency": "EUR"},
            }
            for line in result["lines"]
        ]
        out.append(
            {
                "cost": "Advance payments",
                "basis": "as agreed",
                "share": {"value": -result["advances"], "currency": "EUR"},
            }
        )
        out.append(
            {
                "cost": "Balance (negative: the tenant gets money back)",
                "basis": "",
                "share": {"value": result["balance"], "currency": "EUR"},
            }
        )
        return out

    @registry.data("missing")
    def missing(user: User, params: dict) -> list[dict]:
        if not params.get("tenancy"):
            return []  # nothing chosen yet: the page shows its empty state
        t, p, result = draft(user, params)
        year = result["year"]
        items = []
        open_bills = one(
            "SELECT count(*) FROM cost_items WHERE property_id = :p AND state = 'proposed'",
            p=p["id"],
        )
        if open_bills:
            items.append(
                {
                    "label": f"{open_bills} bills to confirm",
                    "state": "problem",
                    "link": "/plugins/vermieter-de/costs",
                }
            )
        this = {
            r["cost_type"]
            for r in q(
                "SELECT DISTINCT cost_type FROM cost_items WHERE property_id "
                "= :p AND state = 'confirmed' AND extract(year FROM period_to) = :y",
                p=p["id"],
                y=year,
            )
        }
        last = {
            r["cost_type"]
            for r in q(
                "SELECT DISTINCT cost_type FROM cost_items WHERE property_id "
                "= :p AND state = 'confirmed' AND extract(year FROM period_to) = :y",
                p=p["id"],
                y=year - 1,
            )
        }
        labels = {k: v["label"] for k, v in types().items()}
        for cost_type in sorted(last - this):
            items.append(
                {
                    "label": f"No bill for {labels.get(cost_type, cost_type)} in {year} (there was "
                    f"one "
                    f"in {year - 1})",
                    "state": "todo",
                }
            )
        keys = keys_of(p["id"])
        for cost_type in this:
            if keys.get(cost_type, {}).get("key") in ("metered", "consumption") and not one(
                "SELECT 1 FROM consumption WHERE tenancy_id = :t AND cost_type = :c AND year = :y",
                t=t["id"],
                c=cost_type,
                y=year,
            ):
                items.append(
                    {
                        "label": f"The value for {labels.get(cost_type, cost_type)} is missing for "
                        "this tenancy",
                        "state": "problem",
                    }
                )
        return items

    @registry.action("show_statement")
    def show_statement(user: User, params: dict) -> Result:
        t = tenancy(user, params.get("tenancy"))
        return Result(goto=f"statements?tenancy={t['id']}&year={int(params.get('year') or 0)}")

    @registry.action("issue_statement")
    def issue_statement(user: User, params: dict) -> Result:
        t, p, result = draft(user, params)
        if [i for i in missing(user, params) if i["state"] == "problem"]:
            raise ActionError("Finish the items under “Before you issue” first.")
        if not p["profile_id"]:
            raise ActionError("Choose your identity for the property first.")
        me = profiles.get(user, p["profile_id"])
        labels = {k: v["label"] for k, v in types().items()}
        previous = one(
            "SELECT id FROM statements WHERE tenancy_id = :t AND year = :y ORDER BY id DESC "
            "LIMIT 1",
            t=t["id"],
            y=result["year"],
        )
        a = me["address"] or {}
        pdf = render.pdf(
            "statement.html",
            {
                "landlord": me,
                "tenancy": t,
                "property": p,
                "result": result,
                "labels": labels,
                "sender_line": f"{me['name']} · {a.get('street', '')} · {a.get('postcode', '')} "
                f"{a.get('city', '')}",
                "recipient": [
                    t["tenant_name"],
                    *(
                        t["tenant_address"] or f"{p['street']}\n{p['postcode']} {p['city']}"
                    ).splitlines(),
                ],
                "place": a.get("city") or "",
                "date": date.today().strftime("%d.%m.%Y"),
                "subject": f"Betriebskostenabrechnung {result['year']} – {p['name']}, {t['unit']}",
                "replaces": bool(previous),
                "iban": (me["bank"] or {}).get("iban"),
            },
        )
        bills = sorted({d for line in result["lines"] for d in line["documents"]})
        doc_id = documents.create(
            user,
            pdf,
            filename=f"statement-{result['year']}-{norm(t['tenant_name'])}.pdf",
            title=f"Service charges {result['year']}: {t['tenant_name']}",
            category="housing/property",
            derived_from=bills,
            document_date=date.today(),
            correspondent=t["tenant_name"],
        )
        reason = f"Service charges {result['year']}, {t['tenant_name']}"
        until = retention.until("booking_document", date.today().year)
        for d in [doc_id, *bills]:
            if not any(h["reason"] == reason for h in documents.holds(d)):
                documents.hold(d, reason, until=until)
        from ._json import dumps

        run(
            "INSERT INTO statements (tenancy_id, year, lines, total_costs, advances, balance, "
            "document_id, "
            "replaces_id) VALUES (:t, :y, CAST(:l AS jsonb), :c, :a, :b, :d, :r)",
            t=t["id"],
            y=result["year"],
            l=dumps(result["lines"]),
            c=result["costs"],
            a=result["advances"],
            b=result["balance"],
            d=doc_id,
            r=previous,
        )
        return Result(
            message="Issued. The statement and its bills are locked.", goto=f"/documents/{doc_id}"
        )

    @registry.action("send_statement", outgoing=True)
    def send_statement(user: User, params: dict) -> str:
        t = tenancy(user, params.get("tenancy"))
        row = q(
            "SELECT * FROM statements WHERE tenancy_id = :t ORDER BY id DESC LIMIT 1", t=t["id"]
        )
        to = params.get("to") or t["tenant_email"]
        if not row or not to:
            raise ActionError("Issue the statement first, and enter the tenant's mail address.")
        p = q("SELECT * FROM properties WHERE id = :p", p=t["property_id"])[0]
        mail.send(
            user,
            p["profile_id"],
            [to],
            f"Betriebskostenabrechnung {row[0]['year']}",
            "Guten Tag,\n\nanbei die Betriebskostenabrechnung. Die Belege können Sie nach "
            "Absprache einsehen.\n\nMit freundlichen Grüßen",
            [row[0]["document_id"]],
        )
        run(
            "UPDATE statements SET state = 'sent', sent_on = :d WHERE id = :i",
            d=date.today(),
            i=row[0]["id"],
        )
        return f"Sent to {to}."

    @registry.every(timedelta(days=1), "deadlines")
    def deadlines(payload, ctx) -> None:  # type: ignore[no-untyped-def]
        rules = registry.rules("deadlines.yaml")
        for p in q("SELECT * FROM properties"):
            year = date.today().year - 1
            end = year_of(p, year)[1]
            due = date(
                end.year + (end.month + rules["statement_due_months"] - 1) // 12,
                (end.month + rules["statement_due_months"] - 1) % 12 + 1,
                1,
            )
            due = (due + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            done = one(
                "SELECT count(*) FROM statements s JOIN tenancies t ON t.id = s.tenancy_id JOIN "
                "units u ON u.id = t.unit_id WHERE u.property_id = :p AND s.year = :y",
                p=p["id"],
                y=year,
            )
            key = f"statements:{p['id']}:{year}"
            if done:
                reminders.clear(p["owner_id"], key)
            else:
                reminders.set(
                    p["owner_id"],
                    key,
                    f"Service-charge statements {year}: {p['name']}",
                    due,
                    days_before=rules["remind_days_before"],
                    link="/plugins/vermieter-de/statements",
                )

    # Screens -------------------------------------------------------------------------------------

    data = registry.data
    data("properties")(lambda user, params: mine(user))
    data("property_options")(
        lambda user, params: [{"value": str(p["id"]), "label": p["name"]} for p in mine(user)]
    )
    data("profile_options")(
        lambda user, params: [
            {"value": str(p["id"]), "label": p["name"]} for p in profiles.list(user)
        ]
    )
    data("type_options")(
        lambda user, params: [{"value": k, "label": v["label"]} for k, v in types().items()]
    )
    data("key_options")(
        lambda user, params: [
            {"value": k, "label": v}
            for k, v in {
                "area": "Living space",
                "persons": "Persons",
                "units": "Per flat",
                "metered": "Metering statement amount",
                "consumption": "Meter readings",
                "direct": "One flat only",
            }.items()
        ]
    )

    @data("units")
    def units(user: User, params: dict) -> list[dict]:
        ids = [p["id"] for p in mine(user)]
        return (
            q(
                "SELECT u.*, p.name AS property FROM units u JOIN properties p ON p.id = "
                "u.property_id "
                "WHERE u.property_id = ANY(:i) ORDER BY p.name, u.name",
                i=ids,
            )
            if ids
            else []
        )

    data("unit_options")(
        lambda user, params: [
            {"value": str(u["id"]), "label": f"{u['property']}: {u['name']}"}
            for u in units(user, params)
        ]
    )

    @data("tenancies")
    def tenancies(user: User, params: dict) -> list[dict]:
        ids = [u["id"] for u in units(user, params)]
        rows = (
            q(
                "SELECT t.*, u.name AS unit, p.name AS property FROM tenancies t JOIN units u ON "
                "u.id = t.unit_id JOIN properties p ON p.id = u.property_id WHERE t.unit_id = "
                "ANY(:i) "
                "ORDER BY p.name, u.name, t.start_date DESC",
                i=ids,
            )
            if ids
            else []
        )
        today = date.today()
        for r in rows:
            r["state"] = "Ended" if r["end_date"] and r["end_date"] < today else "Running"
            r["monthly"] = {"value": r["rent"] + r["advance"], "currency": "EUR"}
        return rows

    data("tenancy_options")(
        lambda user, params: [
            {"value": str(t["id"]), "label": f"{t['property']}, {t['unit']}: {t['tenant_name']}"}
            for t in tenancies(user, params)
        ]
    )

    @data("costs")
    def costs(user: User, params: dict) -> list[dict]:
        ids = [p["id"] for p in mine(user)]
        labels = {k: v["label"] for k, v in types().items()}
        rows = (
            q(
                "SELECT c.*, p.name AS property FROM cost_items c JOIN properties p ON p.id = "
                "c.property_id WHERE c.property_id = ANY(:i) ORDER BY c.state DESC, c.period_to "
                "DESC",
                i=ids,
            )
            if ids
            else []
        )
        for r in rows:
            r["type_label"] = labels.get(r["cost_type"], "Choose")
            r["money"] = {"value": r["amount"], "currency": "EUR"}
            r["state_label"] = "To confirm" if r["state"] == "proposed" else "Confirmed"
            r["to_confirm"] = r["id"] if r["state"] == "proposed" and r["cost_type"] else None
        return rows

    data("cost_options")(
        lambda user, params: [
            {
                "value": str(c["id"]),
                "label": f"{c['period_to']:%d.%m.%Y} {c['amount']} € ({c['type_label']})",
            }
            for c in costs(user, params)
            if c["state"] == "proposed"
        ]
    )

    @data("ledger")
    def ledger_rows(user: User, params: dict) -> list[dict]:
        ids = [t["id"] for t in tenancies(user, params)]
        rows = (
            q(
                "SELECT l.*, t.tenant_name FROM rent_ledger l JOIN tenancies t ON t.id = "
                "l.tenancy_id "
                "WHERE l.tenancy_id = ANY(:i) ORDER BY l.month DESC, t.tenant_name",
                i=ids,
            )
            if ids
            else []
        )
        for r in rows:
            r["open"] = (
                {"value": r["due"] - r["received"], "currency": "EUR"}
                if r["received"] < r["due"]
                else None
            )
            r["state"] = "Paid" if r["received"] >= r["due"] else "Open"
            r["due_money"] = {"value": r["due"], "currency": "EUR"}
        return rows

    @data("statements")
    def statements(user: User, params: dict) -> list[dict]:
        ids = [t["id"] for t in tenancies(user, params)]
        rows = (
            q(
                "SELECT s.*, t.tenant_name FROM statements s JOIN tenancies t ON t.id = "
                "s.tenancy_id "
                "WHERE s.tenancy_id = ANY(:i) ORDER BY s.year DESC, s.id DESC",
                i=ids,
            )
            if ids
            else []
        )
        for r in rows:
            r["balance_money"] = {"value": r["balance"], "currency": "EUR"}
        return rows

    @data("tax")
    def tax(user: User, params: dict) -> list[dict]:
        """Per property and year: rent received, costs passed on and borne. For the tax return."""
        year = int(params.get("year") or date.today().year - 1)
        out = []
        for p in mine(user):
            received = one(
                "SELECT coalesce(sum(l.received), 0) FROM rent_ledger l JOIN tenancies t ON "
                "t.id = l.tenancy_id JOIN units u ON u.id = t.unit_id WHERE u.property_id = :p "
                "AND extract(year FROM l.month) = :y",
                p=p["id"],
                y=year,
            )
            keys = keys_of(p["id"])
            span = year_of(p, year)
            passed = borne = Decimal(0)
            for c in q(
                "SELECT * FROM cost_items WHERE property_id = :p AND state = 'confirmed' AND "
                "period_to >= :s AND period_from <= :e",
                p=p["id"],
                s=span[0],
                e=span[1],
            ):
                part = st.split(c["amount"], (c["period_from"], c["period_to"]), span)
                if keys.get(c["cost_type"], {}).get("passable"):
                    passed += part
                else:
                    borne += part
            out.append(
                {
                    "property": p["name"],
                    "year": year,
                    "received": {"value": received, "currency": "EUR"},
                    "passed_on": {"value": passed, "currency": "EUR"},
                    "borne": {"value": borne, "currency": "EUR"},
                }
            )
        return out

    @registry.action("tax_csv")
    def tax_csv(user: User, params: dict) -> Result:
        out = io.StringIO()
        writer = csv.writer(out, delimiter=";")
        writer.writerow(["property", "year", "rent_received", "costs_passed_on", "costs_borne"])
        for r in tax(user, params):
            writer.writerow(
                [
                    r["property"],
                    r["year"],
                    r["received"]["value"],
                    r["passed_on"]["value"],
                    r["borne"]["value"],
                ]
            )
        return Result(
            download=("rental-income.csv", out.getvalue().encode("utf-8-sig"), "text/csv")
        )

    @data("overview")
    def overview(user: User, params: dict) -> list[dict]:
        arrears = sum(
            1
            for r in ledger_rows(user, params)
            if r["state"] == "Open" and r["month"] < date.today().replace(day=1)
        )
        waiting = sum(1 for c in costs(user, params) if c["state"] == "proposed")
        return [
            {"label": "Months of rent outstanding", "value": arrears, "format": "number"},
            {"label": "Bills to confirm", "value": waiting, "format": "number"},
        ]

    @data("document_cost")
    def document_cost(user: User, params: dict) -> list[dict]:
        documents.get_for_user(params["document_id"], user)
        return [c for c in costs(user, params) if c["document_id"] == params["document_id"]]

    @registry.tool(aggregates_only=True)
    def rental_income(user: User, year: int) -> dict:
        """Rent received and costs per property for a year (for the tax return).

        Args:
            year: the year, such as 2026
        """
        rows = tax(user, {"year": year})
        return {
            "properties": [
                {k: (str(v["value"]) if isinstance(v, dict) else v) for k, v in r.items()}
                for r in rows
            ],
            "documents": [],
            "summary": f"{len(rows)} properties",
        }
