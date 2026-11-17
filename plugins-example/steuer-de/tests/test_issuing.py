"""Issuing on PostgreSQL with the real converter: numbers, the hybrid PDF, the lock, the booking,
payments, mail, reminders and credit notes."""

import os
import socketserver
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal as D
from email import message_from_bytes, policy
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from docuhive import documents as core
from docuhive import vault
from docuhive.contracts import MetadataPatch
from docuhive.db import session
from docuhive.documents.holds import Held
from docuhive.mail.settings import get_mail_settings
from docuhive.profiles import ProfileIn, save
from docuhive.sdk import ActionError
from docuhive.sdk._plugin import INTERACTIVE
from docuhive.sdk.testing import Archive
from plugin_modules import module
from sqlalchemy import text

pytestmark = pytest.mark.integration
PLUGIN = Path(__file__).resolve().parents[1]
einvoice = module("einvoice")


class Smtp(socketserver.StreamRequestHandler):
    received: list[bytes] = []

    def handle(self) -> None:
        self.wfile.write(b"220 test\r\n")
        while line := self.rfile.readline().decode().strip():
            verb = line.split(" ")[0].upper()
            if verb == "DATA":
                self.wfile.write(b"354 go\r\n")
                data = b""
                while (chunk := self.rfile.readline()) != b".\r\n":
                    data += chunk
                Smtp.received.append(data)
                self.wfile.write(b"250 queued\r\n")
            elif verb == "QUIT":
                self.wfile.write(b"221 bye\r\n")
                return
            else:
                self.wfile.write(b"250 ok\r\n")


def call(archive, how, source, user, /, **params):
    registry = archive.registry("steuer-de")
    fn = registry.data_sources[source] if how == "data" else registry.actions[source][0]
    return fn(user, params)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv(
        "DOCUHIVE_GOTENBERG_URL",
        os.environ.get("DOCUHIVE_TEST_GOTENBERG_URL", "http://127.0.0.1:53001"),
    )
    monkeypatch.setenv("DOCUHIVE_OCR_LANGUAGES", "eng")
    monkeypatch.setenv("DOCUHIVE_MAIL_TOKEN_KEY", Fernet.generate_key().decode())
    get_mail_settings.cache_clear()
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Smtp)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    Smtp.received.clear()
    try:
        with Archive(PLUGIN) as archive:
            alice = archive.user("alice")
            me = save(
                alice,
                ProfileIn(
                    kind="business",
                    name="Muster Design",
                    address={"street": "Beispielweg 1", "postcode": "12345", "city": "Musterstadt"},
                    email="post@example.org",
                    tax_number="12/345/67890",
                    bank={"holder": "Muster Design", "iban": "DE89 3704 0044 0532 0130 00"},
                    smtp={
                        "host": "127.0.0.1",
                        "port": server.server_address[1],
                        "from_address": "post@example.org",
                    },
                ),
            )
            call(
                archive,
                "action",
                "save_book",
                alice,
                name="Studio",
                kind="euer",
                chart="skr03",
                vat_period="quarterly",
                profile_id=str(me.id),
            )
            call(
                archive,
                "action",
                "save_customer",
                alice,
                name="Kunde Beispiel GmbH",
                street="Hauptstraße 5",
                postcode="54321",
                city="Beispielstadt",
                email="buchhaltung@example.org",
                payment_terms_days="14",
            )
            yield archive, alice
    finally:
        server.shutdown()
        get_mail_settings.cache_clear()


def draft(archive, user, *lines, **more):
    customer = call(archive, "data", "customers", user)[0]["id"]
    made = call(
        archive,
        "action",
        "save_draft",
        user,
        customer_id=str(customer),
        service_to=date.today().isoformat(),
        lines=[
            {"description": d, "quantity": q, "unit": "HUR", "unit_price": p, "vat_code": c}
            for d, q, p, c in lines
        ],
        **more,
    )
    return int(made.goto.split("=")[1])


