"""The journey: a receipt with a washing machine and groceries, one proposal, added to the kitchen,
a manual found for it, the contents list and a claim bundle, and Ask."""

import io
import os
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pikepdf
import pytest
from docuhive import vault
from docuhive.contracts import MetadataPatch
from docuhive.db import session
from docuhive.db.models import Document
from docuhive.reminders.models import Reminder
from docuhive.sdk import ActionError
from docuhive.sdk.testing import Archive
from sqlalchemy import select, update

pytestmark = pytest.mark.integration
PLUGIN = Path(__file__).resolve().parents[1]
RECEIPT = {
    "items": [
        {
            "name": "Waschmaschine Bosch Serie 6",
            "category": "appliance",
            "manufacturer": "Bosch",
            "model": "WGG14400",
            "quantity": 1,
            "unit_price": "649.00",
            "is_durable": True,
            "warranty_months": 36,
        },
        {
            "name": "Kaffee",
            "category": "other",
            "quantity": 2,
            "unit_price": "8.99",
            "is_durable": False,
        },
        {
            "name": "Wäschekorb",
            "category": "other",
            "quantity": 1,
            "unit_price": "12.00",
            "is_durable": True,
        },
        {
            "name": "Bügeleisen",
            "category": "appliance",
            "quantity": 1,
            "unit_price": "79.00",
            "is_durable": True,
        },
    ]
}
GREEDY = {
    "items": [
        {
            "name": "TV",
            "category": "electronics",
            "quantity": 1,
            "unit_price": "999.00",
            "is_durable": True,
        }
    ]
}


def call(archive, how, source, user, /, **params):
    registry = archive.registry("inventar")
    fn = registry.data_sources[source] if how == "data" else registry.actions[source][0]
    return fn(user, params)


def arrive(archive, owner, document_type, **doc):
    from docuhive import documents as core

    seller = doc.pop("seller", None)
    doc_id = archive.add(owner, document_type=document_type, **doc)
    if seller:
        core.apply_metadata(doc_id, MetadataPatch(correspondent=seller), actor="system")
    archive.emit("document.classified", document_id=doc_id, document_type=document_type)
    archive.run_jobs()
    return doc_id


def with_pdf(doc_id: str) -> None:
    folder = vault.root() / "2026" / doc_id
    folder.mkdir(parents=True, exist_ok=True)
    pdf = pikepdf.new()
    pdf.add_blank_page()
    out = io.BytesIO()
    pdf.save(out)
    (folder / "archive.pdf").write_bytes(out.getvalue())
    with session() as s:  # made-up documents have no vault folder of their own
        s.execute(update(Document).where(Document.id == doc_id).values(vault_path=f"2026/{doc_id}"))


@pytest.fixture
def archive(monkeypatch):
    monkeypatch.setenv(
        "DOCUHIVE_GOTENBERG_URL",
        os.environ.get("DOCUHIVE_TEST_GOTENBERG_URL", "http://127.0.0.1:53001"),
    )
    monkeypatch.setenv("DOCUHIVE_OCR_LANGUAGES", "eng")
    answers = {"List the goods": RECEIPT, "type plate": {"serial_number": "FD 9901 12345"}}
    with Archive(PLUGIN, ai=answers) as made:
        yield made


