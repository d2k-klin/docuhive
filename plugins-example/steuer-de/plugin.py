"""Tax and bookkeeping for Germany, part 1: books, receipts in, periods and their figures.

Amounts come from structured e-invoices exactly, or from the AI checked by arithmetic, and a
person confirms every booking. Figures are sums over confirmed bookings. Not tax advice.
"""

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from docuhive.sdk import (
    ActionError,
    FactValue,
    Registry,
    Result,
    User,
    ai,
    documents,
    reminders,
    retention,
    services,
)
from pydantic import BaseModel, Field
from sqlalchemy import text

from . import einvoice, filing, invoices, periods
from .rules import Rules, RulesMissing

INTAKE_TYPES = ("invoice", "receipt")
NOT_ADVICE = "Calculated from your bookings with the rules you chose. This is not tax advice."
CENT = Decimal("0.01")


class Line(BaseModel):
    rate: Decimal
    net: Decimal
    tax: Decimal


class InvoiceFields(BaseModel):
    supplier: str | None = None
    supplier_vat_id: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    service_date: date | None = None
    currency: str = "EUR"
    lines: list[Line] = Field(default_factory=list)
    gross: Decimal
    reverse_charge: bool = False
    small_business: bool = False


class Booking(BaseModel):
    account: str
    reason: str
    confidence: float = Field(ge=0, le=1)


def checked_fields(fields: InvoiceFields) -> InvoiceFields:
    """Net + tax per rate must add up to the total, to the cent, or the reading is refused."""
    if not fields.lines:
        raise ValueError("No VAT lines were read")
    for line in fields.lines:
        if line.rate not in (Decimal(19), Decimal(7), Decimal(0)):
            raise ValueError(f"{line.rate} % is not a German VAT rate")
        expected = (line.net * line.rate / 100).quantize(CENT)
        if abs(expected - line.tax) > CENT:
            raise ValueError(f"tax {line.tax} does not match {line.rate} % of {line.net}")
    if sum((line.net + line.tax for line in fields.lines), Decimal(0)) != fields.gross:
        raise ValueError("the lines do not add up to the total")
    return fields