def test_issue_lock_book_pay_and_send(setup):
    archive, alice = setup
    first = draft(
        archive, alice, ("Beratung", "10", "95.00", "sale_19"), ("Fachbuch", "1", "40.00", "sale_7")
    )

    assert call(archive, "data", "is_draft", alice, id=first) == [1]
    assert call(archive, "data", "is_open_invoice", alice, id=first) == []
    issued = call(archive, "action", "issue", alice, id=first)
    assert call(archive, "data", "is_draft", alice, id=first) == []
    assert call(archive, "data", "is_open_invoice", alice, id=first) == [1]
    year = date.today().year
    assert issued.message == f"Issued as RE-{year}-0001."
    inv = call(archive, "data", "invoice", alice, id=first)
    assert (inv["net"], inv["vat"], inv["gross"]) == (D("990.00"), D("183.30"), D("1173.30"))
    assert inv["state"] == "issued" and inv["due_date"] == date.today() + timedelta(days=14)

    # The hybrid PDF in the archive carries the e-invoice; it reads back exactly.
    folder = vault.root()
    stored = next(folder.glob(f"*/{inv['document_id']}"), None)
    archive.run_jobs(queues=("default", "ocr"))
    stored = next(folder.glob(f"*/{inv['document_id']}/original.pdf"))
    read = einvoice.find(stored.read_bytes())
    assert (read.number, read.gross, read.problems) == (f"RE-{year}-0001", D("1173.30"), [])

    # Booked as income, one entry per VAT rate; locked for everyone.
    with archive.registry("steuer-de").db.session() as s:
        entries = s.execute(
            text(
                "SELECT vat_code, net, vat, state, origin FROM entries "
                "WHERE document_id = :d ORDER BY vat_code"
            ),
            {"d": inv["document_id"]},
        ).all()
    assert entries == [
        ("sale_19", D("950.00"), D("180.50"), "confirmed", "invoice"),
        ("sale_7", D("40.00"), D("2.80"), "confirmed", "invoice"),
    ]
    with pytest.raises(Held):
        core.apply_metadata(inv["document_id"], MetadataPatch(title="x"), actor=f"user:{alice.id}")
    with pytest.raises(ActionError, match="cannot be changed"):
        call(
            archive,
            "action",
            "save_draft",
            alice,
            invoice=str(first),
            customer_id=inv["customer_id"],
        )
    with pytest.raises(Exception, match="issued invoice"):
        with archive.registry("steuer-de").db.session() as s:
            s.execute(text("UPDATE invoices SET gross = 1 WHERE id = :i"), {"i": first})
    with pytest.raises(Exception, match="issued invoice"):
        with archive.registry("steuer-de").db.session() as s:
            s.execute(text("DELETE FROM invoice_lines WHERE invoice_id = :i"), {"i": first})

    # The preview shows exactly what goes out.
    preview = archive.registry("steuer-de").actions["send_invoice"][1]["preview"](
        alice, {"id": first}
    )
    assert preview["to"] == ["buchhaltung@example.org"]
    assert preview["subject"] == f"Rechnung RE-{year}-0001" and preview["attachments"]

    # Sending: from a button only; the PDF arrives with the XML inside, unchanged.
    token = INTERACTIVE.set(True)
    try:
        call(archive, "action", "send_invoice", alice, id=first)
    finally:
        INTERACTIVE.reset(token)
    message = message_from_bytes(Smtp.received[-1], policy=policy.default)
    assert message["Subject"] == preview["subject"]
    (attachment,) = list(message.iter_attachments())
    assert einvoice.find(attachment.get_content()).gross == D("1173.30")
    assert call(archive, "data", "invoice", alice, id=first)["state"] == "sent"

    # Paid in two parts: then the income counts in the year it was paid.
    call(
        archive,
        "action",
        "record_payment",
        alice,
        id=first,
        amount="1000.00",
        paid_on=date.today().isoformat(),
    )
    assert call(archive, "data", "invoice", alice, id=first)["state"] == "partly_paid"
    call(
        archive,
        "action",
        "record_payment",
        alice,
        id=first,
        amount="173.30",
        paid_on=date.today().isoformat(),
    )
    assert call(archive, "data", "invoice", alice, id=first)["state"] == "paid"
    with archive.registry("steuer-de").db.session() as s:
        assert (
            s.execute(
                text("SELECT DISTINCT period_year FROM entries WHERE document_id = :d"),
                {"d": inv["document_id"]},
            ).scalar_one()
            == year
        )

    # Cancelling: a credit note with its own number that reverses the booking.
    note = int(call(archive, "action", "credit_note", alice, id=first).goto.split("=")[1])
    assert call(archive, "action", "issue", alice, id=note).message == f"Issued as GS-{year}-0001."
    assert call(archive, "data", "invoice", alice, id=first)["state"] == "cancelled"
    with archive.registry("steuer-de").db.session() as s:
        total = s.execute(
            text("SELECT sum(net) FROM entries WHERE origin = 'invoice'")
        ).scalar_one()
    assert total == 0


