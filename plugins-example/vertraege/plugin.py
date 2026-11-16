"""Contracts and cancellations.

Contract documents become one list with cost, term and the last day for notice. The plugin
reads what the contract says and never sends anything by itself.

How it fits together, top to bottom:
1. reading a contract (the AI, or the values the archive already read),
2. finding or creating the contract it belongs to,
3. the dates, written back to the contract document so the archive's own reminder fires once,
4. price changes as notes, provider confirmations,
5. what the screens show and the buttons do, and two Ask tools.
"""

import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from docuhive.sdk import (
    ActionError,
    FactValue,
    Registry,
    Result,
    User,
    ai,
    documents,
    mail,
    profiles,
    reminders,
    render,
    services,
)
from pydantic import BaseModel
from sqlalchemy import text

from . import dates

EDITABLE = (
    "provider",
    "provider_address",
    "kind",
    "product",
    "customer_number",
    "contract_number",
    "start_date",
    "term_end",
    "renewal_months",
    "notice_amount",
    "notice_unit",
    "notice_to",
    "price",
    "price_period",
    "profile_id",
    "shared",
    "notes",
)
PER_MONTH = {"month": Decimal(1), "quarter": Decimal(3), "year": Decimal(12)}


class Terms(BaseModel):
    provider: str | None = None
    provider_address: list[str] = []
    product: str | None = None
    customer_number: str | None = None
    contract_number: str | None = None
    start_date: date | None = None
    term_end: date | None = None
    minimum_term_months: int | None = None
    renewal_months: int | None = None
    notice_amount: int | None = None
    notice_unit: Literal["days", "weeks", "months"] | None = None
    notice_to: Literal["term_end", "month_end", "quarter_end", "any_day"] | None = None
    price: Decimal | None = None
    price_period: Literal["month", "quarter", "year", "once"] | None = None


class Confirmation(BaseModel):
    is_confirmation: bool
    ends_on: date | None = None


