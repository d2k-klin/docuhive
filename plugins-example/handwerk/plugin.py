"""Craftsman invoices and the upkeep of a home.

1. A craftsman invoice arrives: the AI copies labour, material, the day of the work and the kind
   of work. Python checks the figures, works out the warranty end (rules/warranty.yaml) and keeps
   them as values on the document, which the person can correct.
2. Per year: the labour you can claim for the tax reduction (§ 35a EStG, rules/35a.yaml), per
   kind and capped. With the bank plugin the year you paid counts, and only transfers.
3. Upkeep: recurring tasks with reminders; an invoice for one of them marks it done.
"""

import calendar
from datetime import date
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
    reminders,
    services,
)
from pydantic import BaseModel
from sqlalchemy import text

CENT = Decimal("0.01")
KIND_LABELS = {"building": "Building work", "craftsman": "Craftsman", "household": "Household"}


class Labour(BaseModel):
    labour_gross: Decimal | None = None
    labour_net: Decimal | None = None
    vat_rate: Decimal | None = None
    material_gross: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = None
    work_date: date | None = None
    kind: Literal["building", "craftsman", "household"] | None = None
    paid_in_cash: bool = False
    task: str | None = None


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def money(value: object) -> dict | None:
    return None if value is None else {"value": value, "currency": "EUR"}


def amount(doc, name: str) -> Decimal | None:  # type: ignore[no-untyped-def]
    value = doc.facts.get(name)
    return Decimal(value.value) if value else None


