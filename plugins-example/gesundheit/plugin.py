"""Health claims: which bills went to the insurer and what came back.

1. A medical bill arrives: it becomes a claim to submit, with a reminder.
2. The person marks bills as submitted (several at once); a reminder follows if nothing comes back.
3. A reimbursement notice arrives: the AI copies its lines; each is matched to a bill by number,
   else by amount and date. Lines that match nothing wait on the page to be matched by hand.
4. Per year: what the bills cost and what you paid yourself, for the tax return.
"""

import re
from datetime import date, timedelta
from decimal import Decimal

from docuhive.sdk import ActionError, Registry, Result, User, ai, documents, reminders
from pydantic import BaseModel
from sqlalchemy import text

STATES = {
    "open": "To submit",
    "submitted": "Submitted",
    "reimbursed": "Paid back",
    "not_claimed": "Not claimed",
}


class Line(BaseModel):
    bill_number: str | None = None
    treatment_date: date | None = None
    billed: Decimal | None = None
    reimbursed: Decimal = Decimal(0)


class Notice(BaseModel):
    lines: list[Line] = []
    notice_date: date | None = None


def norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def money(value: object) -> dict | None:
    return None if value is None else {"value": value, "currency": "EUR"}


def setup(registry: Registry) -> None:  # noqa: C901
    def q(sql: str, **params) -> list[dict]:
        with registry.db.session() as s:
            return [dict(r) for r in s.execute(text(sql), params).mappings()]

    def run(sql: str, **params) -> None:
        with registry.db.session() as s:
            s.execute(text(sql), params)

    def wait_days() -> int:
        return int(registry.settings.get("remind_after_days") or 30)

    # 1. Bills become claims --------------------------------------------------------------------

    @registry.on("document.classified")
    def on_classified(event) -> None:  # type: ignore[no-untyped-def]
        if event.document_type == "medical_bill":
            new_claim(event.document_id)
        elif event.document_type == "reimbursement_notice":
            read_notice(event.document_id)

    def new_claim(document_id: str) -> None:
        doc = documents.get(document_id)
        with registry.db.session() as s:
            claim_id = s.execute(
                text(
                    "INSERT INTO claims (owner_id, document_id) VALUES (:o, :d) "
                    "ON CONFLICT (document_id) DO NOTHING RETURNING id"
                ),
                {"o": doc.owner_id, "d": document_id},
            ).scalar()
        if claim_id is not None:
            remind(claim_id, doc.owner_id, "open", doc.title, date.today())

    def remind(claim_id: int, owner: int, state: str, title: str | None, since: date) -> None:
        key, name = f"claim:{claim_id}", title or "a medical bill"
        if state == "open":
            label = f"Submit to your insurer: {name}"
        elif state == "submitted":
            label = f"Nothing paid back yet: {name}"
        else:
            reminders.clear(owner, key)
            return
        reminders.set(
            owner,
            key,
            label,
            since + timedelta(days=wait_days()),
            days_before=[0],
            link="/plugins/gesundheit/claims",
        )

    # 2. Reimbursement notices ------------------------------------------------------------------

    def bill(doc) -> tuple[Decimal | None, date | None, str]:  # type: ignore[no-untyped-def]
        total, when, number = (
            doc.facts.get(k) for k in ("amount_total", "treatment_date", "bill_number")
        )
        return (
            Decimal(total.value) if total else None,
            date.fromisoformat(when.value) if when else doc.document_date,
            norm(number.value if number else ""),
        )

    def read_notice(document_id: str) -> None:
        notice = documents.get(document_id)
        done = q(
            "SELECT 1 FROM claims WHERE notice_document_id = :n UNION ALL "
            "SELECT 1 FROM unmatched WHERE notice_document_id = :n",
            n=document_id,
        )
        if done:
            return  # read once; a retried job must not count it twice
        try:
            got = ai.ask("reimbursement", Notice, document=notice)
        except ai.Unavailable:
            return  # the bills can be marked as paid back by hand
        waiting = {
            c["id"]: (c, documents.get(c["document_id"]))
            for c in q(
                "SELECT * FROM claims WHERE owner_id = :o AND state IN ('open', 'submitted')",
                o=notice.owner_id,
            )
        }
        paid: dict[int, Decimal] = {}
        for line in got.lines:
            claim_id = match(line, waiting)
            if claim_id is None:
                run(
                    "INSERT INTO unmatched (owner_id, notice_document_id, bill_number, "
                    "treatment_date, billed, reimbursed) VALUES (:o, :n, :b, :t, :a, :r) "
                    "ON CONFLICT DO NOTHING",
                    o=notice.owner_id,
                    n=document_id,
                    b=line.bill_number,
                    t=line.treatment_date,
                    a=line.billed,
                    r=line.reimbursed,
                )
            else:
                paid[claim_id] = paid.get(claim_id, Decimal(0)) + line.reimbursed
        for claim_id, amount in paid.items():
            settle(waiting[claim_id][0], amount, document_id)

    def match(line: Line, waiting: dict) -> int | None:
        number = norm(line.bill_number)
        if number:
            hits = [i for i, (_, d) in waiting.items() if bill(d)[2] == number]
            if len(hits) == 1:
                return hits[0]
        if line.billed is None:
            return None
        hits = [
            i
            for i, (_, d) in waiting.items()
            if bill(d)[0] == line.billed
            and (line.treatment_date is None or bill(d)[1] == line.treatment_date)
        ]
        return hits[0] if len(hits) == 1 else None  # two equal bills: let the person choose

    def settle(claim: dict, amount: Decimal, notice_id: str | None) -> None:
        run(
            "UPDATE claims SET state = 'reimbursed', reimbursed = coalesce(reimbursed, 0) + :a, "
            "notice_document_id = coalesce(:n, notice_document_id) WHERE id = :i",
            a=amount,
            n=notice_id,
            i=claim["id"],
        )
        remind(claim["id"], claim["owner_id"], "reimbursed", None, date.today())

    # 3. What the person does -------------------------------------------------------------------

    def own(user: User, claim_id: object) -> dict:
        found = q(
            "SELECT * FROM claims WHERE id = :i AND owner_id = :o", i=int(claim_id or 0), o=user.id
        )
        if not found:
            raise ActionError("This bill is not yours.")
        return found[0]

    def chosen(user: User, params: dict) -> list[dict]:
        ids = [r["id"] for r in params.get("rows") or []] or [params.get("id")]
        return [own(user, i) for i in ids]

    @registry.action("submitted")
    def submitted(user: User, params: dict) -> str:
        on = date.fromisoformat(params["on"]) if params.get("on") else date.today()
        claims = [c for c in chosen(user, params) if c["state"] in ("open", "submitted")]
        for c in claims:
            run(
                "UPDATE claims SET state = 'submitted', submitted_on = :d WHERE id = :i",
                d=on,
                i=c["id"],
            )
            remind(c["id"], c["owner_id"], "submitted", documents.get(c["document_id"]).title, on)
        return f"{len(claims)} {'bill' if len(claims) == 1 else 'bills'} marked as submitted."

    @registry.action("not_claimed")
    def not_claimed(user: User, params: dict) -> str:
        for c in chosen(user, params):
            run("UPDATE claims SET state = 'not_claimed' WHERE id = :i", i=c["id"])
            remind(c["id"], c["owner_id"], "not_claimed", None, date.today())
        return (
            "Kept as your own cost. A premium refund for a year without claims may be worth more."
        )

    @registry.action("reopen")
    def reopen(user: User, params: dict) -> str:
        for c in chosen(user, params):
            run(
                "UPDATE claims SET state = 'open', submitted_on = NULL, reimbursed = NULL, "
                "notice_document_id = NULL WHERE id = :i",
                i=c["id"],
            )
            remind(
                c["id"], c["owner_id"], "open", documents.get(c["document_id"]).title, date.today()
            )
        return "Open again."

    @registry.action("paid_back")
    def paid_back(user: User, params: dict) -> Result:
        """Enter by hand what the insurer paid back for one bill."""
        c = own(user, params.get("claim"))
        try:
            amount = Decimal(str(params.get("amount"))).quantize(Decimal("0.01"))
        except ArithmeticError:
            return Result(errors={"amount": "Enter the amount paid back"})
        run("UPDATE claims SET reimbursed = NULL WHERE id = :i", i=c["id"])
        settle(c, amount, None)
        return Result(message="Saved.")

    @registry.action("match_line")
    def match_line(user: User, params: dict) -> Result:
        line = q(
            "SELECT * FROM unmatched WHERE id = :i AND owner_id = :o",
            i=int(params.get("line") or 0),
            o=user.id,
        )
        if not line:
            return Result(errors={"line": "Choose a line from a statement"})
        c = own(user, params.get("claim"))
        settle(c, line[0]["reimbursed"], line[0]["notice_document_id"])
        run("DELETE FROM unmatched WHERE id = :i", i=line[0]["id"])
        return Result(message="Matched.")

    # 4. Lists ----------------------------------------------------------------------------------

    def rows(user: User) -> list[dict]:
        out = []
        for c in q("SELECT * FROM claims WHERE owner_id = :o ORDER BY id", o=user.id):
            doc = documents.get_for_user(c["document_id"], user)
            billed, when, _ = bill(doc)
            patient = doc.facts.get("patient")
            back = c["reimbursed"]
            own_share = None
            if billed is not None and c["state"] in ("reimbursed", "not_claimed"):
                own_share = billed - (back or Decimal(0))
            out.append(
                c
                | {
                    "title": doc.title or "Medical bill",
                    "from": doc.correspondent or "",
                    "patient": patient.value if patient else "",
                    "treatment_date": when,
                    "billed": billed,
                    "state_label": STATES[c["state"]],
                    "own_share": own_share,
                    "year": str(when.year) if when else "",
                }
            )
        return out

    @registry.data("claims")
    def claims_rows(user: User, params: dict) -> list[dict]:
        return [
            r
            | {
                "billed": money(r["billed"]),
                "reimbursed": money(r["reimbursed"]),
                "own_share": money(r["own_share"]),
            }
            for r in sorted(
                rows(user), key=lambda r: (r["state"] != "open", r["treatment_date"] or date.min)
            )
        ]

    @registry.data("summary")
    def summary(user: User, params: dict) -> list[dict]:
        all_rows, year = rows(user), date.today().year
        this_year = [
            r for r in all_rows if r["treatment_date"] and r["treatment_date"].year == year
        ]

        def total(items: list[dict], field: str) -> Decimal:
            return sum((r[field] or Decimal(0) for r in items), Decimal(0))

        return [
            {
                "label": "To submit",
                "value": money(total([r for r in all_rows if r["state"] == "open"], "billed")),
                "format": "money",
            },
            {
                "label": "Waiting for money",
                "value": money(total([r for r in all_rows if r["state"] == "submitted"], "billed")),
                "format": "money",
            },
            {
                "label": f"Paid back in {year}",
                "value": money(total(this_year, "reimbursed")),
                "format": "money",
            },
            {
                "label": f"Your own share {year}",
                "value": money(total(this_year, "own_share")),
                "format": "money",
            },
        ]

    @registry.data("unmatched")
    def unmatched_rows(user: User, params: dict) -> list[dict]:
        return [
            r | {"billed": money(r["billed"]), "reimbursed": money(r["reimbursed"])}
            for r in q("SELECT * FROM unmatched WHERE owner_id = :o ORDER BY id", o=user.id)
        ]

    @registry.data("line_options")
    def line_options(user: User, params: dict) -> list[dict]:
        return [
            {
                "value": str(r["id"]),
                "label": f"{r['bill_number'] or 'no number'} · {r['treatment_date'] or ''} · "
                f"{r['reimbursed']} € back",
            }
            for r in q("SELECT * FROM unmatched WHERE owner_id = :o ORDER BY id", o=user.id)
        ]

    @registry.data("claim_options")
    def claim_options(user: User, params: dict) -> list[dict]:
        return [
            {
                "value": str(r["id"]),
                "label": f"{r['title']} · {r['treatment_date'] or ''} · {r['billed']} €",
            }
            for r in rows(user)
            if r["state"] in ("open", "submitted")
        ]

    @registry.data("document_claim")
    def document_claim(user: User, params: dict) -> list[dict]:
        doc = documents.get_for_user(params["document_id"], user)
        return [
            {
                "state_label": r["state_label"],
                "submitted_on": r["submitted_on"],
                "reimbursed": money(r["reimbursed"]),
            }
            for r in rows(user)
            if r["document_id"] == doc.id
        ]

    @registry.data("overview")
    def overview(user: User, params: dict) -> list[dict]:
        return summary(user, params)[:2]

    # 5. The tax return and Ask -----------------------------------------------------------------

    @registry.service
    def own_share(user: User, year: int) -> dict:
        """For the tax plugin: health costs you bore yourself in a year (bills settled or kept),
        and how many bills of the year are still open or waiting."""
        in_year = [
            r for r in rows(user) if r["treatment_date"] and r["treatment_date"].year == year
        ]
        settled = [r for r in in_year if r["own_share"] is not None]
        return {
            "own_share": sum((r["own_share"] for r in settled), Decimal(0)),
            "billed": sum((r["billed"] or Decimal(0) for r in in_year), Decimal(0)),
            "still_open": len(in_year) - len(settled),
            "documents": [r["document_id"] for r in settled],
        }

    @registry.tool
    def health_claims(user: User) -> dict:
        """Medical bills still to submit to the health insurer or waiting for money back, and
        what was paid back this year."""
        all_rows = rows(user)
        waiting = [r for r in all_rows if r["state"] in ("open", "submitted")]
        return {
            "waiting": [
                {
                    "title": r["title"],
                    "from": r["from"],
                    "billed": str(r["billed"]),
                    "state": r["state_label"],
                    "since": str(r["submitted_on"] or r["created_at"].date()),
                }
                for r in waiting
            ],
            "documents": [r["document_id"] for r in waiting],
            "summary": f"{len(waiting)} bills to submit or waiting",
        }