def norm(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def setup(registry: Registry) -> None:  # noqa: C901 - one plugin, many small parts
    def q(sql: str, **params) -> list[dict]:  # type: ignore[no-untyped-def]
        with registry.db.session() as s:
            return [dict(r) for r in s.execute(text(sql), params).mappings()]

    def run(sql: str, **params) -> None:  # type: ignore[no-untyped-def]
        with registry.db.session() as s:
            s.execute(text(sql), params)

    def kind_of(category: str | None) -> str:
        """The kind whose category matches most precisely: internet-phone before utilities."""
        best = ("other", -1)
        for kind in registry.rules("kinds.yaml")["kinds"]:
            for c in kind["categories"]:
                if (
                    category
                    and (category == c or category.startswith(f"{c}/"))
                    and len(c) > best[1]
                ):
                    best = (kind["id"], len(c))
        return best[0]

    def notice_by(c: dict) -> date | None:
        if (
            c["term_end"]
            and c["notice_amount"]
            and c["notice_unit"]
            and c["notice_to"] == "term_end"
        ):
            return dates.notice_by(c["term_end"], c["notice_amount"], c["notice_unit"])
        return None

    def per_month(c: dict) -> Decimal | None:
        if c["price"] is None or c["price_period"] not in PER_MONTH:
            return None
        return (c["price"] / PER_MONTH[c["price_period"]]).quantize(Decimal("0.01"))

    def mine(user: User, contract_id: object = None) -> list[dict]:
        sql = "SELECT * FROM contracts WHERE (owner_id = :u OR shared)"
        if contract_id is not None:
            sql += " AND id = :i"
        return q(sql + " ORDER BY provider", u=user.id, i=int(contract_id or 0))

    def own(user: User, contract_id: object) -> dict:
        found = [c for c in mine(user, contract_id) if c["owner_id"] == user.id]
        if not found:
            raise ActionError("This contract is not yours to change.")
        return found[0]

    def link(contract_id: int, doc_id: str, role: str) -> None:
        run(
            "INSERT INTO contract_documents (contract_id, document_id, role) VALUES (:c, :d, :r) "
            "ON CONFLICT (contract_id, document_id) DO UPDATE SET role = :r",
            c=contract_id,
            d=doc_id,
            r=role,
        )

    def write_back(c: dict) -> None:
        """The archive reminds about a contract document's notice deadline from its end date and
        notice days: keep those in step with the contract, so there is one reminder, not two."""
        deadline = notice_by(c)
        if deadline is None:
            return
        for row in q(
            "SELECT document_id FROM contract_documents WHERE contract_id = :c "
            "AND role = 'contract'",
            c=c["id"],
        ):
            try:
                documents.apply_metadata(
                    row["document_id"],
                    facts={
                        "end_date": FactValue(type="date", value=c["term_end"].isoformat()),
                        "notice_period_days": FactValue(
                            type="number", value=str((c["term_end"] - deadline).days)
                        ),
                    },
                )
            except Exception as error:  # noqa: BLE001 - a locked document keeps its values
                registry.log.info("Dates not written to %s: %s", row["document_id"], error)

    # 1–2. Reading a contract, and finding the contract it belongs to ---------------------------

    def read(doc) -> Terms:  # type: ignore[no-untyped-def]
        try:
            terms = ai.ask("contract-terms", Terms, document=doc)
        except ai.Unavailable:
            f = doc.facts
            value = lambda k: f[k].value if k in f else None  # noqa: E731
            notice = value("notice_period_days")
            terms = Terms(
                start_date=value("start_date"),
                term_end=value("end_date"),
                contract_number=value("contract_number"),
                notice_amount=int(Decimal(notice)) if notice else None,
                notice_unit="days" if notice else None,
                price=value("monthly_cost"),
                price_period="month" if value("monthly_cost") else None,
            )
        if terms.term_end is None and terms.start_date and terms.minimum_term_months:
            terms.term_end = dates.term_end(terms.start_date, terms.minimum_term_months)
        return terms

    def find(owner: int, provider: str, terms: Terms) -> dict | None:
        same = [
            c
            for c in q("SELECT * FROM contracts WHERE owner_id = :o", o=owner)
            if norm(c["provider"]) == norm(provider)
        ]
        for c in same:
            numbers = {norm(c["contract_number"]), norm(c["customer_number"])} - {""}
            if numbers & {norm(terms.contract_number), norm(terms.customer_number)}:
                return c
        return next((c for c in same if norm(c["product"]) == norm(terms.product)), None)

    def contract_from(doc) -> None:  # type: ignore[no-untyped-def]
        terms = read(doc)
        provider = terms.provider or doc.correspondent or doc.title or "Unknown provider"
        values = terms.model_dump(exclude={"provider", "minimum_term_months"}) | {
            "notice_to": terms.notice_to or "term_end",
            "kind": kind_of(doc.category),
        }
        existing = find(doc.owner_id, provider, terms)
        if existing is None:
            row_values = values | {
                "owner_id": doc.owner_id,
                "shared": doc.shared,
                "provider": provider,
            }
            columns = ", ".join(row_values)
            marks = ", ".join(f":{c}" for c in row_values)
            with registry.db.session() as s:
                cid = s.execute(
                    text(f"INSERT INTO contracts ({columns}) VALUES ({marks}) RETURNING id"),
                    row_values,
                ).scalar_one()
        else:  # fill what is missing; what a person set stays as they set it
            cid = existing["id"]
            for field, value in values.items():
                if value not in (None, []) and field not in existing["locked_fields"]:
                    run(f"UPDATE contracts SET {field} = :v WHERE id = :i", v=value, i=cid)
        link(cid, doc.id, "contract")
        write_back(q("SELECT * FROM contracts WHERE id = :i", i=cid)[0])

    # 4. Price changes and confirmations --------------------------------------------------------

    def price_note(doc, role: str) -> None:  # type: ignore[no-untyped-def]
        amount = doc.facts.get("new_price") or doc.facts.get("amount_total")
        known = [
            c
            for c in q(
                "SELECT * FROM contracts WHERE owner_id = :o AND state = 'active'", o=doc.owner_id
            )
            if norm(c["provider"]) == norm(doc.correspondent)
        ]
        if not known or amount is None:
            return
        c, price = known[0], Decimal(amount.value)
        link(c["id"], doc.id, role)
        if c["price"] is None or abs(price - c["price"]) > max(Decimal("0.01"), c["price"] / 100):
            effective = doc.facts.get("effective_date")
            run(
                "INSERT INTO price_history (contract_id, valid_from, price, price_period, "
                "document_id) VALUES (:c, :v, :p, :pp, :d)",
                c=c["id"],
                p=price,
                v=date.fromisoformat(effective.value) if effective else doc.document_date,
                pp=c["price_period"],
                d=doc.id,
            )

    def confirmation(doc) -> None:  # type: ignore[no-untyped-def]
        waiting = [
            c
            for c in q(
                "SELECT * FROM contracts WHERE owner_id = :o AND state = 'cancelled'",
                o=doc.owner_id,
            )
            if norm(c["provider"]) == norm(doc.correspondent)
        ]
        if not waiting:
            return
        try:
            answer = ai.ask("cancellation-confirmation", Confirmation, document=doc)
        except ai.Unavailable:
            return
        if answer.is_confirmation:
            c = waiting[0]
            run(
                "UPDATE contracts SET state = 'ended', cancel_confirmed_on = :d, "
                "cancel_effective = coalesce(:e, cancel_effective) WHERE id = :i",
                d=doc.document_date or date.today(),
                e=answer.ends_on,
                i=c["id"],
            )
            link(c["id"], doc.id, "confirmation")
            reminders.clear(c["owner_id"], f"confirm:{c['id']}")

    @registry.on("document.classified")
    def classified(event) -> None:  # type: ignore[no-untyped-def]
        doc = documents.get(event.document_id)
        if event.document_type == "contract":
            contract_from(doc)
        elif event.document_type in ("contract_change", "invoice"):
            price_note(doc, "change" if event.document_type == "contract_change" else "invoice")
        elif event.document_type == "letter":
            confirmation(doc)

    @registry.every(timedelta(days=1), "renew")
    def renew(payload, ctx) -> None:  # type: ignore[no-untyped-def]
        """Terms that ran out without notice renew; the dates move with them."""
        today = date.today()
        for c in q(
            "SELECT * FROM contracts WHERE state = 'active' AND term_end < :t "
            "AND renewal_months > 0",
            t=today,
        ):
            c["term_end"] = dates.roll(c["term_end"], c["renewal_months"], today)
            run("UPDATE contracts SET term_end = :e WHERE id = :i", e=c["term_end"], i=c["id"])
            write_back(c)

    # 5. Screens --------------------------------------------------------------------------------

    labels = {k["id"]: k["label"] for k in registry.rules("kinds.yaml")["kinds"]}

    def row(c: dict) -> dict:
        deadline, month = notice_by(c), per_month(c)
        days = (deadline - date.today()).days if deadline else None
        return c | {
            "per_month": {"value": month, "currency": c["currency"]} if month is not None else None,
            "per_year": {"value": month * 12, "currency": c["currency"]}
            if month is not None
            else None,
            "notice_by": deadline,
            "status": "Dates missing"
            if c["state"] == "active" and deadline is None and c["notice_to"] == "term_end"
            else None
            if days is None
            else "Notice date passed"
            if days < 0
            else "Notice soon"
            if days <= 30
            else None,
            "kind_label": labels.get(c["kind"], c["kind"]),
            "state_label": {"active": "Active", "cancelled": "Cancelled", "ended": "Ended"}[
                c["state"]
            ],
        }

    def choices(*pairs: str) -> list[dict]:
        return [{"value": pairs[i], "label": pairs[i + 1]} for i in range(0, len(pairs), 2)]

    data = registry.data
    data("contracts")(lambda user, params: [row(c) for c in mine(user)])
    data("kinds")(
        lambda user, params: [
            {"value": k["id"], "label": k["label"]} for k in registry.rules("kinds.yaml")["kinds"]
        ]
    )
    data("units")(
        lambda user, params: choices("days", "Days", "weeks", "Weeks", "months", "Months")
    )
    data("notice_tos")(
        lambda user, params: choices(
            "term_end",
            "To the end of the term",
            "month_end",
            "To the end of a month",
            "quarter_end",
            "To the end of a quarter",
            "any_day",
            "At any time",
        )
    )
    data("periods")(
        lambda user, params: choices(
            "month", "Per month", "quarter", "Per quarter", "year", "Per year", "once", "Once"
        )
    )
    data("profiles")(
        lambda user, params: [
            {"value": str(p["id"]), "label": p["name"]} for p in profiles.list(user)
        ]
    )
    data("reasons")(
        lambda user, params: (
            [{"value": "", "label": "No special reason"}]
            + [
                {"value": r["id"], "label": r["en"]}
                for r in registry.rules("kinds.yaml")["special_reasons"]
            ]
        )
    )

    @registry.data("contract")
    def contract(user: User, params: dict) -> dict:
        found = mine(user, params.get("id"))
        if not found:
            raise ActionError("This contract does not exist or is not yours.")
        c = row(found[0])
        if c["notice_to"] != "term_end" and c["notice_amount"] and c["notice_unit"]:
            c["earliest_end"] = dates.earliest_end(
                date.today(), c["notice_amount"], c["notice_unit"], c["notice_to"]
            )
        return c | {"provider_address": "\n".join(c["provider_address"])}

    @registry.data("contract_documents")
    def contract_documents(user: User, params: dict) -> list[dict]:
        contract(user, params)  # access
        out = []
        for r in q("SELECT * FROM contract_documents WHERE contract_id = :c", c=int(params["id"])):
            try:
                doc = documents.get_for_user(r["document_id"], user)
            except documents.NotFound:
                continue
            out.append(
                {"id": doc.id, "title": doc.title, "date": doc.document_date, "role": r["role"]}
            )
        return sorted(out, key=lambda d: d["date"] or date.min, reverse=True)

    @registry.data("prices")
    def prices(user: User, params: dict) -> list[dict]:
        c = contract(user, params)
        return [
            r
            | {
                "amount": {"value": r["price"], "currency": c["currency"]},
                "status": "Accepted" if r["accepted"] else "New: check it",
            }
            for r in q(
                "SELECT * FROM price_history WHERE contract_id = :c ORDER BY valid_from DESC",
                c=c["id"],
            )
        ]

    @registry.data("payments")
    def payments(user: User, params: dict) -> list[dict]:
        """With the bank plugin: what was really paid to the provider in the last 12 months."""
        c = contract(user, params)
        if not services.available("bank.transactions"):
            return []
        since = date.today() - timedelta(days=365)
        return [
            t
            for t in services.get("bank.transactions")(user, counterparty=c["provider"])
            if t["booking_date"] >= since
        ]

    @registry.data("calendar")
    def calendar(user: User, params: dict) -> list[dict]:
        horizon = date.today() + timedelta(days=366)
        rows = [row(c) for c in mine(user) if c["state"] == "active"]
        return sorted(
            (
                {"month": r["notice_by"].strftime("%Y-%m"), **r}
                for r in rows
                if r["notice_by"] and date.today() <= r["notice_by"] <= horizon
            ),
            key=lambda r: r["notice_by"],
        )

    @registry.data("costs")
    def costs(user: User, params: dict) -> list[dict]:
        totals: dict[str, Decimal] = {}
        for c in mine(user):
            if c["state"] == "active" and (month := per_month(c)) is not None:
                totals[c["kind"]] = totals.get(c["kind"], Decimal(0)) + month
        return [{"kind": k, "per_month": v} for k, v in sorted(totals.items())]

    @registry.data("overview")
    def overview(user: User, params: dict) -> list[dict]:
        soon = calendar(user, params)[:3]
        total = sum((r["per_month"] for r in costs(user, params)), Decimal(0))
        return [
            {
                "label": "Contracts per month",
                "value": {"value": total, "currency": "EUR"},
                "format": "money",
            }
        ] + [
            {"label": f"Notice to {r['provider']}", "value": r["notice_by"], "format": "date"}
            for r in soon
        ]

    @registry.data("document_contract")
    def document_contract(user: User, params: dict) -> list[dict]:
        documents.get_for_user(params["document_id"], user)
        ids = {
            r["contract_id"]
            for r in q(
                "SELECT contract_id FROM contract_documents WHERE document_id = :d",
                d=params["document_id"],
            )
        }
        return [row(c) for c in mine(user) if c["id"] in ids]

    # Buttons -----------------------------------------------------------------------------------

    @registry.action("save_contract")
    def save_contract(user: User, params: dict) -> Result:
        """A person's values are theirs: the fields they set are never changed by the AI."""
        c = own(user, params.get("id"))
        changes = {}
        for field in EDITABLE:
            if field not in params:
                continue
            value = params[field]
            if field == "provider_address":
                value = [line.strip() for line in str(value or "").splitlines() if line.strip()]
            elif field in ("start_date", "term_end"):
                value = date.fromisoformat(value) if value else None
            elif field in ("renewal_months", "notice_amount", "profile_id"):
                value = int(value) if value not in (None, "") else None
            elif field == "price":
                value = Decimal(str(value)) if value not in (None, "") else None
            elif field == "shared":
                value = bool(value)
            else:
                value = value or None
            if value != c[field]:
                changes[field] = value
        if not changes:
            return Result(message="Nothing changed.")
        if changes.get("provider", c["provider"]) is None:
            return Result(errors={"provider": "Who is the contract with?"})
        sets = ", ".join(f"{f} = :{f}" for f in changes)
        locked = sorted(set(c["locked_fields"]) | set(changes))
        run(
            f"UPDATE contracts SET {sets}, locked_fields = :locked WHERE id = :id",
            **changes,
            locked=locked,
            id=c["id"],
        )
        write_back(q("SELECT * FROM contracts WHERE id = :i", i=c["id"])[0])
        return Result(message="Saved. These values are yours now; the AI will not change them.")

    @registry.action("accept_price")
    def accept_price(user: User, params: dict) -> str:
        note = q("SELECT * FROM price_history WHERE id = :i", i=int(params["id"]))
        c = own(user, note[0]["contract_id"] if note else 0)
        run("UPDATE price_history SET accepted = true WHERE id = :i", i=note[0]["id"])
        run(
            "UPDATE contracts SET price = :p, locked_fields = array_append(array_remove("
            "locked_fields, 'price'), 'price') WHERE id = :i",
            p=note[0]["price"],
            i=c["id"],
        )
        return f"The contract's price is now {note[0]['price']}."

    def letter_context(user: User, c: dict, params: dict, language: str) -> dict:
        if not c["profile_id"]:
            raise ActionError("Choose who the contract is with (your identity) and save first.")
        if not c["provider_address"]:
            raise ActionError("Enter the provider's address and save first.")
        me = profiles.get(user, c["profile_id"])
        a = me["address"]
        reason = next(
            (
                r[language]
                for r in registry.rules("kinds.yaml")["special_reasons"]
                if r["id"] == params.get("reason")
            ),
            None,
        )
        on_date = params.get("on_date")
        end = (
            date.fromisoformat(on_date)
            if on_date
            else dates.earliest_end(
                date.today(),
                c["notice_amount"] or 0,
                c["notice_unit"] or "days",
                c["notice_to"],
                c["term_end"],
                c["renewal_months"],
            )
        )
        return {
            "language": language,
            "sender_line": f"{me['name']} · {a['street']} · {a['postcode']} {a['city']}",
            "recipient": c["provider_address"],
            "place": a["city"],
            "date": date.today().strftime("%d.%m.%Y"),
            "name": me["name"],
            "contract": c,
            "reason": reason,
            "end": end.strftime("%d.%m.%Y"),
            "to_date": bool(on_date),
        }

    @registry.action("prepare_cancellation")
    def prepare_cancellation(user: User, params: dict) -> Result:
        """A draft letter in the archive. Nothing is sent: post it, or send it by mail below."""
        c = own(user, params.get("id"))
        language = registry.settings.get("letter_language") or "de"
        pdf = render.pdf(f"cancellation.{language}.html", letter_context(user, c, params, language))
        sources = [
            r["document_id"]
            for r in q(
                "SELECT document_id FROM contract_documents WHERE "
                "contract_id = :c AND role = 'contract'",
                c=c["id"],
            )
        ]
        doc_id = documents.create(
            user,
            pdf,
            filename=f"cancellation-{norm(c['provider']) or 'contract'}.pdf",
            title=f"Cancellation: {c['provider']}",
            document_type="letter",
            tags=["cancellation"],
            derived_from=sources,
        )
        link(c["id"], doc_id, "cancellation")
        return Result(
            message="The letter is ready. Check it, then post it or send it by mail.",
            goto=f"/documents/{doc_id}",
        )

    def sent(user: User, c: dict) -> None:
        run(
            "UPDATE contracts SET state = 'cancelled', cancel_sent_on = :d WHERE id = :i",
            d=date.today(),
            i=c["id"],
        )
        reminders.set(
            c["owner_id"],
            f"confirm:{c['id']}",
            f"No confirmation from {c['provider']} yet",
            date.today() + timedelta(days=14),
            days_before=[0],
            link=f"/plugins/vertraege/contract?id={c['id']}",
        )

    @registry.action("mark_sent")
    def mark_sent(user: User, params: dict) -> str:
        c = own(user, params.get("id"))
        sent(user, c)
        return "Marked as sent. You are reminded in two weeks if no confirmation has arrived."

    @registry.action("send_cancellation", outgoing=True)
    def send_cancellation(user: User, params: dict) -> str:
        c = own(user, params.get("id"))
        letters = [
            r["document_id"]
            for r in q(
                "SELECT document_id FROM contract_documents WHERE "
                "contract_id = :c AND role = 'cancellation'",
                c=c["id"],
            )
        ]
        if not letters:
            raise ActionError("Prepare the letter first.")
        if not params.get("to"):
            raise ActionError("Enter the provider's mail address.")
        mail.send(
            user,
            c["profile_id"],
            [params["to"]],
            f"Kündigung / Cancellation {c['contract_number'] or ''}".strip(),
            render.text("cancellation-mail.txt", {"contract": c}),
            [letters[-1]],
        )
        sent(user, c)
        return f"Sent to {params['to']}. The letter and the mail are kept with the contract."

    # Ask ---------------------------------------------------------------------------------------

    @registry.tool
    def contracts_list(user: User, kind: str = "", cancellable_within_days: int = 0) -> dict:
        """Your contracts with cost and notice dates.

        Args:
            kind: energy, telecom, insurance, lease, subscription, membership, software, service
            cancellable_within_days: only contracts whose last day for notice is this soon
        """
        rows = [row(c) for c in mine(user) if c["state"] == "active" and kind in ("", c["kind"])]
        if cancellable_within_days:
            limit = date.today() + timedelta(days=cancellable_within_days)
            rows = [r for r in rows if r["notice_by"] and r["notice_by"] <= limit]
        ids = (
            q(
                "SELECT document_id FROM contract_documents WHERE contract_id = ANY(:c)",
                c=[r["id"] for r in rows],
            )
            if rows
            else []
        )
        return {
            "contracts": [
                {
                    "provider": r["provider"],
                    "product": r["product"],
                    "per_month": str(r["per_month"]["value"]) if r["per_month"] else None,
                    "notice_by": r["notice_by"] and r["notice_by"].isoformat(),
                }
                for r in rows
            ],
            "documents": [i["document_id"] for i in ids],
            "summary": f"{len(rows)} contracts",
        }

    @registry.tool(aggregates_only=True)
    def monthly_cost(user: User) -> dict:
        """What your active contracts cost per month, by kind."""
        rows = costs(user, {})
        return {
            "per_month": {r["kind"]: str(r["per_month"]) for r in rows},
            "documents": [],
            "summary": f"{sum(r['per_month'] for r in rows)} EUR per month",
        }
