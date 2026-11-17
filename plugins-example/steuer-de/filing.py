"""Tax and bookkeeping for Germany, part 3 without ELSTER software: filing by hand, letters to the
tax office, and the hand-over to a tax advisor.

Filing directly from DocuHive (ELSTER levels 2 and 3) needs the tax administration's library and
a developer registration; until then the person types the figures into Mein ELSTER and uploads
the confirmation here, which closes the loop.
"""

import calendar
import csv
import io
import re
import zipfile
from datetime import date, timedelta
from typing import Any

from docuhive.sdk import (
    ActionError,
    Result,
    User,
    documents,
    guest_links,
    profiles,
    reminders,
    render,
)

LETTERS = {
    "extension": ("letter-extension.html", "Antrag auf Fristverlängerung"),
    "objection": ("letter-objection.html", "Einspruch"),
    "prepayments": ("letter-prepayments.html", "Antrag auf Anpassung der Vorauszahlungen"),
}


def register(
    registry: Any,
    q: Any,
    run: Any,
    book_of: Any,
    period_params: Any,
    figures: Any,
    documents_of: Any,
) -> None:  # noqa: C901
    def identity(user: User, book: dict) -> dict:
        if not book.get("profile_id"):
            raise ActionError("Choose the book's identity first (Tax → Books).")
        return profiles.get(user, book["profile_id"])

    @registry.data("recent_documents")
    def recent_documents(user: User, params: dict) -> list[dict]:
        return [
            {
                "value": d.id,
                "label": f"{d.title or 'Untitled'} ({d.document_date or d.added_at.date()})",
            }
            for d in documents.find(user, limit=200)
        ]

    # Level 1: filed by hand ----------------------------------------------------------------------

    @registry.action("mark_filed")
    def mark_filed(user: User, params: dict) -> Result:
        """The figures were typed into Mein ELSTER; its transfer confirmation is kept and locked."""
        book, key = period_params(user, params)
        book = book_of(user, {"book": book["id"]}, write=True) or book
        if not params.get("confirmation"):
            return Result(
                errors={"confirmation": "Choose the confirmation you saved from Mein ELSTER"}
            )
        saved = q("SELECT * FROM periods WHERE book_id = :b AND key = :k", b=book["id"], k=key)
        if not saved or saved[0]["state"] not in ("closed", "filed"):
            raise ActionError(
                "Close the period first: the figures you filed must not change afterwards."
            )
        doc = documents.get_for_user(params["confirmation"], user)
        filed_on = (
            date.fromisoformat(params["filed_on"]) if params.get("filed_on") else date.today()
        )
        run(
            "UPDATE periods SET state = 'filed', filed_on = :d, filing_document_id = :doc "
            "WHERE book_id = :b AND key = :k",
            d=filed_on,
            doc=doc.id,
            b=book["id"],
            k=key,
        )
        if not any(h["reason"].startswith("Filed") for h in documents.holds(doc.id)):
            from docuhive.sdk import retention

            documents.hold(
                doc.id, f"Filed VAT return {key}", until=retention.until("tax_filing", int(key[:4]))
            )
        reminders.clear(user.id, f"vat:{book['id']}:{key}")
        return Result(message=f"Period {key} is filed. The confirmation is kept with it.")

    @registry.data("payment_reference")
    def payment_reference(user: User, params: dict) -> list[dict]:
        """What to pay, by when, and the reference the tax office expects."""
        book, key = period_params(user, params)
        result = figures(book, key)
        period = key[5:] if "-" in key else "Jahr"
        quarter = {"Q1": "I", "Q2": "II", "Q3": "III", "Q4": "IV"}.get(period, period)
        reference = (
            f"{book.get('tax_number') or 'Steuernummer'} USt {quarter.replace('-', '')} {key[:4]}"
        )
        return [
            {
                "label": "To pay (negative: refund)",
                "value": {"value": result["payable"], "currency": "EUR"},
                "format": "money",
            },
            {
                "label": "Payment reference",
                "value": reference,
                "hint": "Tax number, tax type and period; check it against your tax office's "
                "letters.",
            },
        ]

    # Letters -------------------------------------------------------------------------------------

    @registry.data("letter_kinds")
    def letter_kinds(user: User, params: dict) -> list[dict]:
        return [{"value": k, "label": v[1]} for k, v in LETTERS.items()]

    @registry.action("write_letter")
    def write_letter(user: User, params: dict) -> Result:
        """A letter to the tax office as a document to read, change and send. The plugin fills in
        the formal parts; reasons are yours. Nothing is sent."""
        book = book_of(user, params, write=True)
        if not book:
            raise ActionError("Create a book first.")
        kind = params.get("kind")
        if kind not in LETTERS:
            return Result(errors={"kind": "Choose the letter"})
        if not params.get("office_address"):
            return Result(errors={"office_address": "The tax office's postal address"})
        me = identity(user, book)
        a = me["address"] or {}
        notice_date = (
            date.fromisoformat(params["notice_date"]) if params.get("notice_date") else None
        )
        if kind == "objection" and not notice_date:
            return Result(errors={"notice_date": "The date on the notice"})
        template, subject = LETTERS[kind]
        pdf = render.pdf(
            template,
            {
                "sender_line": f"{me['name']} · {a.get('street', '')} · {a.get('postcode', '')} "
                f"{a.get('city', '')}",
                "recipient": [
                    line for line in str(params["office_address"]).splitlines() if line.strip()
                ],
                "place": a.get("city") or "",
                "date": date.today().strftime("%d.%m.%Y"),
                "subject": f"{subject} – Steuernummer "
                f"{book.get('tax_number') or me.get('tax_number') or '…'}",
                "name": me["name"],
                "tax_type": params.get("tax_type") or "Umsatzsteuer",
                "year": params.get("year") or str(date.today().year - 1),
                "notice_date": notice_date.strftime("%d.%m.%Y") if notice_date else "",
                "until": params.get("until") or "",
            },
        )
        doc_id = documents.create(
            user,
            pdf,
            filename=f"{kind}-{date.today()}.pdf",
            title=f"{subject} ({params.get('year') or ''})".strip(),
            category="finance/tax",
            document_type="letter",
            document_date=date.today(),
        )
        if kind == "objection":
            # A notice counts as received three days after it was posted (AO § 122a, § 122 (2));
            # the objection is due one month after that (AO § 355 (1)). To be confirmed.
            received = notice_date + timedelta(days=3)
            following = date(received.year + received.month // 12, received.month % 12 + 1, 1)
            last = calendar.monthrange(following.year, following.month)[1]
            due = following.replace(day=min(received.day, last))
            reminders.set(
                user.id,
                f"objection:{doc_id}",
                "Deadline for the objection",
                due,
                days_before=[7, 2],
                link=f"/documents/{doc_id}",
            )
        return Result(message="The letter is ready to read and sign.", goto=f"/documents/{doc_id}")

    # Level 4: the advisor ------------------------------------------------------------------------

    @registry.action("advisor_zip")
    def advisor_zip(user: User, params: dict) -> Result:
        """Every booking of the period as CSV, and each booked document as a PDF named by date,
        counterparty and number, with an index linking them."""
        book, key = period_params(user, params)
        rows = q(
            "SELECT * FROM entries WHERE book_id = :b AND period_vat = :k AND state <> 'proposed' "
            "ORDER BY entry_date, id",
            b=book["id"],
            k=key,
        )
        out = io.BytesIO()
        names: dict[str, str] = {}
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for doc_id in documents_of(book, key):
                try:
                    doc = documents.get_for_user(doc_id, user)
                    pdf = documents.archive_pdf(doc_id)
                except documents.NotFound:
                    continue
                number = doc.facts.get("invoice_number")
                stem = re.sub(
                    r"[^\w.-]+",
                    "_",
                    f"{doc.document_date or ''}_{doc.correspondent or ''}_"
                    f"{number.value if number else ''}",
                ).strip("_")
                names[doc_id] = f"documents/{stem or doc_id}_{doc_id[-6:]}.pdf"
                z.writestr(names[doc_id], pdf)
            index = io.StringIO()
            writer = csv.writer(index, delimiter=";")
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
                    "state",
                    "file",
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
                        r["state"],
                        names.get(r["document_id"] or "", ""),
                    ]
                )
            z.writestr("bookings.csv", index.getvalue().encode("utf-8-sig"))
            z.writestr(
                "README.txt",
                (
                    f"Bookings of {key}, book “{book['name']}”, exported {date.today()}.\n"
                    "bookings.csv: one line per booking; 'file' names the document's PDF.\n"
                    "Columns are plain, not the DATEV import format: map them in your software.\n"
                ),
            )
        return Result(download=(f"handover-{key}.zip", out.getvalue(), "application/zip"))

    def advisor_preview(user: User, params: dict) -> dict:
        book, key = period_params(user, params)
        ids = documents_of(book, key)
        return {
            "to": ["anyone holding the link, for 14 days"],
            "subject": f"Read-only access: tax {key}, {book['name']}",
            "body": "The link shows these documents and lets them be downloaded as PDFs. "
            "Every view is recorded; the link stops working by itself after 14 days.",
            "attachments": [documents.get_for_user(i, user).title or i for i in ids],
        }

    @registry.action("advisor_link", outgoing=True, preview=advisor_preview)
    def advisor_link(user: User, params: dict) -> str:
        book, key = period_params(user, params)
        ids = documents_of(book, key)
        if not ids:
            raise ActionError("This period has no documents.")
        made = guest_links.create(
            user,
            f"Tax {key} – {book['name']}",
            ids,
            int(params.get("days") or 14),
            include_private=True,
        )
        until = f"{made['expires_at']:%d.%m.%Y}"
        return f"Give this link to your advisor (valid until {until}): {made['path']}"

    # Procedure documentation ---------------------------------------------------------------------

    @registry.action("procedure")
    def procedure(user: User, params: dict) -> Result:
        """How this installation captures, books and keeps records, for the tax office (GoBD)."""
        book = book_of(user, params)
        if not book:
            raise ActionError("Create a book first.")
        me = identity(user, book)
        pdf = render.pdf(
            "procedure.html",
            {
                "book": book,
                "me": me,
                "today": date.today().strftime("%d.%m.%Y"),
                "vault": "dem Archiv-Speicher dieser Installation",
            },
        )
        doc_id = documents.create(
            user,
            pdf,
            filename=f"procedure-{date.today()}.pdf",
            title=f"Verfahrensdokumentation {book['name']}",
            category="finance/tax",
            document_date=date.today(),
        )
        return Result(
            message="The description is ready. Read it, complete it and keep it.",
            goto=f"/documents/{doc_id}",
        )