def normalise(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def vat_code(
    direction: str, rate: Decimal, *, reverse_charge: bool = False, foreign: bool = False
) -> str:
    if direction == "expense":
        if reverse_charge:
            return "purchase_rc_eu" if foreign else "purchase_rc_other"
        return {Decimal(19): "purchase_19", Decimal(7): "purchase_7"}.get(rate, "purchase_none")
    return {Decimal(19): "sale_19", Decimal(7): "sale_7"}.get(rate, "sale_exempt")


def setup(registry: Registry) -> None:  # noqa: C901 - one plugin, many small parts
    rules = Rules(registry)

    def q(sql: str, **params):  # type: ignore[no-untyped-def]
        with registry.db.session() as s:
            return [dict(r) for r in s.execute(text(sql), params).mappings()]

    def run(sql: str, **params) -> int:
        with registry.db.session() as s:
            return s.execute(text(sql), params).rowcount

    # Books -------------------------------------------------------------------------------------

    def books_of(user_id: int) -> list[dict]:
        return q(
            "SELECT b.*, m.role FROM books b JOIN book_members m ON m.book_id = b.id "
            "WHERE m.user_id = :u ORDER BY b.default_for_uploads DESC, b.id",
            u=user_id,
        )

    def book_of(user: User, params: dict, *, write: bool = False) -> dict | None:
        mine = books_of(user.id)
        wanted = str(params.get("book") or "")
        book = next((b for b in mine if str(b["id"]) == wanted), None) if wanted else None
        book = book or (mine[0] if mine else None)
        if book and write and book["role"] not in ("owner", "bookkeeper"):
            raise ActionError("You can look at this book but not change it.")
        return book

    def as_book(row: dict) -> periods.Book:
        return periods.Book(
            id=row["id"],
            kind=row["kind"],
            chart=row["chart"],
            vat_status=row["vat_status"],
            vat_period=row["vat_period"],
            vat_basis=row["vat_basis"],
            standing_extension=row["standing_extension"],
            special_advance=row["special_advance"],
            federal_state=row["federal_state"],
        )

    def as_entry(row: dict) -> periods.Entry:
        return periods.Entry(
            direction=row["direction"],
            entry_date=row["entry_date"],
            net=row["net"],
            vat=row["vat"],
            gross=row["gross"],
            vat_code=row["vat_code"],
            account=row["account"],
            service_date=row["service_date"],
            paid_on=row["paid_on"],
            deductible=row["deductible_fraction"],
            id=row["id"],
            document_id=row["document_id"],
        )

    # Receipts in -------------------------------------------------------------------------------

    def read(doc) -> tuple[list[Line], dict, str, list[str]]:  # type: ignore[no-untyped-def]
        """(VAT lines, details, origin, notes): exact e-invoice data first, then the AI checked by
        arithmetic, then the amounts the archive already read."""
        try:
            invoice = einvoice.find(documents.original(doc.id))
        except documents.NotFound:
            invoice = None
        if invoice is not None:
            lines = [Line(rate=v.rate, net=v.base, tax=v.tax) for v in invoice.vat]
            sign = -1 if invoice.credit_note else 1
            lines = [Line(rate=x.rate, net=sign * x.net, tax=sign * x.tax) for x in lines]
            details = {
                "counterparty": invoice.seller,
                "vat_id": invoice.seller_vat_id,
                "entry_date": invoice.issue_date,
                "service_date": invoice.service_date,
                "reverse_charge": any(v.category == "AE" for v in invoice.vat),
                "number": invoice.number,
            }
            facts = {
                "invoice_number": FactValue(type="string", value=invoice.number),
                "invoice_date": FactValue(type="date", value=invoice.issue_date.isoformat()),
                "amount_total": FactValue(
                    type="money", value=str(invoice.gross), currency=invoice.currency
                ),
                "amount_tax": FactValue(
                    type="money", value=str(invoice.tax), currency=invoice.currency
                ),
                "net_total": FactValue(
                    type="money", value=str(invoice.net), currency=invoice.currency
                ),
            }
            if invoice.service_date:
                facts["service_date"] = FactValue(
                    type="date", value=invoice.service_date.isoformat()
                )
            if invoice.seller_vat_id:
                facts["supplier_vat_id"] = FactValue(type="string", value=invoice.seller_vat_id)
            if invoice.due_date:
                facts["due_date"] = FactValue(type="date", value=invoice.due_date.isoformat())
            documents.apply_metadata(doc.id, facts=facts, correspondent=invoice.seller or None)
            return lines, details, "e_invoice", invoice.problems
        try:
            fields = ai.ask("invoice-fields", InvoiceFields, document=doc, validate=checked_fields)
            details = {
                "counterparty": fields.supplier or doc.correspondent,
                "vat_id": fields.supplier_vat_id,
                "entry_date": fields.invoice_date or doc.document_date,
                "service_date": fields.service_date,
                "reverse_charge": fields.reverse_charge,
                "number": fields.invoice_number,
            }
            return fields.lines, details, "ai", []
        except ai.Unavailable as error:
            notes = [f"The amounts could not be read automatically ({error})."]
        details = {
            "counterparty": doc.correspondent,
            "vat_id": None,
            "entry_date": doc.document_date or doc.added_at.date(),
            "service_date": None,
            "reverse_charge": False,
            "number": None,
        }
        total = doc.facts.get("amount_total")
        if total is None:
            return [], details, "ai", notes + ["No total found: enter the booking by hand."]
        gross = Decimal(total.value)
        tax = Decimal(doc.facts["amount_tax"].value) if "amount_tax" in doc.facts else Decimal(0)
        net = gross - tax
        rate = next(
            (
                r
                for r in (Decimal(19), Decimal(7))
                if net and abs((net * r / 100).quantize(CENT) - tax) <= CENT
            ),
            Decimal(0),
        )
        return [Line(rate=rate, net=net, tax=tax)], details, "ai", notes

    def propose(book: dict, doc, counterparty: str | None) -> tuple[str | None, str]:  # type: ignore[no-untyped-def]
        """(account, why): your rules, your history, known suppliers, then the AI."""
        key = normalise(counterparty)
        if key:
            rule = q(
                "SELECT account FROM booking_rules WHERE book_id = :b AND counterparty = :c",
                b=book["id"],
                c=key,
            )
            if rule:
                run(
                    "UPDATE booking_rules SET uses = uses + 1 WHERE book_id = :b AND counterparty "
                    "= :c",
                    b=book["id"],
                    c=key,
                )
                return rule[0]["account"], "Your rule for this sender"
            history = q(
                "SELECT account FROM entries WHERE book_id = :b AND state <> 'proposed' "
                "AND account IS NOT NULL AND lower(regexp_replace(counterparty, '[^a-zA-Z0-9]', "
                "'', 'g')) = :c "
                "ORDER BY entry_date DESC LIMIT 3",
                b=book["id"],
                c=key,
            )
            if history and len({h["account"] for h in history}) == 1:
                return history[0]["account"], "As before for this sender"
            suppliers = registry.rules("suppliers.yaml")
            for supplier in suppliers["suppliers"]:
                if normalise(supplier["match"]) in key and book["chart"]:
                    return suppliers["kinds"][supplier["kind"]][
                        book["chart"]
                    ], "Usual account for this kind of sender"
        if not book["chart"]:
            return None, ""
        chart = rules.chart(book["chart"])
        expenses = [a for a in chart["accounts"] if a["kind"] == "expense"]

        def known(answer: Booking) -> Booking:
            if answer.account not in {a["id"] for a in expenses}:
                raise ValueError(f"{answer.account} is not one of the listed accounts")
            return answer

        try:
            answer = ai.ask(
                "booking",
                Booking,
                document=doc,
                validate=known,
                variables={
                    "accounts": "\n".join(f"{a['id']} {a['name']}" for a in expenses),
                    "supplier": counterparty or "an unknown sender",
                    "summary": doc.document_type or "document",
                },
            )
        except ai.Unavailable:
            return None, ""
        return answer.account, f"Suggested by the AI: {answer.reason}"

    @registry.on("document.classified")
    def intake(event) -> None:
        if event.document_type in INTAKE_TYPES:
            book_document(event.document_id)

    @registry.job("book")
    def book_later(payload, ctx) -> None:  # type: ignore[no-untyped-def]
        book_document(payload["document_id"])

    def book_document(document_id: str) -> None:
        """Propose bookings for one invoice or receipt in its owner's book, once."""
        doc = documents.get(document_id)
        book = next(
            (
                b
                for b in books_of(doc.owner_id)
                if b["role"] in ("owner", "bookkeeper") and b["kind"] != "private"
            ),
            None,
        )
        if book is None or q(
            "SELECT 1 FROM entries WHERE book_id = :b AND document_id = :d", b=book["id"], d=doc.id
        ):
            return
        lines, details, origin, notes = read(doc)
        account, why = propose(book, doc, details["counterparty"])
        foreign = bool(details["vat_id"]) and not str(details["vat_id"]).upper().startswith("DE")
        if details["reverse_charge"]:
            notes.append("Reverse charge: you owe the VAT. Check the treatment before confirming.")
        if why:
            notes.append(why)
        for number, line in enumerate(
            lines or [Line(rate=Decimal(0), net=Decimal(0), tax=Decimal(0))], start=1
        ):
            code = vat_code(
                "expense", line.rate, reverse_charge=details["reverse_charge"], foreign=foreign
            )
            run(
                "INSERT INTO entries (book_id, document_id, line, direction, entry_date, "
                "service_date, "
                "account, vat_code, net, vat, gross, deductible_fraction, counterparty, state, "
                "origin, note, "
                "created_by) VALUES (:b, :d, :l, 'expense', :ed, :sd, :a, :c, :n, :v, :g, :f, :cp, "
                "'proposed', :o, :note, :by) ON CONFLICT (book_id, document_id, line) DO NOTHING",
                b=book["id"],
                d=doc.id,
                l=number,
                ed=details["entry_date"] or date.today(),
                sd=details["service_date"],
                a=account,
                c=code,
                n=line.net,
                v=line.tax,
                g=line.net + line.tax,
                f=rules.deductible(book["chart"], account),
                cp=(details["counterparty"] or "")[:200] or None,
                o=origin,
                note=" ".join(notes) or None,
                by=f"plugin:{registry.id}",
            )

    @registry.on("document.changed")
    def recheck(event) -> None:
        """A person (or the AI) changed an amount or date: the booking is checked again. Our own
        writes, and invoices issued from these books (which are locked), are not a change."""
        changed = set(event.fields or [])
        if getattr(event, "actor", "") == f"plugin:{registry.id}":
            return
        if changed & {"document_date", "facts.amount_total", "facts.amount_tax", "facts.net_total"}:
            run(
                "UPDATE entries SET state = 'proposed', note = 'The document changed after it was "
                "booked; check it again.' "
                "WHERE document_id = :d AND state = 'confirmed' AND origin <> 'invoice'",
                d=event.document_id,
            )

    @registry.on("bank.matched")
    def paid(event) -> None:
        run(
            "UPDATE entries SET paid_on = :p WHERE document_id = :d AND state <> 'closed' AND "
            "paid_on IS NULL",
            p=date.fromisoformat(event.date),
            d=event.document_id,
        )
        for row in q(
            "SELECT e.*, b.vat_period, b.vat_status, b.vat_basis, b.kind, b.chart, "
            "b.standing_extension, "
            "b.special_advance, b.federal_state FROM entries e JOIN books b ON b.id = e.book_id "
            "WHERE e.document_id = :d AND e.state = 'confirmed'",
            d=event.document_id,
        ):
            assign(row, row)

    def assign(entry_row: dict, book_row: dict) -> None:
        entry, book = as_entry(entry_row), as_book(book_row)
        run(
            "UPDATE entries SET period_vat = :pv, period_year = :py WHERE id = :i",
            pv=periods.vat_period(book, entry),
            py=periods.income_year(entry),
            i=entry.id,
        )

    # Confirming --------------------------------------------------------------------------------

    def confirm(
        user: User,
        book: dict,
        entry_id: int,
        account: str | None,
        code: str | None,
        paid_on: date | None,
        remember: bool,
    ) -> str:
        rows = q("SELECT * FROM entries WHERE id = :i AND book_id = :b", i=entry_id, b=book["id"])
        if not rows:
            raise ActionError("This booking is not in your book.")
        row = rows[0]
        if row["state"] == "closed":
            raise ActionError("This booking is in a closed period and cannot change.")
        account = account or row["account"]
        code = code or row["vat_code"]
        chart_account = rules.account(book["chart"], account)
        if book["chart"] and chart_account is None:
            raise ActionError("Choose an account from your chart of accounts.")
        codes = rules.vat_codes()
        if code not in codes:
            raise ActionError("Choose a VAT treatment.")
        if codes[code]["direction"] != ("purchases" if row["direction"] == "expense" else "sales"):
            raise ActionError("That VAT treatment is for the other direction (sales or purchases).")
        if paid_on is None and services.available("bank.payments_for") and row["document_id"]:
            payments = services.get("bank.payments_for")(row["document_id"])
            paid_on = payments[-1]["date"] if payments else None
        run(
            "UPDATE entries SET account = :a, vat_code = :c, paid_on = coalesce(:p, paid_on), "
            "deductible_fraction = :f, state = 'confirmed', confirmed_by = :by, confirmed_at = :at "
            "WHERE id = :i",
            a=account,
            c=code,
            p=paid_on,
            f=rules.deductible(book["chart"], account),
            by=f"user:{user.id}",
            at=datetime.now(UTC),
            i=entry_id,
        )
        assign(q("SELECT * FROM entries WHERE id = :i", i=entry_id)[0], book)
        if remember and row["counterparty"]:
            run(
                "INSERT INTO booking_rules (book_id, counterparty, account, vat_code) VALUES (:b, "
                ":c, :a, :v) "
                "ON CONFLICT (book_id, counterparty) DO UPDATE SET account = :a, vat_code = :v",
                b=book["id"],
                c=normalise(row["counterparty"]),
                a=account,
                v=code,
            )
        return "Booked." + (
            " From now on this sender is booked like this."
            if remember and row["counterparty"]
            else ""
        )

    # Figures -----------------------------------------------------------------------------------

    def period_entries(book: dict, key: str) -> list[periods.Entry]:
        rows = q(
            "SELECT * FROM entries WHERE book_id = :b AND state IN ('confirmed', 'closed') "
            "AND (period_vat = :k OR (length(:k) = 4 AND period_vat LIKE :k || '%'))",
            b=book["id"],
            k=key,
        )
        return [as_entry(r) for r in rows]

    def figures(book: dict, key: str) -> dict:
        saved = q("SELECT * FROM periods WHERE book_id = :b AND key = :k", b=book["id"], k=key)
        if saved and saved[0]["state"] in ("closed", "filed"):
            return saved[0]["figures"] | {
                "state": saved[0]["state"],
                "rules_version": saved[0]["rules_version"],
            }
        year = rules.year(int(key[:4]))
        result = periods.vat_figures(
            as_book(book), period_entries(book, key), rules.vat_codes(), year["forms"]["ustva"], key
        )
        result["state"] = saved[0]["state"] if saved else "open"
        result["rules_version"] = rules.version(int(key[:4]))
        return result

    def missing(user: User, book: dict, key: str) -> list[dict]:
        start, end = periods.bounds(key)
        items: list[dict] = []
        proposed = q(
            "SELECT count(*) AS n FROM entries WHERE book_id = :b AND state = 'proposed' "
            "AND entry_date BETWEEN :s AND :e",
            b=book["id"],
            s=start,
            e=end,
        )[0]["n"]
        if proposed:
            items.append(
                {
                    "label": f"{proposed} bookings to confirm",
                    "state": "problem",
                    "link": "/plugins/steuer-de/inbox",
                }
            )
        booked = {
            r["document_id"]
            for r in q("SELECT DISTINCT document_id FROM entries WHERE book_id = :b", b=book["id"])
        }
        for doc in documents.find(
            user, document_type=list(INTAKE_TYPES), date_from=start, date_to=end, limit=500
        ):
            if doc.id not in booked:
                items.append(
                    {
                        "label": f"Not booked: {doc.title or 'a document'}",
                        "state": "problem",
                        "link": f"/documents/{doc.id}",
                    }
                )
        stale = q(
            "SELECT count(*) AS n FROM entries WHERE book_id = :b AND state = 'confirmed' AND "
            "paid_on IS NULL "
            "AND entry_date < :old AND entry_date BETWEEN :s AND :e",
            b=book["id"],
            old=date.today() - timedelta(days=60),
            s=start,
            e=end,
        )[0]["n"]
        if stale:
            items.append(
                {"label": f"{stale} bookings unpaid for more than 60 days", "state": "todo"}
            )
        # ponytail: payments without a receipt are the bank plugin's inbox; linked, not recounted
        if services.available("bank.payments_for"):
            items.append(
                {
                    "label": "Payments without a document are listed by the bank plugin",
                    "state": "todo",
                    "link": "/plugins/bank/inbox",
                }
            )
        try:
            if not rules.year(start.year).get("reviewed"):
                items.append(
                    {
                        "label": f"The rules for {start.year} have not been reviewed by a tax "
                        f"advisor yet",
                        "state": "todo",
                    }
                )
        except RulesMissing as error:
            items.append({"label": str(error), "state": "problem"})
        return items

    def period_keys(book: dict) -> list[str]:
        keys = {
            r["period_vat"]
            for r in q(
                "SELECT DISTINCT period_vat FROM entries WHERE book_id = :b AND period_vat IS NOT "
                "NULL",
                b=book["id"],
            )
        }
        keys |= {
            r["key"]
            for r in q(
                "SELECT key FROM periods WHERE book_id = :b AND key NOT LIKE 'EUER%'", b=book["id"]
            )
        }
        if as_book(book).files_vat:
            keys.add(periods.key(book["vat_period"], date.today()))
        return sorted(keys, reverse=True)

    # Deadlines ---------------------------------------------------------------------------------

    @registry.every(timedelta(days=1), "deadlines")
    def deadlines(payload, ctx) -> None:
        for book in q(
            "SELECT b.*, m.user_id FROM books b JOIN book_members m ON m.book_id = b.id AND m.role "
            "= 'owner'"
        ):
            if not as_book(book).files_vat:
                continue
            today = date.today()
            current = periods.key(book["vat_period"], today)
            previous = periods.key(
                book["vat_period"], periods.bounds(current)[0] - timedelta(days=1)
            )
            for key in (previous, current):
                filed = q(
                    "SELECT 1 FROM periods WHERE book_id = :b AND key = :k AND state = 'filed'",
                    b=book["id"],
                    k=key,
                )
                name = f"vat:{book['id']}:{key}"
                if filed:
                    reminders.clear(book["user_id"], name)
                    continue
                try:
                    year = rules.year(int(key[:4]))
                except RulesMissing:
                    continue
                due = periods.due_date(as_book(book), key, year["advance_return"])
                reminders.set(
                    book["user_id"],
                    name,
                    f"VAT advance return {key} ({book['name']})",
                    due,
                    days_before=[7, 1],
                    link=f"/plugins/steuer-de/period?book={book['id']}&key={key}",
                )

    def vat_label(row: dict) -> dict:
        code = rules.vat_codes().get(row.get("vat_code") or "")
        row["vat_label"] = code["label"] if code else row.get("vat_code")
        return row

    # Screens: data -----------------------------------------------------------------------------

    @registry.data("books")
    def books_rows(user: User, params: dict) -> list[dict]:
        return books_of(user.id)

    @registry.data("book_options")
    def book_options(user: User, params: dict) -> list[dict]:
        return [{"value": "", "label": "A new book"}] + [
            {"value": str(b["id"]), "label": b["name"]}
            for b in books_of(user.id)
            if b["role"] == "owner"
        ]

    def choices(*pairs: str) -> list[dict]:
        return [{"value": pairs[i], "label": pairs[i + 1]} for i in range(0, len(pairs), 2)]

    @registry.data("kinds")
    def kinds(user: User, params: dict) -> list[dict]:
        return choices(
            "euer",
            "Self-employed or business, income-surplus accounting (EÜR)",
            "hand_over",
            "Company with a tax advisor: prepare and hand over",
            "private",
            "Household: receipts for the private return",
        )

    @registry.data("charts")
    def charts(user: User, params: dict) -> list[dict]:
        return choices("skr03", "SKR03", "skr04", "SKR04")

    @registry.data("vat_statuses")
    def vat_statuses(user: User, params: dict) -> list[dict]:
        return choices(
            "regular",
            "Regular VAT",
            "small_business",
            "Small-business rule (§ 19 UStG)",
            "exempt",
            "VAT-exempt activity",
        )

    @registry.data("vat_periods")
    def vat_periods(user: User, params: dict) -> list[dict]:
        return choices(
            "monthly",
            "Monthly",
            "quarterly",
            "Quarterly",
            "yearly",
            "Yearly return only",
            "none",
            "No VAT returns",
        )

    @registry.data("vat_bases")
    def vat_bases(user: User, params: dict) -> list[dict]:
        return choices("invoice", "When invoiced (Soll)", "payment", "When paid (Ist)")

    @registry.data("proposals")
    def proposals(user: User, params: dict) -> list[dict]:
        book = book_of(user, params)
        if not book:
            return []
        rows = q(
            "SELECT * FROM entries WHERE book_id = :b AND state = 'proposed' ORDER BY entry_date",
            b=book["id"],
        )
        for r in rows:
            try:
                r["title"] = (
                    documents.get_for_user(r["document_id"], user).title
                    if r["document_id"]
                    else "Manual booking"
                )
            except documents.NotFound:
                r["title"] = None
            r["amount"] = {"value": r["gross"], "currency": "EUR"}
        return [vat_label(r) for r in rows if r["title"] is not None]

    @registry.data("proposal_options")
    def proposal_options(user: User, params: dict) -> list[dict]:
        return [
            {
                "value": str(r["id"]),
                "label": f"{r['entry_date']:%d.%m.%Y} {r['counterparty'] or r['title'] or ''} "
                f"{r['gross']} €",
            }
            for r in proposals(user, params)
        ]

    @registry.data("accounts")
    def accounts(user: User, params: dict) -> list[dict]:
        book = book_of(user, params)
        if not book or not book["chart"]:
            return []
        return [
            {"value": a["id"], "label": f"{a['id']} {a['name']}"}
            for a in rules.chart(book["chart"])["accounts"]
        ]

    @registry.data("directions")
    def directions(user: User, params: dict) -> list[dict]:
        return choices("expense", "Expense (money out)", "income", "Income (money in)")

    @registry.data("vat_code_options")
    def vat_code_options(user: User, params: dict) -> list[dict]:
        return [{"value": c["id"], "label": c["label"]} for c in rules.vat_codes().values()]

    @registry.data("entries")
    def entries_rows(user: User, params: dict) -> list[dict]:
        book = book_of(user, params)
        if not book:
            return []
        rows = q(
            "SELECT * FROM entries WHERE book_id = :b ORDER BY entry_date DESC, id DESC",
            b=book["id"],
        )
        for r in rows:
            vat_label(r)
            r["state_label"] = {
                "proposed": "To confirm",
                "confirmed": "Booked",
                "closed": "Closed",
            }[r["state"]]
        return rows

    @registry.data("periods")
    def periods_rows(user: User, params: dict) -> list[dict]:
        book = book_of(user, params)
        if not book:
            return []
        out = []
        for key in period_keys(book):
            try:
                result = figures(book, key)
                due = periods.due_date(
                    as_book(book), key, rules.year(int(key[:4]))["advance_return"]
                )
            except RulesMissing:
                continue
            out.append(
                {
                    "key": key,
                    "book": str(book["id"]),
                    "payable": {"value": result["payable"], "currency": "EUR"},
                    "due": due,
                    "state": {
                        "open": "Open",
                        "checked": "Checked",
                        "closed": "Closed",
                        "filed": "Filed",
                    }[result["state"]],
                }
            )
        return out

    def period_params(user: User, params: dict) -> tuple[dict, str]:
        book = book_of(user, params)
        if not book:
            raise ActionError("Create a book first.")
        key = str(params.get("key") or periods.key(book["vat_period"], date.today()))
        if not re.fullmatch(r"\d{4}(-Q[1-4]|-\d{2})?", key):
            raise ActionError("That is not a period.")
        return book, key

    @registry.data("period_summary")
    def period_summary(user: User, params: dict) -> list[dict]:
        book, key = period_params(user, params)
        result = figures(book, key)
        due = periods.due_date(as_book(book), key, rules.year(int(key[:4]))["advance_return"])
        return [
            {
                "label": f"Period {key}",
                "value": {
                    "open": "Open",
                    "checked": "Checked",
                    "closed": "Closed",
                    "filed": "Filed",
                }[result["state"]],
            },
            {
                "label": "Amount due (negative: refund)",
                "value": {"value": result["payable"], "currency": "EUR"},
                "format": "money",
            },
            {"label": "Due", "value": due, "format": "date"},
            {"label": "Rules", "value": result["rules_version"], "hint": NOT_ADVICE},
        ]

    @registry.data("period_fields")
    def period_fields(user: User, params: dict) -> list[dict]:
        book, key = period_params(user, params)
        return [
            {
                **f,
                "value": {"value": f["value"], "currency": "EUR"},
                "tax": {"value": f["tax"], "currency": "EUR"} if f["tax"] is not None else None,
            }
            for f in figures(book, key)["fields"]
        ]

    @registry.data("period_missing")
    def period_missing(user: User, params: dict) -> list[dict]:
        book, key = period_params(user, params)
        return missing(user, book, key)

    @registry.data("year_statement")
    def year_statement(user: User, params: dict) -> list[dict]:
        book = book_of(user, params)
        if not book or not book["chart"]:
            return []
        year = int(params.get("year") or date.today().year)
        rows = q(
            "SELECT * FROM entries WHERE book_id = :b AND state IN ('confirmed', 'closed') AND "
            "period_year = :y",
            b=book["id"],
            y=year,
        )
        result = periods.income_statement(
            [as_entry(r) for r in rows],
            rules.chart(book["chart"]),
            rules.vat_codes(),
            rules.year(year)["euer"],
        )
        out = [
            {
                "label": p["label"],
                "side": "Income" if p["side"] == "income" else "Expenses",
                "amount": {"value": p["amount"], "currency": "EUR"},
            }
            for p in result["positions"]
        ]
        out.append(
            {
                "label": "Surplus (income minus expenses)",
                "side": "Result",
                "amount": {"value": result["surplus"], "currency": "EUR"},
            }
        )
        if result["not_deductible"]:
            out.append(
                {
                    "label": "Not deductible (shown for information)",
                    "side": "Note",
                    "amount": {"value": result["not_deductible"], "currency": "EUR"},
                }
            )
        return [r | {"year": year} for r in out]

    @registry.data("private_receipts")
    def private_receipts(user: User, params: dict) -> list[dict]:
        year = int(params.get("year") or date.today().year)
        out = []
        for section in registry.rules("private-tags.yaml")["sections"]:
            for doc in documents.find(user, tags=[section["tag"]], year=year):
                total = doc.facts.get("amount_total")
                out.append(
                    {
                        "section": section["label"],
                        "id": doc.id,
                        "title": doc.title or "Untitled",
                        "document_date": doc.document_date,
                        "amount": {"value": total.value, "currency": total.currency or "EUR"}
                        if total
                        else None,
                    }
                )
        return out

    @registry.data("rules_rows")
    def rules_rows(user: User, params: dict) -> list[dict]:
        book = book_of(user, params)
        return [
            vat_label(r)
            for r in (
                q(
                    "SELECT * FROM booking_rules WHERE book_id = :b ORDER BY counterparty",
                    b=book["id"],
                )
                if book
                else []
            )
        ]

    @registry.data("overview")
    def overview(user: User, params: dict) -> list[dict]:
        book = book_of(user, params)
        if not book:
            return [{"label": "No book yet", "value": "Create one under Tax → Books"}]
        to_confirm = len(proposals(user, params))
        out = [{"label": "Bookings to confirm", "value": to_confirm, "format": "number"}]
        if as_book(book).files_vat:
            key = periods.key(book["vat_period"], date.today())
            try:
                result = figures(book, key)
                due = periods.due_date(
                    as_book(book), key, rules.year(int(key[:4]))["advance_return"]
                )
                out += [
                    {
                        "label": f"VAT {key} so far",
                        "value": {"value": result["payable"], "currency": "EUR"},
                        "format": "money",
                    },
                    {"label": "Due", "value": due, "format": "date"},
                ]
            except RulesMissing:
                pass
        if book["vat_status"] == "small_business":
            out += small_business_watch(book, date.today().year)
        overdue = q(
            "SELECT count(*) AS n FROM invoices WHERE book_id = :b AND due_date < :t "
            "AND state IN ('issued', 'sent', 'partly_paid')",
            b=book["id"],
            t=date.today() - timedelta(days=14),
        )[0]["n"]
        if overdue:
            out.append(
                {
                    "label": "Invoices more than 14 days overdue",
                    "value": overdue,
                    "format": "number",
                }
            )
        return out

    def turnover(book: dict, year: int) -> Decimal:
        return q(
            "SELECT coalesce(sum(net), 0) AS t FROM entries WHERE book_id = :b "
            "AND direction = 'income' AND state <> 'proposed' "
            "AND extract(year FROM entry_date) = :y",
            b=book["id"],
            y=year,
        )[0]["t"]

    def small_business_watch(book: dict, year: int) -> list[dict]:
        """Turnover against the small-business limits. It explains; it does not decide."""
        try:
            limits = rules.year(year)["small_business"]
        except RulesMissing:
            return []
        now, before = turnover(book, year), turnover(book, year - 1)
        current, prior = Decimal(limits["current_year_limit"]), Decimal(limits["prior_year_limit"])
        hint = f"Limits: {prior} last year, {current} this year ({limits['source']})."
        if now > current:
            hint = (
                f"Your turnover passed {current}: from the invoice that crossed it, the "
                "small-business rule no longer applies. Talk to your tax advisor now."
            )
        elif before > prior:
            hint = (
                f"Last year's turnover was above {prior}: the small-business rule may not apply "
                "this year. Check with your tax advisor."
            )
        elif now >= current * Decimal("0.8"):
            hint = f"You have used 80 % of this year's limit of {current}. {hint}"
        return [
            {
                "label": f"Turnover {year} (small-business rule)",
                "value": {"value": now, "currency": "EUR"},
                "format": "money",
                "hint": hint,
            }
        ]

    @registry.data("document_entries")
    def document_entries(user: User, params: dict) -> list[dict]:
        doc = documents.get_for_user(params["document_id"], user)
        mine = {b["id"]: b for b in books_of(user.id)}
        if not mine:
            return []
        rows = q(
            "SELECT * FROM entries WHERE document_id = :d AND book_id = ANY(:b) ORDER BY line",
            d=doc.id,
            b=list(mine),
        )
        for r in rows:
            r["book_name"] = mine[r["book_id"]]["name"]
            vat_label(r)
            r["state_label"] = {
                "proposed": "To confirm",
                "confirmed": "Booked",
                "closed": "Closed",
            }[r["state"]]
        return rows

    # Screens: actions --------------------------------------------------------------------------

    @registry.action("save_book")
    def save_book(user: User, params: dict) -> Result:
        name = str(params.get("name") or "").strip()
        values = {
            "kind": params.get("kind") or "euer",
            "chart": params.get("chart") or None,
            "vat_status": params.get("vat_status") or "regular",
            "vat_period": params.get("vat_period") or "quarterly",
            "vat_basis": params.get("vat_basis") or "invoice",
            "ext": bool(params.get("standing_extension")),
            "adv": Decimal(str(params.get("special_advance") or 0)),
            "tax": params.get("tax_number") or None,
            "vat_id": params.get("vat_id") or None,
            "default": bool(params.get("default_for_uploads")),
            "profile": int(params["profile_id"]) if params.get("profile_id") else None,
        }
        if values["kind"] != "private" and not values["chart"]:
            return Result(
                errors={"chart": "Choose the chart of accounts (your advisor knows which)"}
            )
        if values["kind"] == "private":
            values.update(chart=None, vat_status="exempt", vat_period="none")
        existing = (
            book_of(user, {"book": params.get("book")}, write=True) if params.get("book") else None
        )
        if existing and existing["role"] != "owner":
            raise ActionError("Only the book's owner can change its settings.")
        if values["default"]:
            run(
                "UPDATE books SET default_for_uploads = false WHERE id IN (SELECT book_id FROM "
                "book_members WHERE user_id = :u)",
                u=user.id,
            )
        if existing:
            run(
                "UPDATE books SET name = coalesce(nullif(:n, ''), name), kind = :kind, chart = "
                ":chart, "
                "vat_status = :vat_status, vat_period = :vat_period, vat_basis = :vat_basis, "
                "standing_extension = :ext, special_advance = :adv, tax_number = :tax, vat_id = "
                ":vat_id, "
                "default_for_uploads = :default OR default_for_uploads, "
                "profile_id = coalesce(:profile, profile_id) WHERE id = :id",
                n=name,
                id=existing["id"],
                **values,
            )
            return Result(message="Saved.")
        if not name:
            return Result(errors={"name": "Give the book a name"})
        first = not books_of(user.id)
        with registry.db.session() as s:
            book_id = s.execute(
                text(
                    "INSERT INTO books (owner_id, name, kind, chart, vat_status, vat_period, "
                    "vat_basis, "
                    "standing_extension, special_advance, tax_number, vat_id, default_for_uploads, "
                    "profile_id) "
                    "VALUES (:u, :n, :kind, :chart, :vat_status, :vat_period, :vat_basis, :ext, "
                    ":adv, :tax, "
                    ":vat_id, :default, :profile) RETURNING id"
                ),
                {"u": user.id, "n": name, **values, "default": values["default"] or first},
            ).scalar_one()
            s.execute(
                text("INSERT INTO book_members (book_id, user_id, role) VALUES (:b, :u, 'owner')"),
                {"b": book_id, "u": user.id},
            )
        registry.enqueue("deadlines", {})
        return Result(
            message=f"Book “{name}” created. New invoices and receipts are booked into it."
        )

    @registry.action("confirm_entry")
    def confirm_entry(user: User, params: dict) -> Result:
        book = book_of(user, params, write=True)
        if not book:
            raise ActionError("Create a book first.")
        if not params.get("entry"):
            return Result(errors={"entry": "Choose the booking"})
        paid = params.get("paid_on")
        message = confirm(
            user,
            book,
            int(params["entry"]),
            params.get("account") or None,
            params.get("vat_code") or None,
            date.fromisoformat(paid) if paid else None,
            bool(params.get("always")),
        )
        return Result(message=message)

    @registry.action("confirm_as_proposed")
    def confirm_as_proposed(user: User, params: dict) -> str:
        book = book_of(user, params, write=True)
        if not book:
            raise ActionError("Create a book first.")
        return confirm(user, book, int(params["id"]), None, None, None, False)

    @registry.action("close_period")
    def close_period(user: User, params: dict) -> str:
        book, key = period_params(user, params)
        book = book_of(user, {"book": book["id"]}, write=True) or book
        if book["kind"] == "hand_over":
            raise ActionError(
                "This book is prepared for your tax advisor, who closes the periods in their "
                "own software. Download the bookings under Bookings and hand them over."
            )
        result = figures(book, key)
        if result["state"] in ("closed", "filed"):
            raise ActionError("This period is already closed.")
        start, end = periods.bounds(key)
        open_items = [i for i in missing(user, book, key) if i["state"] == "problem"]
        if open_items:
            raise ActionError(
                "Finish these first: " + "; ".join(i["label"] for i in open_items[:3])
            )
        stored = {k: v for k, v in result.items() if k not in ("state", "rules_version")}
        with registry.db.session() as s:
            s.execute(
                text(
                    "INSERT INTO periods (book_id, key, state, rules_version, figures, closed_by, "
                    "closed_at) "
                    "VALUES (:b, :k, 'closed', :r, CAST(:f AS jsonb), :by, :at) ON CONFLICT "
                    "(book_id, key) "
                    "DO UPDATE SET state = 'closed', figures = EXCLUDED.figures, rules_version = "
                    "EXCLUDED.rules_version, "
                    "closed_by = EXCLUDED.closed_by, closed_at = EXCLUDED.closed_at"
                ),
                {
                    "b": book["id"],
                    "k": key,
                    "r": result["rules_version"],
                    "f": _json(stored),
                    "by": f"user:{user.id}",
                    "at": datetime.now(UTC),
                },
            )
            s.execute(
                text(
                    "UPDATE entries SET state = 'closed' WHERE book_id = :b AND state = "
                    "'confirmed' AND period_vat = :k"
                ),
                {"b": book["id"], "k": key},
            )
        # Every receipt and invoice of the period stays as it was for the retention period.
        until = retention.until("booking_document", start.year)
        for doc_id in documents_of(book, key):
            if not any(h["reason"].startswith("Booked in") for h in documents.holds(doc_id)):
                documents.hold(doc_id, f"Booked in the closed VAT period {key}", until=until)
        return (
            f"Period {key} is closed. Its bookings can no longer change; corrections go into a "
            f"later period."
        )

    @registry.action("book_missing")
    def book_missing(user: User, params: dict) -> str:
        """Documents that arrived before the book existed, or while the plugin was off."""
        book, key = period_params(user, params)
        start, end = periods.bounds(key)
        booked = {
            r["document_id"]
            for r in q("SELECT DISTINCT document_id FROM entries WHERE book_id = :b", b=book["id"])
        }
        waiting = [
            d.id
            for d in documents.find(
                user, document_type=list(INTAKE_TYPES), date_from=start, date_to=end, limit=500
            )
            if d.id not in booked and d.owner_id == user.id
        ]
        for doc_id in waiting:
            registry.enqueue("book", {"document_id": doc_id}, dedupe_key=doc_id)
        if not waiting:
            return "Every invoice and receipt of this period is booked or proposed."
        return f"{len(waiting)} documents are being read; their bookings appear under Tax inbox."

    @registry.action("add_entry")
    def add_entry(user: User, params: dict) -> Result:
        """A booking without a document: a cash sale, a bank fee, an invoice written elsewhere."""
        book = book_of(user, params, write=True)
        if not book:
            raise ActionError("Create a book first.")
        errors = {
            k: "Required"
            for k in ("direction", "entry_date", "gross", "vat_code")
            if not params.get(k)
        }
        if errors:
            return Result(errors=errors)
        codes = rules.vat_codes()
        code = codes.get(str(params["vat_code"]))
        direction = str(params["direction"])
        if code is None or code["direction"] != (
            "purchases" if direction == "expense" else "sales"
        ):
            return Result(errors={"vat_code": "Choose a VAT treatment for this direction"})
        gross = Decimal(str(params["gross"])).quantize(CENT)
        rate = Decimal(str(code["rate"]))
        if code.get("reverse_charge"):
            net, vat = gross, Decimal(0)  # the invoice shows no VAT; the return adds it
        else:
            net = (gross * 100 / (100 + rate)).quantize(CENT)
            vat = gross - net
        account = params.get("account") or None
        if book["chart"] and rules.account(book["chart"], account) is None:
            return Result(errors={"account": "Choose an account"})
        paid = params.get("paid_on")
        with registry.db.session() as s:
            entry_id = s.execute(
                text(
                    "INSERT INTO entries (book_id, direction, entry_date, service_date, paid_on, "
                    "account, "
                    "vat_code, net, vat, gross, deductible_fraction, counterparty, state, origin, "
                    "created_by, "
                    "confirmed_by, confirmed_at) VALUES (:b, :d, :ed, :ed, :p, :a, :c, :n, :v, :g, "
                    ":f, :cp, "
                    "'confirmed', 'manual', :by, :by, :at) RETURNING id"
                ),
                {
                    "b": book["id"],
                    "d": direction,
                    "ed": date.fromisoformat(str(params["entry_date"])),
                    "p": date.fromisoformat(str(paid)) if paid else None,
                    "a": account,
                    "c": code["id"],
                    "n": net,
                    "v": vat,
                    "g": net + vat,
                    "f": rules.deductible(book["chart"], account),
                    "cp": params.get("counterparty") or None,
                    "by": f"user:{user.id}",
                    "at": datetime.now(UTC),
                },
            ).scalar_one()
        assign(q("SELECT * FROM entries WHERE id = :i", i=entry_id)[0], book)
        return Result(message=f"Booked: {net} net + {vat} VAT.")

    @registry.action("export_entries", destructive=False)
    def export_entries(user: User, params: dict) -> Result:
        """Every confirmed booking of a year as CSV, for a tax advisor's software or a spreadsheet.
        ponytail: plain CSV, not the DATEV import format; add that when an advisor asks for it."""
        import csv
        import io

        book = book_of(user, params)
        if not book:
            raise ActionError("Create a book first.")
        year = int(params.get("year") or date.today().year)
        rows = q(
            "SELECT * FROM entries WHERE book_id = :b AND state <> 'proposed' "
            "AND extract(year FROM entry_date) = :y ORDER BY entry_date, id",
            b=book["id"],
            y=year,
        )
        out = io.StringIO()
        writer = csv.writer(out, delimiter=";")
        writer.writerow(
            [
                "date",
                "direction",
                "counterparty",
                "account",
                "vat_code",
                "net",
                "vat",
                "gross",
                "paid_on",
                "document",
                "state",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r["entry_date"],
                    r["direction"],
                    r["counterparty"] or "",
                    r["account"] or "",
                    r["vat_code"] or "",
                    r["net"],
                    r["vat"],
                    r["gross"],
                    r["paid_on"] or "",
                    r["document_id"] or "",
                    r["state"],
                ]
            )
        name = re.sub(r"[^A-Za-z0-9_-]+", "-", book["name"]).strip("-") or "book"
        return Result(
            download=(f"{name}-{year}.csv", out.getvalue().encode("utf-8-sig"), "text/csv")
        )

    @registry.action("delete_rule", destructive=True)
    def delete_rule(user: User, params: dict) -> str:
        book = book_of(user, params, write=True)
        run(
            "DELETE FROM booking_rules WHERE id = :i AND book_id = :b",
            i=int(params["id"]),
            b=book["id"] if book else 0,
        )
        return "The rule is gone; new documents from this sender are proposed again."

    # Ask -----------------------------------------------------------------------------------------

    def documents_of(book: dict, key: str) -> list[str]:
        return [
            r["document_id"]
            for r in q(
                "SELECT DISTINCT document_id FROM entries WHERE book_id = :b AND period_vat = :k "
                "AND document_id IS NOT NULL",
                b=book["id"],
                k=key,
            )
        ]

    @registry.tool
    def vat_return(user: User, year: int, period: str = "", exclude_ids: set | None = None) -> dict:
        """The VAT advance return figures for a period, from your confirmed bookings.

        Args:
            year: the year, such as 2026
            period: "Q1"…"Q4" or a month "03"; empty for the whole year
        """
        book = book_of(user, {})
        if not book:
            return {"documents": [], "summary": "No book yet"}
        key = f"{year}" + (
            f"-{period}" if period.startswith("Q") else f"-{int(period):02d}" if period else ""
        )
        result = figures(book, key)
        docs = documents_of(book, key) if len(key) > 4 else []
        if exclude_ids and set(docs) & exclude_ids:
            return {
                "documents": [],
                "summary": "Some bookings are on private documents; ask with a local model",
            }
        return {
            "period": key,
            "amount_due": str(result["payable"]),
            "fields": {f["field"]: str(f["value"]) for f in result["fields"]},
            "documents": docs,
            "note": NOT_ADVICE,
            "summary": f"VAT {key}: {result['payable']} EUR due",
        }

    @registry.tool
    def income_surplus(user: User, year: int) -> dict:
        """Income, expenses and surplus for a year (income-surplus accounting, EÜR).

        Args:
            year: the year, such as 2026
        """
        rows = year_statement(user, {"year": year})
        return {
            "positions": {r["label"]: str(r["amount"]["value"]) for r in rows},
            "documents": [],
            "note": NOT_ADVICE,
            "summary": f"{len(rows)} positions",
        }

    @registry.tool
    def open_items(user: User) -> dict:
        """Bookings still to confirm, and confirmed ones not paid yet."""
        book = book_of(user, {})
        if not book:
            return {"documents": [], "summary": "No book yet"}
        to_confirm = q(
            "SELECT count(*) AS n FROM entries WHERE book_id = :b AND state = 'proposed'",
            b=book["id"],
        )[0]["n"]
        unpaid = q(
            "SELECT counterparty, gross, entry_date, document_id FROM entries WHERE book_id = :b "
            "AND state = 'confirmed' AND paid_on IS NULL",
            b=book["id"],
        )
        return {
            "to_confirm": to_confirm,
            "unpaid": [
                {
                    "from": u["counterparty"],
                    "amount": str(u["gross"]),
                    "date": u["entry_date"].isoformat(),
                }
                for u in unpaid
            ],
            "documents": [u["document_id"] for u in unpaid if u["document_id"]],
            "summary": f"{to_confirm} to confirm, {len(unpaid)} unpaid",
        }

    invoices.register(registry, rules, q, run, book_of, assign)
    filing.register(registry, q, run, book_of, period_params, figures, documents_of)


def _json(value: object) -> str:
    import json

    def default(v: object) -> object:
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, date):
            return v.isoformat()
        raise TypeError(type(v).__name__)

    return json.dumps(value, default=default)