def setup(registry: Registry) -> None:  # noqa: C901
    def q(sql: str, **params) -> list[dict]:
        with registry.db.session() as s:
            return [dict(r) for r in s.execute(text(sql), params).mappings()]

    def run(sql: str, **params) -> None:
        with registry.db.session() as s:
            s.execute(text(sql), params)

    presets = lambda: {t["id"]: t for t in registry.rules("maintenance.yaml")["tasks"]}  # noqa: E731

    # 1. Reading an invoice ---------------------------------------------------------------------

    @registry.on("document.classified")
    def on_classified(event) -> None:  # type: ignore[no-untyped-def]
        if event.document_type == "craftsman_invoice":
            read_invoice(event.document_id)

    def read_invoice(document_id: str) -> None:
        doc = documents.get(document_id)
        try:
            got = ai.ask("labour", Labour, document=doc)
        except ai.Unavailable:
            return  # the person can enter labour and material on the document
        labour = got.labour_gross
        if labour is None and got.labour_net is not None and got.vat_rate is not None:
            labour = (got.labour_net * (100 + got.vat_rate) / 100).quantize(CENT)
        total = got.total
        # Never more labour than the invoice total: then the reading is wrong, not the invoice.
        if labour is not None and total is not None and labour > total:
            labour = None
        currency = got.currency or "EUR"
        facts: dict[str, FactValue] = {}
        for name, value in (
            ("labour_cost", labour),
            ("material_cost", got.material_gross),
            ("amount_total", total),
        ):
            if value is not None:
                facts[name] = FactValue(type="money", value=str(value), currency=currency)
        worked = got.work_date or doc.document_date
        if got.work_date:
            facts["work_date"] = FactValue(type="date", value=got.work_date.isoformat())
        if got.kind:
            facts["service_kind"] = FactValue(type="string", value=got.kind)
            years = registry.rules("warranty.yaml")["years_by_kind"].get(got.kind, 0)
            if years and worked:
                until = add_months(worked, 12 * int(years))
                facts["warranty_until"] = FactValue(type="date", value=until.isoformat())
        if got.paid_in_cash:
            facts["payment"] = FactValue(type="string", value="cash")
        if facts:
            documents.apply_metadata(document_id, facts=facts)
        if got.task and got.task in presets() and worked:
            for task in q(
                "SELECT * FROM maintenance WHERE owner_id = :o AND preset = :p",
                o=doc.owner_id,
                p=got.task,
            ):
                if task["last_done"] is None or worked > task["last_done"]:
                    mark_done(task, worked, document_id)

    # 2. Invoices and the tax reduction ---------------------------------------------------------

    def paid(doc) -> tuple[date | None, bool]:  # type: ignore[no-untyped-def]
        """When it was paid, and whether that is known to be a transfer (the bank plugin)."""
        if services.available("bank.payments_for"):
            payments = services.get("bank.payments_for")(doc.id)
            if payments:
                return payments[0]["date"], True
        return doc.document_date, False

    def kind_of(doc) -> str:  # type: ignore[no-untyped-def]
        value = doc.facts.get("service_kind")
        return value.value if value and value.value in KIND_LABELS else "craftsman"

    def invoices(user: User, year: int) -> list[dict]:
        rows = []
        for doc in documents.find(user, document_type="craftsman_invoice", limit=2000):
            on, by_transfer = paid(doc)
            if on is None or on.year != year:
                continue
            labour = amount(doc, "labour_cost")
            cash = (doc.facts.get("payment") or FactValue(type="string", value="")).value == "cash"
            until = doc.facts.get("warranty_until")
            rows.append(
                {
                    "id": doc.id,
                    "title": doc.title or "Craftsman invoice",
                    "from": doc.correspondent or "",
                    "paid_on": on,
                    "kind": kind_of(doc),
                    "kind_label": KIND_LABELS[kind_of(doc)],
                    "labour": labour,
                    "material": amount(doc, "material_cost"),
                    "total": amount(doc, "amount_total"),
                    "counts": labour is not None and not cash,
                    "note": "Paid in cash: does not count"
                    if cash
                    else "Labour missing"
                    if labour is None
                    else "Paid by transfer"
                    if by_transfer
                    else "",
                    "warranty_until": until.value if until else None,
                }
            )
        return sorted(rows, key=lambda r: r["paid_on"])

    def reduction(user: User, year: int) -> list[dict]:
        """Per kind: labour that counts, the share, the cap and what comes off the tax."""
        rules = registry.rules("35a.yaml")["years"].get(year)
        if rules is None:
            return []
        rows = invoices(user, year)
        out = []
        for key, kinds in (("craftsman", ("craftsman", "building")), ("household", ("household",))):
            labour = sum(
                (r["labour"] for r in rows if r["counts"] and r["kind"] in kinds), Decimal(0)
            )
            spec = rules[key]
            share = (labour * Decimal(str(spec["rate"])) / 100).quantize(CENT)
            out.append(
                {
                    "kind": key,
                    "label": spec["label"],
                    "labour": labour,
                    "reduction": min(share, Decimal(str(spec["cap"]))),
                    "cap": Decimal(str(spec["cap"])),
                    "documents": [r["id"] for r in rows if r["counts"] and r["kind"] in kinds],
                }
            )
        return out

    def rate(year: int, kind: str) -> Decimal | None:
        """The share of labour that counts, from rules/35a.yaml, or None for an unknown year."""
        rules = registry.rules("35a.yaml")["years"].get(year)
        if rules is None:
            return None
        return (
            Decimal(str(rules["household" if kind == "household" else "craftsman"]["rate"])) / 100
        )

    def share(labour: Decimal | None, year: int, kind: str) -> dict | None:
        part = rate(year, kind)
        return money((labour * part).quantize(CENT)) if labour is not None and part else None

    def year_of(params: dict) -> int:
        return int(params.get("year") or date.today().year)

    @registry.data("invoices")
    def invoices_rows(user: User, params: dict) -> list[dict]:
        year = year_of(params)
        return [
            r
            | {
                "labour": money(r["labour"]),
                "material": money(r["material"]),
                "share": share(r["labour"], year, r["kind"]) if r["counts"] else None,
                "year": str(year),
            }
            for r in invoices(user, year)
        ]

    @registry.data("reduction")
    def reduction_rows(user: User, params: dict) -> list[dict]:
        return [
            r
            | {
                "labour": money(r["labour"]),
                "reduction": money(r["reduction"]),
                "cap": money(r["cap"]),
                "year": str(year_of(params)),
            }
            for r in reduction(user, year_of(params))
        ]

    @registry.service
    def year_35a(user: User, year: int) -> list[dict]:
        """For the tax plugin: labour per kind and the reduction for the household's return."""
        return reduction(user, year)

    # 3. Upkeep ---------------------------------------------------------------------------------

    def own_task(user: User, task_id: object) -> dict:
        found = q(
            "SELECT * FROM maintenance WHERE id = :i AND owner_id = :o",
            i=int(task_id or 0),
            o=user.id,
        )
        if not found:
            raise ActionError("This task is not yours.")
        return found[0]

    def remind(task: dict) -> None:
        reminders.set(
            task["owner_id"],
            f"task:{task['id']}",
            f"Due: {task['name']}",
            task["next_due"],
            days_before=[14, 0],
            link="/plugins/handwerk/upkeep",
        )

    def mark_done(task: dict, on: date, document_id: str | None = None) -> None:
        due = add_months(on, task["every_months"])
        run(
            "UPDATE maintenance SET last_done = :d, next_due = :n, "
            "document_id = coalesce(:doc, document_id) WHERE id = :i",
            d=on,
            n=due,
            doc=document_id,
            i=task["id"],
        )
        remind(task | {"next_due": due})

    @registry.data("preset_options")
    def preset_options(user: User, params: dict) -> list[dict]:
        taken = {
            r["preset"] for r in q("SELECT preset FROM maintenance WHERE owner_id = :o", o=user.id)
        }
        return [{"value": "", "label": "My own task (enter a name)"}] + [
            {"value": k, "label": f"{t['label']} (every {t['every_months']} months)"}
            for k, t in presets().items()
            if k not in taken
        ]

    @registry.action("add_task")
    def add_task(user: User, params: dict) -> Result:
        preset = presets().get(str(params.get("preset") or ""))
        name = str(params.get("name") or "").strip() or (preset["label"] if preset else "")
        if not name:
            return Result(errors={"name": "Name the task, or choose one of the usual ones"})
        try:
            every = int(params.get("every_months") or (preset or {}).get("every_months") or 0)
        except ValueError:
            every = 0
        if not 1 <= every <= 240:
            return Result(errors={"every_months": "Every 1 to 240 months"})
        last = date.fromisoformat(params["last_done"]) if params.get("last_done") else None
        due = add_months(last, every) if last else date.today()
        with registry.db.session() as s:
            task_id = s.execute(
                text(
                    "INSERT INTO maintenance (owner_id, name, preset, every_months, last_done, "
                    "next_due) VALUES (:o, :n, :p, :e, :l, :d) ON CONFLICT (owner_id, name) DO "
                    "NOTHING RETURNING id"
                ),
                {
                    "o": user.id,
                    "n": name,
                    "p": preset and preset["id"],
                    "e": every,
                    "l": last,
                    "d": due,
                },
            ).scalar()
        if task_id is None:
            return Result(errors={"name": "You already have a task with this name"})
        remind(own_task(user, task_id))
        return Result(message=f"“{name}” is due on {due:%d.%m.%Y}.")

    @registry.action("task_done")
    def task_done(user: User, params: dict) -> str:
        task = own_task(user, params.get("id"))
        mark_done(task, date.today())
        return f"Done. Next time: {add_months(date.today(), task['every_months']):%d.%m.%Y}."

    @registry.action("remove_task", destructive=True)
    def remove_task(user: User, params: dict) -> str:
        task = own_task(user, params.get("id"))
        run("DELETE FROM maintenance WHERE id = :i", i=task["id"])
        reminders.clear(user.id, f"task:{task['id']}")
        return "Removed."

    @registry.data("tasks")
    def tasks(user: User, params: dict) -> list[dict]:
        today = date.today()
        return [
            r
            | {
                "state": "Due"
                if r["next_due"] <= today
                else "Soon"
                if (r["next_due"] - today).days <= 30
                else "Later",
                "every": f"every {r['every_months']} months",
            }
            for r in q(
                "SELECT * FROM maintenance WHERE owner_id = :o ORDER BY next_due, name", o=user.id
            )
        ]

    # 4. Dashboard, document panel and Ask ------------------------------------------------------

    @registry.data("overview")
    def overview(user: User, params: dict) -> list[dict]:
        due = [t for t in tasks(user, params) if t["state"] != "Later"]
        out: list[dict] = [{"label": "Upkeep due soon", "value": len(due), "format": "number"}]
        if due:
            out.append({"label": due[0]["name"], "value": due[0]["next_due"], "format": "date"})
        return out

    @registry.data("document_work")
    def document_work(user: User, params: dict) -> list[dict]:
        doc = documents.get_for_user(params["document_id"], user)
        if doc.document_type != "craftsman_invoice":
            return []
        labour = amount(doc, "labour_cost")
        until = doc.facts.get("warranty_until")
        return [
            {
                "kind": KIND_LABELS[kind_of(doc)],
                "labour": money(labour),
                "share": share(labour, (doc.document_date or date.today()).year, kind_of(doc)),
                "warranty_until": until.value if until else None,
            }
        ]

    @registry.tool
    def home_costs(user: User, year: int) -> dict:
        """Craftsman and household-service invoices of a year: labour, the estimated tax
        reduction (§ 35a), and the work still under warranty."""
        rows = invoices(user, year)
        parts = reduction(user, year)
        today = date.today().isoformat()
        return {
            "year": year,
            "reduction": {r["label"]: str(r["reduction"]) for r in parts},
            "under_warranty": [
                {"from": r["from"], "title": r["title"], "until": r["warranty_until"]}
                for r in rows
                if r["warranty_until"] and r["warranty_until"] >= today
            ],
            "documents": [r["id"] for r in rows],
            "summary": f"{len(rows)} invoices in {year}",
        }
