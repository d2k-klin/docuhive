"""Tax and bookkeeping for Germany, part 2: your own invoices.

A draft can change freely. Issuing gives it the next number, prints the PDF and the e-invoice
from the same data, reads its own output back to the cent, stores it locked in the archive and
books it. After that nothing changes except its state, payments and sending; a mistake is
corrected with a credit note. Nothing is ever sent without a person's click.
"""

import hashlib
import io
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from docuhive.sdk import ActionError, Result, User, documents, mail, profiles, render, retention
from sqlalchemy import text

from . import einvoice

CENT = Decimal("0.01")
TYPE_CODES = {"invoice": "380", "credit_note": "381"}
SERIES = {"invoice": "RE", "credit_note": "GS", "quote": "AN"}
UNITS = {
    "C62": "Stück / piece",
    "HUR": "Stunde / hour",
    "DAY": "Tag / day",
    "MON": "Monat / month",
    "KMT": "km",
    "LS": "pauschal / lump sum",
}


class IssueRefused(ActionError):
    """Pre-issue checks failed; every problem is listed for the person."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("This invoice cannot be issued yet: " + " ".join(problems))
        self.problems = problems


# Calculation (Decimal only) --------------------------------------------------------------------


def line_net(quantity: Decimal, unit_price: Decimal, discount: Decimal) -> Decimal:
    return (quantity * unit_price * (100 - discount) / 100).quantize(CENT, ROUND_HALF_UP)


def net_price(unit_price: Decimal, discount: Decimal) -> Decimal:
    return (unit_price * (100 - discount) / 100).normalize()


def totals(lines: list[dict], codes: dict[str, dict]) -> dict:
    """VAT is calculated once per VAT treatment on the sum of its lines, as EN 16931 checks it."""
    groups: dict[str, Decimal] = {}
    for line in lines:
        groups[line["vat_code"]] = groups.get(line["vat_code"], Decimal(0)) + line["net"]
    breakdown = []
    for code, base in groups.items():
        rate = Decimal(str(codes[code]["rate"]))
        breakdown.append(
            {
                "code": code,
                "category": codes[code].get("category", "S"),
                "rate": rate,
                "base": base,
                "tax": (base * rate / 100).quantize(CENT, ROUND_HALF_UP),
            }
        )
    net = sum((b["base"] for b in breakdown), Decimal(0))
    tax = sum((b["tax"] for b in breakdown), Decimal(0))
    return {"breakdown": breakdown, "net": net, "tax": tax, "gross": net + tax}


def number(pattern: str, seq: int, year: int) -> str:
    return pattern.format(seq=seq, year=year)


# Checks: one rule, one message --------------------------------------------------------------------


def checks(
    inv: dict, lines: list[dict], seller: dict, buyer: dict, book: dict, codes: dict[str, dict]
) -> list[str]:
    problems = []

    def need(ok: object, message: str) -> None:
        if not ok:
            problems.append(message)

    need(
        seller.get("name") and seller.get("street") and seller.get("city"),
        "Your name and address are missing: choose an identity for the book.",
    )
    if inv["kind"] != "quote":
        need(
            seller.get("tax_number") or seller.get("vat_id"),
            "An invoice needs your tax number or VAT id (Settings → Identities).",
        )
    need(
        buyer.get("name") and (buyer.get("city") or inv["gross_estimate"] <= Decimal("250")),
        "The customer's name and address are missing.",
    )
    need(lines, "Add at least one line.")
    for line in lines:
        need(
            line["description"] and line["quantity"] and line["unit_price"] is not None,
            f"Line {line['position']} needs a description, a quantity and a price.",
        )
        code = codes.get(line["vat_code"])
        need(
            code and code["direction"] == "sales", f"Line {line['position']} needs a VAT treatment."
        )
        if book["vat_status"] == "small_business":
            need(
                line["vat_code"] == "sale_small_business",
                "Under the small-business rule every line uses “Sale under the small-business "
                "rule”.",
            )
        if code and code.get("needs_vat_ids"):
            need(
                buyer.get("vat_id") and seller.get("vat_id"),
                "Reverse charge and EU supplies need both VAT ids on the invoice.",
            )
    need(
        inv["service_from"] or inv["service_to"] or inv["kind"] == "quote",
        "Enter the date or period of the service.",
    )
    if inv["kind"] == "credit_note":
        need(inv["refers_to_invoice_id"], "A credit note refers to an issued invoice.")
    if buyer.get("e_invoice_format") == "xrechnung":
        need(buyer.get("routing_id"), "XRechnung needs the customer's routing id (Leitweg-ID).")
        need(seller.get("iban"), "XRechnung needs your bank account (Settings → Identities).")
        need(
            buyer.get("email"),
            "XRechnung needs the customer's mail address (their electronic address).",
        )
        need(
            seller.get("phone") and seller.get("email"),
            "XRechnung needs your phone number and mail address (Settings → Identities).",
        )
    if buyer.get("country", "DE") != "DE" and buyer.get("kind") == "consumer":
        problems.append(
            "Invoices to consumers in other countries may need the EU one-stop shop; "
            "this plugin does not handle that."
        )
    return problems


# The plugin's part --------------------------------------------------------------------------------


def register(registry: Any, rules: Any, q: Any, run: Any, book_of: Any, assign: Any) -> None:  # noqa: C901
    texts = lambda: registry.rules("invoice-texts.yaml")  # noqa: E731

    def seller_of(user: User, book: dict) -> dict:
        if not book.get("profile_id"):
            return {}
        try:
            p = profiles.get(user, book["profile_id"])
        except profiles.NotFound:
            return {}
        a, bank = p["address"] or {}, p["bank"] or {}
        return {
            "name": p["name"],
            "street": a.get("street"),
            "postcode": a.get("postcode"),
            "city": a.get("city"),
            "country": a.get("country") or "DE",
            "email": p["email"],
            "phone": p["phone"],
            "vat_id": p["vat_id"] or book.get("vat_id"),
            "tax_number": p["tax_number"] or book.get("tax_number"),
            "iban": bank.get("iban"),
            "bic": bank.get("bic"),
            "bank": bank.get("name"),
            "website": p["website"],
        }

    def invoice(user: User, invoice_id: object, *, write: bool = False) -> tuple[dict, dict]:
        rows = q("SELECT * FROM invoices WHERE id = :i", i=int(invoice_id or 0))
        book = book_of(user, {"book": rows[0]["book_id"]}, write=write) if rows else None
        if not rows or not book or book["id"] != rows[0]["book_id"]:
            raise ActionError("This invoice is not in your books.")
        return rows[0], book

    def lines_of(invoice_id: int) -> list[dict]:
        return q(
            "SELECT * FROM invoice_lines WHERE invoice_id = :i ORDER BY position", i=invoice_id
        )

    def customer(customer_id: int) -> dict:
        return q("SELECT * FROM customers WHERE id = :i", i=customer_id)[0]

    # Drafts --------------------------------------------------------------------------------------

    @registry.action("save_customer")
    def save_customer(user: User, params: dict) -> Result:
        book = book_of(user, params, write=True)
        if not book:
            raise ActionError("Create a book first.")
        if not str(params.get("name") or "").strip():
            return Result(errors={"name": "Name the customer"})
        fields = (
            "name",
            "street",
            "postcode",
            "city",
            "country",
            "email",
            "vat_id",
            "routing_id",
            "kind",
            "e_invoice_format",
            "payment_terms_days",
            "language",
        )
        values = {f: params.get(f) or None for f in fields}
        values["country"] = (values["country"] or "DE").upper()
        values["kind"] = values["kind"] or "business"
        values["e_invoice_format"] = values["e_invoice_format"] or "zugferd"
        values["payment_terms_days"] = int(values["payment_terms_days"] or 14)
        values["language"] = values["language"] or "de"
        values = {
            k: ("" if v is None and k in ("street", "postcode", "city") else v)
            for k, v in values.items()
        }
        if params.get("customer"):
            run(
                "UPDATE customers SET "
                + ", ".join(f"{f} = :{f}" for f in fields)
                + " WHERE id = :id AND book_id = :b",
                **values,
                id=int(params["customer"]),
                b=book["id"],
            )
            return Result(message="Customer saved.")
        run(
            "INSERT INTO customers (book_id, "
            + ", ".join(fields)
            + ") VALUES (:b, "
            + ", ".join(f":{f}" for f in fields)
            + ")",
            **values,
            b=book["id"],
        )
        return Result(message=f"Customer “{values['name']}” added.")

    @registry.action("save_draft")
    def save_draft(user: User, params: dict) -> Result:
        """Create or change a draft. Lines come from the form's `lines` field."""
        book = book_of(user, params, write=True)
        if not book:
            raise ActionError("Create a book first.")
        if not params.get("customer_id"):
            return Result(errors={"customer_id": "Choose the customer"})
        kind = params.get("kind") or "invoice"
        dates = {
            k: date.fromisoformat(params[k]) if params.get(k) else None
            for k in ("service_from", "service_to")
        }
        lines = []
        for n, raw in enumerate(params.get("lines") or [], start=1):
            if not any(str(v).strip() for v in raw.values()):
                continue
            try:
                lines.append(
                    {
                        "position": n,
                        "description": str(raw.get("description") or "").strip(),
                        "quantity": Decimal(str(raw.get("quantity") or "1")),
                        "unit": raw.get("unit") or "C62",
                        "unit_price": Decimal(str(raw.get("unit_price") or "0")),
                        "discount_percent": Decimal(str(raw.get("discount_percent") or "0")),
                        "vat_code": raw.get("vat_code")
                        or (
                            "sale_small_business"
                            if book["vat_status"] == "small_business"
                            else "sale_19"
                        ),
                        "account": raw.get("account") or None,
                    }
                )
            except ArithmeticError:
                return Result(errors={"lines": f"Line {n}: quantity and price must be numbers"})
        with registry.db.session() as s:
            if params.get("invoice"):
                current, _ = invoice(user, params["invoice"], write=True)
                if current["number"]:
                    raise ActionError(
                        "An issued invoice cannot be changed. Cancel it with a credit note."
                    )
                invoice_id = current["id"]
                s.execute(
                    text(
                        "UPDATE invoices SET customer_id = :c, service_from = :sf, "
                        "service_to = :st, notes = :n, recurring_months = :r WHERE id = :i"
                    ),
                    {
                        "c": int(params["customer_id"]),
                        "sf": dates["service_from"],
                        "st": dates["service_to"],
                        "n": params.get("notes") or None,
                        "r": int(params["recurring_months"])
                        if params.get("recurring_months")
                        else None,
                        "i": invoice_id,
                    },
                )
                s.execute(
                    text("DELETE FROM invoice_lines WHERE invoice_id = :i"), {"i": invoice_id}
                )
            else:
                invoice_id = s.execute(
                    text(
                        "INSERT INTO invoices (book_id, customer_id, kind, service_from, "
                        "service_to, "
                        "notes, recurring_months, refers_to_invoice_id) VALUES (:b, :c, :k, :sf, "
                        ":st, :n, "
                        ":r, :ref) RETURNING id"
                    ),
                    {
                        "b": book["id"],
                        "c": int(params["customer_id"]),
                        "k": kind,
                        "sf": dates["service_from"],
                        "st": dates["service_to"],
                        "n": params.get("notes") or None,
                        "ref": params.get("refers_to") or None,
                        "r": int(params["recurring_months"])
                        if params.get("recurring_months")
                        else None,
                    },
                ).scalar_one()
            for line in lines:
                s.execute(
                    text(
                        "INSERT INTO invoice_lines (invoice_id, position, description, "
                        "quantity, unit, unit_price, discount_percent, vat_code, account) "
                        "VALUES (:i, :position, :description, :quantity, :unit, :unit_price, "
                        ":discount_percent, :vat_code, :account)"
                    ),
                    line | {"i": invoice_id},
                )
        return Result(message="Draft saved.", goto=f"invoice?id={invoice_id}")

    @registry.action("save_quote")
    def save_quote(user: User, params: dict) -> Result:
        return save_draft(user, params | {"kind": "quote"})

    @registry.action("delete_draft", destructive=True)
    def delete_draft(user: User, params: dict) -> Result:
        current, _ = invoice(user, params.get("id"), write=True)
        if current["number"]:
            raise ActionError("Issued invoices are kept; cancel it with a credit note instead.")
        run("DELETE FROM invoices WHERE id = :i", i=current["id"])
        return Result(message="Draft deleted.", goto="invoices")

    # Issuing -------------------------------------------------------------------------------------

    def model(
        inv: dict,
        lines: list[dict],
        calc: dict,
        seller: dict,
        buyer: dict,
        language: str,
        refers: dict | None,
    ) -> dict:
        codes = rules.vat_codes()
        reasons = {
            b["code"]: texts()["texts"][codes[b["code"]]["text"]][language]
            for b in calc["breakdown"]
            if codes[b["code"]].get("text")
        }
        labels = texts()["labels"][language]
        return {
            "number": inv["number"],
            "type_code": TYPE_CODES.get(inv["kind"], "380"),
            "issue_date": inv["issue_date"],
            "currency": "EUR",
            "seller": seller,
            "buyer": buyer,
            "service_from": inv["service_from"],
            "service_to": inv["service_to"] or inv["service_from"],
            "due_date": inv["due_date"],
            "payment_text": labels["due"].format(due=inv["due_date"].strftime("%d.%m.%Y"))
            if inv["due_date"]
            else None,
            "lines": [
                line
                | {
                    "net_price": net_price(line["unit_price"], line["discount_percent"]),
                    "category": rules.vat_codes()[line["vat_code"]].get("category", "S"),
                    "rate": Decimal(str(rules.vat_codes()[line["vat_code"]]["rate"])),
                }
                for line in lines
            ],
            "breakdown": [b | {"reason": reasons.get(b["code"])} for b in calc["breakdown"]],
            "net": calc["net"],
            "tax": calc["tax"],
            "gross": calc["gross"],
            "refers_to": refers,
            "notes": [n for n in [inv.get("notes"), *reasons.values()] if n],
            "labels": labels,
            "units": UNITS,
            "kind": inv["kind"],
        }

    def zugferd(pdf: bytes, xml: bytes) -> bytes:
        """The XML inside the PDF, with the XMP block that says it is there (Factur-X 1.0)."""
        import pikepdf

        data = render.attach(pdf, "factur-x.xml", xml, relationship="Alternative")
        with pikepdf.open(io.BytesIO(data)) as document:
            with document.open_metadata(set_pikepdf_as_editor=False) as meta:
                meta.register_xml_namespace(
                    "urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#", "fx"
                )
                meta["fx:DocumentType"] = "INVOICE"
                meta["fx:DocumentFileName"] = "factur-x.xml"
                meta["fx:Version"] = "1.0"
                meta["fx:ConformanceLevel"] = "EN 16931"
            out = io.BytesIO()
            document.save(out)
        return out.getvalue()

    def self_check(produced: bytes, model_: dict) -> None:
        """Read our own output back with the reader for incoming invoices: equal to the cent."""
        read = (
            einvoice.find(produced)
            if produced.startswith(b"%PDF")
            else einvoice.parse_xml(produced)
        )
        if read is None or read.problems:
            raise ActionError(f"The e-invoice did not pass its own check: {read and read.problems}")
        if (read.number, read.net, read.tax, read.gross) != (
            model_["number"],
            model_["net"],
            model_["tax"],
            model_["gross"],
        ):
            raise ActionError("The e-invoice does not match the invoice; nothing was issued.")

    @registry.action("issue")
    def issue(user: User, params: dict) -> Result:
        draft, book = invoice(user, params.get("id"), write=True)
        if draft["number"]:
            raise ActionError("This invoice is already issued.")
        lines = lines_of(draft["id"])
        for line in lines:
            line["net"] = line_net(line["quantity"], line["unit_price"], line["discount_percent"])
        codes = rules.vat_codes()
        calc = totals(lines, codes)
        buyer_row = customer(draft["customer_id"])
        buyer = {
            k: buyer_row[k]
            for k in (
                "name",
                "street",
                "postcode",
                "city",
                "country",
                "email",
                "vat_id",
                "routing_id",
                "kind",
                "e_invoice_format",
            )
        }
        seller = seller_of(user, book)
        refers = None
        if draft["refers_to_invoice_id"]:
            original = q(
                "SELECT number, issue_date, customer_id FROM invoices WHERE id = :i",
                i=draft["refers_to_invoice_id"],
            )
            if (
                not original
                or not original[0]["number"]
                or original[0]["customer_id"] != draft["customer_id"]
            ):
                raise IssueRefused(
                    ["A credit note refers to an issued invoice of the same customer."]
                )
            refers = {"number": original[0]["number"], "issue_date": original[0]["issue_date"]}
        problems = checks(
            draft | {"gross_estimate": calc["gross"]}, lines, seller, buyer, book, codes
        )
        if problems:
            raise IssueRefused(problems)
        language = buyer_row["language"] if buyer_row["language"] in ("de", "en") else "de"
        today = date.today()
        series = SERIES[draft["kind"]]
        with registry.db.session() as s:
            # The series row stays locked until the invoice is stored: two people issuing at once
            # get consecutive numbers, and a failed issue leaves no gap.
            s.execute(
                text(
                    "INSERT INTO number_series (book_id, series, year) VALUES (:b, :s, :y) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"b": book["id"], "s": series, "y": today.year},
            )
            row = (
                s.execute(
                    text(
                        "SELECT * FROM number_series WHERE book_id = :b AND series = :s FOR UPDATE"
                    ),
                    {"b": book["id"], "s": series},
                )
                .mappings()
                .one()
            )
            seq = 1 if row["reset"] == "yearly" and row["year"] != today.year else row["next_seq"]
            inv = draft | {
                "number": f"{series}-{number(row['pattern'], seq, today.year)}",
                "issue_date": today,
                "due_date": today + timedelta(days=buyer_row["payment_terms_days"])
                if draft["kind"] != "quote"
                else None,
            }
            m = model(inv, lines, calc, seller, buyer, language, refers)
            pdf = render.pdf("invoice.html", m, pdfa=draft["kind"] != "quote")
            xml = None
            stored = pdf
            if draft["kind"] != "quote" and buyer["e_invoice_format"] != "pdf_only":
                flavour = "xrechnung" if buyer["e_invoice_format"] == "xrechnung" else "zugferd"
                xml = einvoice.write_cii(m, flavour)
                stored = zugferd(pdf, xml)
                self_check(stored, m)
            title = f"{m['labels'][draft['kind']]} {inv['number']} {buyer['name']}"
            doc_id = documents.create(
                user,
                stored,
                document_date=today,
                correspondent=buyer["name"],
                filename=f"{inv['number']}.pdf",
                title=title,
                document_type="outgoing_invoice" if draft["kind"] != "quote" else "quote",
                facts={
                    "invoice_number": {"type": "string", "value": inv["number"]},
                    "invoice_date": {"type": "date", "value": today.isoformat()},
                    "amount_total": {
                        "type": "money",
                        "value": str(calc["gross"]),
                        "currency": "EUR",
                    },
                    "amount_tax": {"type": "money", "value": str(calc["tax"]), "currency": "EUR"},
                    **(
                        {"due_date": {"type": "date", "value": inv["due_date"].isoformat()}}
                        if inv["due_date"]
                        else {}
                    ),
                },
            )
            for line in lines:
                s.execute(
                    text("UPDATE invoice_lines SET net = :n WHERE id = :i"),
                    {"n": line["net"], "i": line["id"]},
                )
            s.execute(
                text(
                    "UPDATE invoices SET series = :s, number = :n, issue_date = :d, due_date = "
                    ":due, "
                    "state = 'issued', customer_snapshot = CAST(:c AS jsonb), seller_snapshot = "
                    "CAST(:se AS jsonb), net = :net, vat = :vat, gross = :g, vat_breakdown = "
                    "CAST(:vb AS jsonb), document_id = :doc, xml_sha256 = :x, issued_by = :by, "
                    "issued_at = :at WHERE id = :i"
                ),
                {
                    "s": series,
                    "n": inv["number"],
                    "d": today,
                    "due": inv["due_date"],
                    "c": _json(buyer),
                    "se": _json(seller),
                    "net": calc["net"],
                    "vat": calc["tax"],
                    "g": calc["gross"],
                    "vb": _json(calc["breakdown"]),
                    "doc": doc_id,
                    "x": hashlib.sha256(xml).hexdigest() if xml else None,
                    "by": f"user:{user.id}",
                    "at": datetime.now(UTC),
                    "i": draft["id"],
                },
            )
            s.execute(
                text(
                    "UPDATE number_series SET next_seq = :n, year = :y WHERE book_id = :b "
                    "AND series = :s"
                ),
                {"n": seq + 1, "y": today.year, "b": book["id"], "s": series},
            )
            if draft["kind"] != "quote":
                sign = -1 if draft["kind"] == "credit_note" else 1
                for position, part in enumerate(calc["breakdown"], start=1):
                    accounts = [
                        ln["account"]
                        for ln in lines
                        if ln["vat_code"] == part["code"] and ln["account"]
                    ]
                    account = max(set(accounts), key=accounts.count) if accounts else None
                    s.execute(
                        text(
                            "INSERT INTO entries (book_id, document_id, line, direction, "
                            "entry_date, "
                            "service_date, account, vat_code, net, vat, gross, counterparty, "
                            "state, "
                            "origin, created_by, confirmed_by, confirmed_at) VALUES (:b, :d, :l, "
                            "'income', "
                            ":ed, :sd, :a, :c, :n, :v, :g, :cp, 'confirmed', 'invoice', :by, :by, "
                            ":at)"
                        ),
                        {
                            "b": book["id"],
                            "d": doc_id,
                            "l": position,
                            "ed": today,
                            "sd": inv["service_to"] or inv["service_from"] or today,
                            "a": account or default_account(book, part["code"]),
                            "c": part["code"],
                            "n": sign * part["base"],
                            "v": sign * part["tax"],
                            "g": sign * (part["base"] + part["tax"]),
                            "cp": buyer["name"][:200],
                            "by": f"user:{user.id}",
                            "at": datetime.now(UTC),
                        },
                    )
            if draft["refers_to_invoice_id"] and draft["kind"] == "credit_note":
                s.execute(
                    text("UPDATE invoices SET state = 'cancelled' WHERE id = :i"),
                    {"i": draft["refers_to_invoice_id"]},
                )
        for entry in q("SELECT * FROM entries WHERE document_id = :d", d=doc_id):
            assign(entry, book)
        if draft["kind"] != "quote":
            documents.hold(
                doc_id,
                f"Issued: {m['labels'][draft['kind']]} {inv['number']}",
                until=retention.until("booking_document", today.year),
            )
        return Result(message=f"Issued as {inv['number']}.", goto=f"invoice?id={draft['id']}")

    def default_account(book: dict, code: str) -> str | None:
        if not book["chart"]:
            return None
        return next(
            (
                a["id"]
                for a in rules.chart(book["chart"])["accounts"]
                if a["kind"] == "income" and a.get("vat") == code
            ),
            None,
        )

    # After issuing -------------------------------------------------------------------------------

    def invoice_mail(user: User, params: dict) -> dict:
        """What sending this invoice would send: shown first, then sent exactly so."""
        inv, book = invoice(user, params.get("id"), write=True)
        if not inv["number"] or not inv["document_id"]:
            raise ActionError("Issue the invoice first.")
        if not book.get("profile_id"):
            raise ActionError("Choose the book's identity first (Tax → Books).")
        buyer = inv["customer_snapshot"]
        to = params.get("to") or buyer.get("email")
        if not to:
            raise ActionError("Enter the customer's mail address.")
        language = customer(inv["customer_id"])["language"]
        body = render.text(
            f"mail-invoice.{language if language in ('de', 'en') else 'de'}.txt",
            {"invoice": inv, "customer": buyer},
        )
        label = texts()["labels"]["de" if language != "en" else "en"][inv["kind"]]
        return {
            "to": [to],
            "subject": f"{label} {inv['number']}",
            "body": body,
            "attachments": [f"{inv['number']}.pdf"],
            "invoice": inv,
            "book": book,
        }

    def invoice_preview(user: User, params: dict) -> dict:
        m = invoice_mail(user, params)
        return {k: m[k] for k in ("to", "subject", "body", "attachments")}

    @registry.action("send_invoice", outgoing=True, preview=invoice_preview)
    def send_invoice(user: User, params: dict) -> str:
        m = invoice_mail(user, params)
        inv, to = m["invoice"], m["to"][0]
        mail.send(
            user, m["book"]["profile_id"], m["to"], m["subject"], m["body"], [inv["document_id"]]
        )
        run(
            "UPDATE invoices SET state = CASE WHEN state = 'issued' THEN 'sent' ELSE state END, "
            "sent_at = :at, sent_to = :to WHERE id = :i",
            at=datetime.now(UTC),
            to=to,
            i=inv["id"],
        )
        return f"Sent to {to}. The mail is kept with the invoice."

    @registry.action("mark_sent")
    def mark_sent(user: User, params: dict) -> str:
        inv, _ = invoice(user, params.get("id"), write=True)
        if not inv["number"]:
            raise ActionError("Issue the invoice first.")
        run(
            "UPDATE invoices SET state = CASE WHEN state = 'issued' THEN 'sent' ELSE state END, "
            "sent_at = :at, sent_to = 'by post or portal' WHERE id = :i",
            at=datetime.now(UTC),
            i=inv["id"],
        )
        return "Marked as sent."

    def settle(invoice_id: int) -> None:
        inv = q("SELECT * FROM invoices WHERE id = :i", i=invoice_id)[0]
        paid = q(
            "SELECT coalesce(sum(amount), 0) AS p, max(paid_on) AS d FROM invoice_payments "
            "WHERE invoice_id = :i",
            i=invoice_id,
        )[0]
        if inv["state"] in ("cancelled", "written_off"):
            return
        state = (
            "paid"
            if paid["p"] >= inv["gross"]
            else "partly_paid"
            if paid["p"] > 0
            else inv["state"]
        )
        run("UPDATE invoices SET state = :s WHERE id = :i", s=state, i=invoice_id)
        if state == "paid":  # income-surplus and payment-basis periods count from here
            run(
                "UPDATE entries SET paid_on = :d WHERE document_id = :doc AND paid_on IS NULL "
                "AND state <> 'closed'",
                d=paid["d"],
                doc=inv["document_id"],
            )
            book = q("SELECT * FROM books WHERE id = :b", b=inv["book_id"])[0]
            for entry in q(
                "SELECT * FROM entries WHERE document_id = :d AND state = 'confirmed'",
                d=inv["document_id"],
            ):
                assign(entry, book)

    @registry.action("record_payment")
    def record_payment(user: User, params: dict) -> Result:
        inv, _ = invoice(user, params.get("id"), write=True)
        if not inv["number"]:
            raise ActionError("Only issued invoices are paid.")
        if not params.get("amount") or not params.get("paid_on"):
            return Result(errors={"amount": "Enter the amount and the date"})
        run(
            "INSERT INTO invoice_payments (invoice_id, paid_on, amount, note) VALUES (:i, :d, :a, "
            ":n)",
            i=inv["id"],
            d=date.fromisoformat(params["paid_on"]),
            a=Decimal(str(params["amount"])),
            n=params.get("note") or None,
        )
        settle(inv["id"])
        return Result(message="Payment recorded.")

    @registry.on("bank.matched")
    def matched(event) -> None:  # type: ignore[no-untyped-def]
        for inv in q(
            "SELECT id FROM invoices WHERE document_id = :d AND number IS NOT NULL",
            d=event.document_id,
        ):
            run(
                "INSERT INTO invoice_payments (invoice_id, paid_on, amount, transaction_id) VALUES "
                "(:i, :d, :a, :t) ON CONFLICT DO NOTHING",
                i=inv["id"],
                d=date.fromisoformat(event.date),
                a=abs(Decimal(event.amount)),
                t=event.transaction_id,
            )
            settle(inv["id"])

    @registry.action("payment_reminder")
    def payment_reminder(user: User, params: dict) -> Result:
        """The next reminder letter as a document; post it or send it. Never automatic."""
        inv, book = invoice(user, params.get("id"), write=True)
        if inv["state"] not in ("issued", "sent", "partly_paid") or not inv["due_date"]:
            raise ActionError("Only unpaid issued invoices get reminders.")
        sent = q(
            "SELECT * FROM payment_reminders WHERE invoice_id = :i ORDER BY level", i=inv["id"]
        )
        level = len(sent) + 1
        wait = registry.rules("payment-reminders.yaml")
        if level > 3:
            raise ActionError("Three reminders were sent. Talk to the customer or a lawyer.")
        last = sent[-1]["sent_on"] if sent else inv["due_date"]
        if date.today() < last + timedelta(days=wait["days_between"]):
            raise ActionError(f"Wait until {last + timedelta(days=wait['days_between']):%d.%m.%Y}.")
        paid = q(
            "SELECT coalesce(sum(amount), 0) AS p FROM invoice_payments WHERE invoice_id = :i",
            i=inv["id"],
        )[0]["p"]
        seller = inv["seller_snapshot"]
        pdf = render.pdf(
            f"reminder-{level}.html",
            {
                "invoice": inv,
                "open": inv["gross"] - paid,
                "seller": seller,
                "sender_line": f"{seller['name']} · {seller['street']} · {seller['postcode']} "
                f"{seller['city']}",
                "recipient": [
                    x
                    for x in (
                        inv["customer_snapshot"]["name"],
                        inv["customer_snapshot"]["street"],
                        f"{inv['customer_snapshot']['postcode']} "
                        f"{inv['customer_snapshot']['city']}",
                    )
                    if x.strip()
                ],
                "place": seller["city"],
                "date": date.today().strftime("%d.%m.%Y"),
                "subject": f"Zahlungserinnerung zur Rechnung {inv['number']}"
                if level == 1
                else f"{level}. Mahnung zur Rechnung {inv['number']}",
            },
        )
        doc_id = documents.create(
            user,
            pdf,
            filename=f"reminder-{level}-{inv['number']}.pdf",
            title=f"Reminder {level}: {inv['number']}",
            document_type="letter",
            derived_from=[inv["document_id"]],
        )
        run(
            "INSERT INTO payment_reminders (invoice_id, level, document_id, sent_on) VALUES "
            "(:i, :l, :d, :s)",
            i=inv["id"],
            l=level,
            d=doc_id,
            s=date.today(),
        )
        return Result(message=f"Reminder {level} is ready.", goto=f"/documents/{doc_id}")

    @registry.action("credit_note")
    def credit_note(user: User, params: dict) -> Result:
        """Cancel an issued invoice: a credit note with the same lines, as a draft to issue."""
        inv, book = invoice(user, params.get("id"), write=True)
        if inv["kind"] != "invoice" or not inv["number"] or inv["state"] == "cancelled":
            raise ActionError("Only an issued, not yet cancelled invoice can be cancelled.")
        lines = [
            {
                k: str(v) if v is not None else ""
                for k, v in line.items()
                if k
                in (
                    "description",
                    "quantity",
                    "unit",
                    "unit_price",
                    "discount_percent",
                    "vat_code",
                    "account",
                )
            }
            for line in lines_of(inv["id"])
        ]
        return save_draft(
            user,
            {
                "book": book["id"],
                "customer_id": inv["customer_id"],
                "kind": "credit_note",
                "refers_to": inv["id"],
                "lines": lines,
                "service_from": inv["service_from"] and inv["service_from"].isoformat(),
                "service_to": inv["service_to"] and inv["service_to"].isoformat(),
                "notes": f"Storno / cancellation of {inv['number']}",
            },
        )

    @registry.action("to_invoice")
    def to_invoice(user: User, params: dict) -> Result:
        """A quote becomes a draft invoice with the same lines."""
        inv, book = invoice(user, params.get("id"), write=True)
        if inv["kind"] != "quote":
            raise ActionError("Only quotes are turned into invoices.")
        lines = [
            {
                k: str(v) if v is not None else ""
                for k, v in line.items()
                if k
                in (
                    "description",
                    "quantity",
                    "unit",
                    "unit_price",
                    "discount_percent",
                    "vat_code",
                    "account",
                )
            }
            for line in lines_of(inv["id"])
        ]
        return save_draft(
            user,
            {
                "book": book["id"],
                "customer_id": inv["customer_id"],
                "kind": "invoice",
                "lines": lines,
                "notes": inv["notes"],
            },
        )

    @registry.every(timedelta(days=1), "recurring")
    def recurring(payload, ctx) -> None:  # type: ignore[no-untyped-def]
        """Issued invoices marked as recurring get a new draft each period. A person issues it."""
        today = date.today()
        for inv in q(
            "SELECT * FROM invoices WHERE recurring_months IS NOT NULL AND number IS NOT "
            "NULL AND kind = 'invoice' AND coalesce(next_run, issue_date) <= :t",
            t=today,
        ):
            months = inv["recurring_months"]
            first = inv["next_run"] or inv["issue_date"]
            following = date(
                first.year + (first.month - 1 + months) // 12,
                (first.month - 1 + months) % 12 + 1,
                min(first.day, 28),
            )
            with registry.db.session() as s:
                new_id = s.execute(
                    text(
                        "INSERT INTO invoices (book_id, customer_id, kind, notes) VALUES (:b, :c, "
                        "'invoice', :n) RETURNING id"
                    ),
                    {
                        "b": inv["book_id"],
                        "c": inv["customer_id"],
                        "n": f"From the recurring invoice {inv['number']}",
                    },
                ).scalar_one()
                s.execute(
                    text(
                        "INSERT INTO invoice_lines (invoice_id, position, description, quantity, "
                        "unit, "
                        "unit_price, discount_percent, vat_code, account) SELECT :n, position, "
                        "description, "
                        "quantity, unit, unit_price, discount_percent, vat_code, account FROM "
                        "invoice_lines "
                        "WHERE invoice_id = :o"
                    ),
                    {"n": new_id, "o": inv["id"]},
                )
                s.execute(
                    text("UPDATE invoices SET next_run = :d WHERE id = :i"),
                    {"d": following, "i": inv["id"]},
                )

    # Screens -------------------------------------------------------------------------------------

    state_labels = {
        "draft": "Draft",
        "issued": "Issued",
        "sent": "Sent",
        "partly_paid": "Partly paid",
        "paid": "Paid",
        "cancelled": "Cancelled",
        "written_off": "Written off",
    }

    def listing(user: User, params: dict, kind: str) -> list[dict]:
        book = book_of(user, params)
        if not book:
            return []
        rows = q(
            "SELECT i.*, c.name AS customer, coalesce((SELECT sum(amount) FROM invoice_payments "
            "p WHERE p.invoice_id = i.id), 0) AS paid FROM invoices i JOIN customers c ON "
            "c.id = i.customer_id WHERE i.book_id = :b AND (i.kind = :k OR (:k = 'invoice' AND "
            "i.kind = 'credit_note')) ORDER BY i.id DESC",
            b=book["id"],
            k=kind,
        )
        today = date.today()
        for r in rows:
            r["total"] = (
                {"value": r["gross"], "currency": "EUR"} if r["gross"] is not None else None
            )
            r["open"] = (
                {"value": r["gross"] - r["paid"], "currency": "EUR"}
                if r["gross"] is not None and r["state"] in ("issued", "sent", "partly_paid")
                else None
            )
            r["overdue_days"] = (
                (today - r["due_date"]).days
                if r["open"] and r["due_date"] and r["due_date"] < today
                else None
            )
            r["state_label"] = state_labels[r["state"]]
            r["kind_label"] = {
                "invoice": "Invoice",
                "credit_note": "Credit note",
                "quote": "Quote",
            }[r["kind"]]
        return rows

    registry.data("invoices")(lambda user, params: listing(user, params, "invoice"))
    registry.data("quotes")(lambda user, params: listing(user, params, "quote"))
    registry.data("receivables")(
        lambda user, params: sorted(
            (r for r in listing(user, params, "invoice") if r["open"]),
            key=lambda r: -(r["overdue_days"] or 0),
        )
    )

    @registry.data("customers")
    def customers(user: User, params: dict) -> list[dict]:
        book = book_of(user, params)
        return (
            q(
                "SELECT * FROM customers WHERE book_id = :b AND NOT archived ORDER BY name",
                b=book["id"],
            )
            if book
            else []
        )

    registry.data("customer_options")(
        lambda user, params: [
            {"value": str(c["id"]), "label": c["name"]} for c in customers(user, params)
        ]
    )
    registry.data("customer_choice")(
        lambda user, params: (
            [{"value": "", "label": "A new customer"}]
            + [{"value": str(c["id"]), "label": c["name"]} for c in customers(user, params)]
        )
    )
    registry.data("unit_options")(
        lambda user, params: [{"value": k, "label": v} for k, v in UNITS.items()]
    )
    registry.data("sales_codes")(
        lambda user, params: [
            {"value": c["id"], "label": c["label"]}
            for c in rules.vat_codes().values()
            if c["direction"] == "sales"
        ]
    )
    registry.data("customer_kinds")(
        lambda user, params: [
            {"value": "business", "label": "Business"},
            {"value": "consumer", "label": "Consumer"},
            {"value": "public", "label": "Public authority"},
        ]
    )
    registry.data("formats")(
        lambda user, params: [
            {"value": "zugferd", "label": "PDF with e-invoice inside (ZUGFeRD)"},
            {"value": "xrechnung", "label": "XRechnung (public authorities)"},
            {"value": "pdf_only", "label": "PDF only (consumers)"},
        ]
    )
    registry.data("languages")(
        lambda user, params: [
            {"value": "de", "label": "Deutsch"},
            {"value": "en", "label": "English"},
        ]
    )
    registry.data("profile_options")(
        lambda user, params: [
            {"value": str(p["id"]), "label": p["name"]} for p in profiles.list(user)
        ]
    )

    @registry.data("invoice")
    def invoice_detail(user: User, params: dict) -> dict:
        if not params.get("id"):
            return {}
        inv, _ = invoice(user, params["id"])
        paid = q(
            "SELECT coalesce(sum(amount), 0) AS p FROM invoice_payments WHERE invoice_id = :i",
            i=inv["id"],
        )[0]["p"]
        return inv | {
            "customer": customer(inv["customer_id"])["name"],
            "state_label": state_labels[inv["state"]],
            "total": {"value": inv["gross"], "currency": "EUR"}
            if inv["gross"] is not None
            else None,
            "paid_amount": {"value": paid, "currency": "EUR"},
            "customer_id": str(inv["customer_id"]),
            "invoice": str(inv["id"]),
            "lines": [
                {k: (str(v) if isinstance(v, Decimal) else v) for k, v in line.items()}
                for line in lines_of(inv["id"])
            ],
            "is_draft": "yes" if not inv["number"] else None,
        }

    def state_of(user: User, params: dict) -> dict | None:
        try:
            return invoice(user, params.get("id"))[0] if params.get("id") else None
        except ActionError:
            return None

    # For show_if: which parts of the invoice page apply to this invoice.
    registry.data("is_draft")(
        lambda user, params: [1] if (inv := state_of(user, params)) and not inv["number"] else []
    )
    registry.data("is_issued_invoice")(
        lambda user, params: (
            [1]
            if (inv := state_of(user, params)) and inv["number"] and inv["kind"] != "quote"
            else []
        )
    )
    registry.data("is_open_invoice")(
        lambda user, params: (
            [1]
            if (inv := state_of(user, params))
            and inv["state"] in ("issued", "sent", "partly_paid")
            and inv["kind"] == "invoice"
            else []
        )
    )
    registry.data("is_issued_quote")(
        lambda user, params: (
            [1]
            if (inv := state_of(user, params)) and inv["number"] and inv["kind"] == "quote"
            else []
        )
    )

    @registry.data("invoice_payments")
    def invoice_payments(user: User, params: dict) -> list[dict]:
        inv, _ = invoice(user, params.get("id"))
        return [
            p | {"money": {"value": p["amount"], "currency": "EUR"}}
            for p in q(
                "SELECT * FROM invoice_payments WHERE invoice_id = :i ORDER BY paid_on", i=inv["id"]
            )
        ]


def _json(value: object) -> str:
    import json

    return json.dumps(value, default=lambda v: str(v) if isinstance(v, Decimal) else v.isoformat())
