"""Official letters with a deadline to answer, an objection letter, and ID documents.

1. An official notice arrives: the AI reads its date, a printed deadline or the period to answer,
   the reference and the kind. A deadline the letter only states as a period is computed here,
   with the delivery days and weekend and holiday rules in `rules/deadlines.yaml`.
2. The deadline is a value on the document, so DocuHive reminds 14, 7 and 2 days before.
3. The notice page writes an objection (Einspruch or Widerspruch) from your identity, as a draft
   letter in the archive linked to the notice.
4. ID documents: who they belong to and when they run out; DocuHive reminds before they do.
"""

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
    profiles,
    render,
)
from pydantic import BaseModel

from . import deadlines

ANSWERED = "answered"
RENEW_DAYS = 180


class Notice(BaseModel):
    letter_date: date | None = None
    delivered_on: date | None = None
    deadline: date | None = None
    period_amount: int | None = None
    period_unit: Literal["months", "weeks", "days"] | None = None
    reference: str | None = None
    kind: Literal["tax", "fine", "social", "other_authority", "reminder", "other"] | None = None
    amount_due: Decimal | None = None
    currency: str | None = None
    sender_address: list[str] = []


def fact(doc, name: str) -> str | None:  # type: ignore[no-untyped-def]
    value = doc.facts.get(name)
    return value.value if value else None