def test_numbers_have_no_gaps_and_reminders(setup):
    archive, alice = setup
    # A refused issue uses no number.
    with archive.registry("steuer-de").db.session() as s:
        s.execute(text("UPDATE books SET vat_status = 'small_business'"))
    refused = draft(archive, alice, ("Beratung", "1", "100.00", "sale_19"))
    with pytest.raises(ActionError, match="small-business"):
        call(archive, "action", "issue", alice, id=refused)
    with archive.registry("steuer-de").db.session() as s:
        s.execute(text("UPDATE books SET vat_status = 'regular'"))

    drafts = [draft(archive, alice, (f"Leistung {n}", "1", "10.00", "sale_19")) for n in range(5)]
    with ThreadPoolExecutor(5) as pool:  # five people pressing Issue at the same moment
        list(pool.map(lambda i: call(archive, "action", "issue", alice, id=i), drafts))
    year = date.today().year
    numbers = sorted(call(archive, "data", "invoice", alice, id=i)["number"] for i in drafts)
    assert numbers == [f"RE-{year}-{n:04d}" for n in range(1, 6)]

    # A reminder only after the due date, then the next one only after a week.
    with archive.registry("steuer-de").db.session() as s:
        s.execute(
            text("UPDATE invoices SET due_date = :d WHERE id = :i"),
            {"d": date.today() - timedelta(days=20), "i": drafts[0]},
        )
    with pytest.raises(ActionError, match="Wait until"):
        call(archive, "action", "payment_reminder", alice, id=drafts[1])
    made = call(archive, "action", "payment_reminder", alice, id=drafts[0])
    assert made.goto.startswith("/documents/")
    with pytest.raises(ActionError, match="Wait until"):
        call(archive, "action", "payment_reminder", alice, id=drafts[0])
    assert [r["number"] for r in call(archive, "data", "receivables", alice)][
        0
    ] == f"RE-{year}-0001"


def test_quotes_become_invoices(setup):
    archive, alice = setup
    customer = call(archive, "data", "customers", alice)[0]["id"]
    quote = int(
        call(
            archive,
            "action",
            "save_quote",
            alice,
            customer_id=str(customer),
            lines=[
                {
                    "description": "Website",
                    "quantity": "1",
                    "unit_price": "2500.00",
                    "vat_code": "sale_19",
                }
            ],
        ).goto.split("=")[1]
    )
    assert call(archive, "action", "issue", alice, id=quote).message.startswith("Issued as AN-")
    made = call(archive, "action", "to_invoice", alice, id=quote)
    new = int(made.goto.split("=")[1])
    assert call(archive, "data", "invoice", alice, id=new)["lines"][0]["description"] == "Website"
    with session() as s:
        assert s.execute(text("SELECT count(*) FROM document_holds")).scalar_one() == 0  # no lock