def test_from_receipt_to_claim(archive):
    alice, bob = archive.user("alice"), archive.user("bob")
    receipt = arrive(
        archive,
        alice,
        "receipt",
        title="Elektromarkt Beleg",
        seller="Elektromarkt Beispiel",
        date=date(2026, 3, 2),
        category="purchases/receipts",
        facts={"amount_total": ("770.98", "EUR")},
    )
    proposals = call(archive, "data", "proposals", alice)
    assert [p["name"] for p in proposals] == [
        "Bügeleisen",
        "Waschmaschine Bosch Serie 6",
    ]  # not food
    machine = next(p for p in proposals if p["model"] == "WGG14400")
    assert (machine["warranty_until"], machine["warranty_source"]) == (date(2029, 3, 2), "document")
    iron = next(p for p in proposals if p["name"] == "Bügeleisen")
    assert (iron["warranty_until"], iron["warranty_source"]) == (date(2028, 3, 2), "assumed")
    assert call(archive, "data", "proposals", bob) == []

    call(archive, "action", "add_item", alice, id=machine["id"], location="Küche")
    call(archive, "action", "not_an_item", alice, id=iron["id"])
    with session() as s:
        due = s.scalars(select(Reminder.due_on).where(Reminder.owner_id == alice.id)).all()
    assert date(2029, 3, 2) in due
    # "Not an item" is remembered: the same receipt again does not propose the iron.
    arrive(
        archive,
        alice,
        "receipt",
        title="Beleg 2",
        seller="Elektromarkt Beispiel",
        date=date(2026, 3, 3),
        facts={"amount_total": ("770.98", "EUR")},
    )
    names = [p["name"] for p in call(archive, "data", "proposals", alice)]
    assert "Bügeleisen" not in names

    # The manual names the model: it is suggested on the machine, a person confirms.
    manual = arrive(archive, alice, "manual", title="Bedienungsanleitung WGG14400")
    (item,) = [i for i in call(archive, "data", "items", alice) if i["model"] == "WGG14400"]
    docs = call(archive, "data", "item_documents", alice, id=item["id"])
    assert {d["id"]: d["status"] for d in docs} == {receipt: None, manual: "Suggested"}
    call(archive, "action", "confirm_document", alice, item=item["id"], document=manual)

    # A photo of the type plate fills in the serial number.
    plate = archive.add(alice, document_type="type_plate", title="Typenschild")
    call(
        archive,
        "action",
        "attach_document",
        alice,
        id=item["id"],
        document=plate,
        role="type_plate",
    )
    assert call(archive, "data", "item", alice, id=item["id"])["serial_number"] == "FD 9901 12345"

    # The list for the insurer and a claim bundle are documents.
    made = call(archive, "action", "contents_list", alice)
    assert made.goto.startswith("/documents/")
    for doc_id in (receipt, manual, plate):
        with_pdf(doc_id)
    bundle = call(archive, "action", "claim_bundle", alice, id=item["id"])
    archive.run_jobs(queues=("default", "ocr"))
    bundle_id = bundle.goto.removeprefix("/documents/")
    stored = archive.document(bundle_id)
    assert stored.source.derived_from == [receipt, plate, manual]  # receipt, plate, manual order
    folder = next(vault.root().glob(f"*/{bundle_id}"))
    with pikepdf.open(next(folder.glob("original.*"))) as pdf:
        assert len(pdf.pages) == 1 + 3  # the cover sheet and one page per document

    # Ask, and isolation.
    answer = archive.tool("inventar", "inventory_items")(alice, query="Waschmaschine")
    assert answer["items"][0]["warranty_until"] == "2029-03-02" and receipt in answer["documents"]
    assert archive.tool("inventar", "inventory_items")(bob)["items"] == []
    assert archive.tool("inventar", "inventory_value")(alice)["totals"] == {"EUR": "649.00"}
    with pytest.raises(ActionError):
        call(archive, "action", "save_item", bob, id=item["id"], name="Mine now")

    # Sold: off the lists, no reminder.
    call(archive, "action", "leave", alice, id=item["id"], state="sold")
    assert call(archive, "data", "items", alice) == []
    with session() as s:
        assert date(2029, 3, 2) not in s.scalars(select(Reminder.due_on)).all()


def test_prices_above_the_receipt_are_refused(archive, monkeypatch):
    from docuhive.ai import fake

    fake.REGISTRY["test/model"].outputs = {"List the goods": [GREEDY, GREEDY, GREEDY]}
    alice = archive.user("alice")
    arrive(
        archive,
        alice,
        "receipt",
        title="Kleiner Beleg",
        date=date(2026, 3, 2),
        facts={"amount_total": ("99.00", "EUR")},
    )
    assert call(archive, "data", "proposals", alice) == []  # nothing invented


def test_manual_entry_assumes_the_usual_warranty(archive):
    alice = archive.user("alice")
    made = call(
        archive,
        "action",
        "save_item",
        alice,
        name="Laptop",
        category="electronics",
        purchase_date="2026-01-31",
        price="1299.00",
        location_id="Büro",
    )
    item_id = int(made.goto.split("=")[1])
    item = call(archive, "data", "item", alice, id=item_id)
    assert (item["warranty_until"], item["warranty_source"], item["business_flag"]) == (
        date(2028, 1, 31),
        "assumed",
        "asset",
    )
    assert item["location"] == "Büro" and item["price"] == D("1299.00")