def setup(registry: Registry) -> None:  # noqa: C901
    rules = lambda: registry.rules("deadlines.yaml")  # noqa: E731
    kinds = lambda: {k["id"]: k for k in rules()["kinds"]}  # noqa: E731

    # 1. Reading a notice -----------------------------------------------------------------------

    def read_notice(document_id: str) -> None:
        doc = documents.get(document_id)
        try:
            n = ai.ask("deadline", Notice, document=doc)
        except ai.Unavailable:
            return  # the person enters the deadline on the document; the reminder still works
        facts: dict[str, FactValue] = {}
        due = n.deadline
        if due is None and n.letter_date and n.period_amount and n.period_unit:
            due = deadlines.respond_by(
                n.letter_date,
                n.period_amount,
                n.period_unit,
                delivery_days=int(rules()["delivery_days"]),
                delivered=n.delivered_on,
            )
        if n.letter_date:
            facts["notice_date"] = FactValue(type="date", value=n.letter_date.isoformat())
        if due:
            facts["respond_by"] = FactValue(type="date", value=due.isoformat())
        if n.reference:
            facts["reference"] = FactValue(type="string", value=n.reference.strip())
        if n.kind:
            facts["notice_kind"] = FactValue(type="string", value=n.kind)
        if n.amount_due is not None:
            facts["amount_due"] = FactValue(
                type="money", value=str(n.amount_due), currency=n.currency or "EUR"
            )
        if n.sender_address:
            address = ", ".join(line.strip() for line in n.sender_address if line.strip())
            facts["authority_address"] = FactValue(type="string", value=address)
        if facts:
            documents.apply_metadata(document_id, facts=facts)

    @registry.on("document.classified")
    def on_classified(event) -> None:  # type: ignore[no-untyped-def]
        if event.document_type == "official_notice":
            read_notice(event.document_id)

    # 2. Lists ----------------------------------------------------------------------------------

    def row(doc) -> dict:  # type: ignore[no-untyped-def]
        due = fact(doc, "respond_by")
        days = (date.fromisoformat(due) - date.today()).days if due else None
        kind = kinds().get(fact(doc, "notice_kind") or "", {})
        amount = doc.facts.get("amount_due")
        return {
            "id": doc.id,
            "title": doc.title or "Untitled letter",
            "from": doc.correspondent or "",
            "kind": kind.get("label", ""),
            "reference": fact(doc, "reference") or "",
            "notice_date": fact(doc, "notice_date"),
            "respond_by": due,
            "state": (
                "Answered"
                if ANSWERED in doc.tags
                else "No date"
                if days is None
                else "Overdue"
                if days < 0
                else "This week"
                if days <= 7
                else "Open"
            ),
            "amount_due": {"value": amount.value, "currency": amount.currency or "EUR"}
            if amount
            else None,
        }

    def notices(user: User) -> list[dict]:
        return [row(d) for d in documents.find(user, document_type="official_notice", limit=500)]

    @registry.data("open_notices")
    def open_notices(user: User, params: dict) -> list[dict]:
        rows = [r for r in notices(user) if r["state"] != "Answered"]
        return sorted(rows, key=lambda r: (r["respond_by"] is None, r["respond_by"] or ""))

    @registry.data("answered_notices")
    def answered_notices(user: User, params: dict) -> list[dict]:
        rows = [r for r in notices(user) if r["state"] == "Answered"]
        return sorted(rows, key=lambda r: r["notice_date"] or "", reverse=True)[:50]

    def notice_of(user: User, params: dict):  # type: ignore[no-untyped-def]
        doc = documents.get_for_user(str(params.get("id") or ""), user)
        if doc.document_type != "official_notice":
            raise ActionError("This document is not an official notice.")
        return doc

    @registry.data("notice")
    def notice(user: User, params: dict) -> dict:
        doc = notice_of(user, params)
        return row(doc) | {"authority_address": fact(doc, "authority_address") or ""}

    @registry.data("is_open")
    def is_open(user: User, params: dict) -> bool:
        return ANSWERED not in notice_of(user, params).tags

    @registry.data("is_answered")
    def is_answered(user: User, params: dict) -> bool:
        return ANSWERED in notice_of(user, params).tags

    @registry.data("can_object")
    def can_object(user: User, params: dict) -> bool:
        doc = notice_of(user, params)
        return ANSWERED not in doc.tags and bool(remedy_of(doc))

    def remedy_of(doc) -> str | None:  # type: ignore[no-untyped-def]
        return kinds().get(fact(doc, "notice_kind") or "other_authority", {}).get("remedy")

    @registry.data("document_notice")
    def document_notice(user: User, params: dict) -> list[dict]:
        doc = documents.get_for_user(params["document_id"], user)
        return [row(doc)] if doc.document_type == "official_notice" else []

    # 3. Answering ------------------------------------------------------------------------------

    @registry.action("answered")
    def answered(user: User, params: dict) -> str:
        doc = notice_of(user, params)
        documents.apply_metadata(doc.id, tags_add=[ANSWERED])
        return "Marked as answered. The reminders stop."

    @registry.action("reopen")
    def reopen(user: User, params: dict) -> str:
        doc = notice_of(user, params)
        documents.apply_metadata(doc.id, tags_remove=[ANSWERED])
        return "Open again."

    @registry.data("profile_options")
    def profile_options(user: User, params: dict) -> list[dict]:
        return [{"value": str(p["id"]), "label": p["name"]} for p in profiles.list(user)]

    @registry.action("objection")
    def objection(user: User, params: dict) -> Result:
        """A draft objection in the archive, linked to the notice. Nothing is sent: check it,
        sign it and post it, or send it through the authority's own portal (ELSTER for tax)."""
        doc = notice_of(user, params)
        remedy = remedy_of(doc)
        if not remedy:
            raise ActionError("This kind of letter has no objection; answer it directly.")
        if not params.get("profile_id"):
            return Result(errors={"profile_id": "Choose who is objecting"})
        address = [
            line.strip()
            for line in str(params.get("authority_address") or "").replace("\n", ",").split(",")
            if line.strip()
        ]
        if not address:
            return Result(errors={"authority_address": "Enter the authority's address"})
        try:
            me = profiles.get(user, int(params["profile_id"]))
        except profiles.NotFound:
            return Result(errors={"profile_id": "Choose one of your identities"})
        a = me["address"] or {}
        if not a.get("street") or not a.get("city"):
            raise ActionError("Add your address to this identity under Settings → Identities.")
        notice_date = fact(doc, "notice_date")
        pdf = render.pdf(
            "objection.html",
            {
                "sender_line": f"{me['name']} · {a['street']} · "
                f"{a.get('postcode', '')} {a['city']}",
                "recipient": address,
                "place": a["city"],
                "date": date.today().strftime("%d.%m.%Y"),
                "name": me["name"],
                "remedy": remedy,
                "kind": fact(doc, "notice_kind") or "other_authority",
                "notice_date": date.fromisoformat(notice_date).strftime("%d.%m.%Y")
                if notice_date
                else "",
                "reference": fact(doc, "reference") or "",
                "tax_number": me.get("tax_number") or "",
                "reasons": str(params.get("reasons") or "").strip(),
                "suspend": bool(params.get("suspend")),
            },
        )
        letter = documents.create(
            user,
            pdf,
            filename=f"{remedy.lower()}-{date.today().isoformat()}.pdf",
            title=f"{remedy}: {doc.title or 'official notice'}"[:120],
            category="government/official",
            derived_from=[doc.id],
            document_date=date.today(),
            correspondent=doc.correspondent,
        )
        return Result(
            message=f"The {remedy} is ready. Check it, sign and post it before "
            f"{row(doc)['respond_by'] or 'the deadline'}, then mark the notice as answered.",
            goto=f"/documents/{letter}",
        )

    # 4. ID documents ---------------------------------------------------------------------------

    @registry.data("id_documents")
    def id_documents(user: User, params: dict) -> list[dict]:
        rows = []
        for d in documents.find(user, document_type="id-document", limit=500):
            until = fact(d, "expiry_date")
            days = (date.fromisoformat(until) - date.today()).days if until else None
            rows.append(
                {
                    "id": d.id,
                    "title": d.title or "ID document",
                    "holder": fact(d, "holder") or "",
                    "expiry_date": until,
                    "state": "No date"
                    if days is None
                    else "Expired"
                    if days < 0
                    else "Renew soon"
                    if days <= RENEW_DAYS
                    else "Valid",
                }
            )
        return sorted(rows, key=lambda r: (r["expiry_date"] is None, r["expiry_date"] or ""))

    # 5. Dashboard and Ask ----------------------------------------------------------------------

    @registry.data("overview")
    def overview(user: User, params: dict) -> list[dict]:
        waiting = [r for r in open_notices(user, params) if r["respond_by"]]
        renew = [r for r in id_documents(user, params) if r["state"] in ("Expired", "Renew soon")]
        out: list[dict] = [
            {"label": "Letters to answer", "value": len(waiting), "format": "number"}
        ]
        if waiting:
            out.append(
                {
                    "label": f"Answer {waiting[0]['from'] or waiting[0]['title']} by",
                    "value": waiting[0]["respond_by"],
                    "format": "date",
                }
            )
        out.append({"label": "ID documents to renew", "value": len(renew), "format": "number"})
        return out

    @registry.tool
    def official_deadlines(user: User) -> dict:
        """Official letters still waiting for an answer, with their deadlines, and ID documents
        that have run out or run out within six months."""
        letters = [r for r in open_notices(user, {}) if r["respond_by"]]
        ids = [r for r in id_documents(user, {}) if r["state"] in ("Expired", "Renew soon")]
        return {
            "letters": [
                {
                    "from": r["from"],
                    "title": r["title"],
                    "respond_by": r["respond_by"],
                    "reference": r["reference"],
                    "kind": r["kind"],
                }
                for r in letters
            ],
            "id_documents": [
                {"title": r["title"], "holder": r["holder"], "expires": r["expiry_date"]}
                for r in ids
            ],
            "documents": [r["id"] for r in letters + ids],
            "summary": f"{len(letters)} letters to answer, {len(ids)} ID documents to renew",
        }
