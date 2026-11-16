"""Filing by hand, letters to the tax office, and the advisor hand-over."""

import io
import os
import zipfile
from datetime import date
from pathlib import Path

import pikepdf
import pytest
from docuhive import documents as core
from docuhive import vault
from docuhive.contracts import MetadataPatch
from docuhive.db import session
from docuhive.db.models import Document
from docuhive.documents.holds import Held
from docuhive.profiles import ProfileIn, save
from docuhive.reminders.models import Reminder
from docuhive.sdk import ActionError
from docuhive.sdk._plugin import NotInteractive
from docuhive.sdk.testing import Archive
from sqlalchemy import select, update

pytestmark = pytest.mark.integration
PLUGIN = Path(__file__).resolve().parents[1]
Q1 = {"key": "2026-Q1"}


def call(archive, how, source, user, /, **params):
    registry = archive.registry("steuer-de")
    fn = registry.data_sources[source] if how == "data" else registry.actions[source][0]
    return fn(user, params)


def with_pdf(doc_id: str) -> None:
    folder = vault.root() / "2026" / doc_id
    folder.mkdir(parents=True, exist_ok=True)
    pdf = pikepdf.new()
    pdf.add_blank_page()
    out = io.BytesIO()
    pdf.save(out)
    (folder / "archive.pdf").write_bytes(out.getvalue())
    with session() as s:
        s.execute(update(Document).where(Document.id == doc_id).values(vault_path=f"2026/{doc_id}"))


@pytest.fixture
def archive(monkeypatch):
    monkeypatch.setenv(
        "DOCUHIVE_GOTENBERG_URL",
        os.environ.get("DOCUHIVE_TEST_GOTENBERG_URL", "http://127.0.0.1:53001"),
    )
    with Archive(PLUGIN) as made:
        yield made


def test_filed_letters_and_handover(archive):
    alice = archive.user("alice")
    me = save(
        alice,
        ProfileIn(
            kind="business",
            name="Muster Design",
            tax_number="12/345/67890",
            address={"street": "Beispielweg 1", "postcode": "12345", "city": "Musterstadt"},
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
        tax_number="12/345/67890",
    )
    receipt = archive.add(
        alice,
        document_type="receipt",
        title="Bürobedarf",
        date=date(2026, 2, 10),
        facts={"amount_total": ("119.00", "EUR")},
    )
    core.apply_metadata(receipt, MetadataPatch(correspondent="Papier Beispiel"), actor="system")
    archive.emit("document.classified", document_id=receipt, document_type="receipt")
    archive.run_jobs()
    (entry,) = call(archive, "data", "proposals", alice)
    call(
        archive,
        "action",
        "confirm_entry",
        alice,
        entry=entry["id"],
        account="4930",
        vat_code="purchase_19",
    )

    reference = {
        r["label"]: r["value"] for r in call(archive, "data", "payment_reference", alice, **Q1)
    }
    assert reference["Payment reference"] == "12/345/67890 USt I 2026"

    confirmation = archive.add(alice, title="Übertragungsprotokoll UStVA Q1", date=date(2026, 4, 9))
    with pytest.raises(ActionError, match="Close the period"):
        call(archive, "action", "mark_filed", alice, confirmation=confirmation, **Q1)
    call(archive, "action", "close_period", alice, **Q1)
    call(
        archive,
        "action",
        "mark_filed",
        alice,
        confirmation=confirmation,
        filed_on="2026-04-09",
        **Q1,
    )
    assert call(archive, "data", "period_summary", alice, **Q1)[0]["value"] == "Filed"
    with pytest.raises(Held):
        core.apply_metadata(confirmation, MetadataPatch(title="x"), actor=f"user:{alice.id}")

    # An objection: the formal parts, no grounds, and its deadline as a reminder.
    made = call(
        archive,
        "action",
        "write_letter",
        alice,
        kind="objection",
        year="2025",
        tax_type="Einkommensteuer",
        notice_date="2026-11-02",
        office_address="Finanzamt Musterstadt\nPostfach 1\n12345 Musterstadt",
    )
    letter = made.goto.removeprefix("/documents/")
    assert archive.document(letter).title.startswith("Einspruch")
    with session() as s:
        due = s.scalars(
            select(Reminder.due_on).where(Reminder.fact == f"plugin:steuer-de:objection:{letter}")
        ).all()
    assert date(2026, 12, 5) in due  # posted 2 Nov, received 5 Nov, one month later

    # The advisor gets the bookings and the documents in one file.
    with_pdf(receipt)
    zipped = call(archive, "action", "advisor_zip", alice, **Q1).download
    with zipfile.ZipFile(io.BytesIO(zipped[1])) as z:
        names = z.namelist()
        index = z.read("bookings.csv").decode("utf-8-sig")
    assert "bookings.csv" in names and any(n.startswith("documents/") for n in names)
    assert "Papier Beispiel" in index and "documents/" in index
    with pytest.raises(NotInteractive):  # a link is made only when a person presses the button
        call(archive, "action", "advisor_link", alice, **Q1)

    made = call(archive, "action", "procedure", alice)
    assert archive.document(made.goto.removeprefix("/documents/")).title.startswith(
        "Verfahrensdokumentation"
    )
