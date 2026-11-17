"""Official letters: the deadline from the letter, the lists, the objection; ID documents."""

import os
from datetime import date, timedelta
from pathlib import Path

import pytest
from docuhive.documents import NotFound
from docuhive.profiles import ProfileIn, save
from docuhive.sdk import ActionError
from docuhive.sdk.testing import Archive

pytestmark = pytest.mark.integration
PLUGIN = Path(__file__).resolve().parents[1]

TAX_NOTICE = {
    "letter_date": "2026-03-02",
    "period_amount": 1,
    "period_unit": "months",
    "reference": "12/345/67890",
    "kind": "tax",
    "amount_due": "420.00",
    "currency": "EUR",
    "sender_address": ["Finanzamt Musterstadt", "Postfach 1", "12345 Musterstadt"],
}


def call(archive, how, source, user, /, **params):
    registry = archive.registry("behoerden")
    fn = registry.data_sources[source] if how == "data" else registry.actions[source][0]
    return fn(user, params)


@pytest.fixture
def archive(monkeypatch):
    monkeypatch.setenv(
        "DOCUHIVE_GOTENBERG_URL",
        os.environ.get("DOCUHIVE_TEST_GOTENBERG_URL", "http://127.0.0.1:53001"),
    )
    with Archive(PLUGIN, ai={"*": TAX_NOTICE}) as made:
        yield made


def arrive(archive, owner, **doc):
    doc_id = archive.add(owner, document_type="official_notice", **doc)
    archive.emit("document.classified", document_id=doc_id, document_type="official_notice")
    archive.run_jobs()
    return doc_id


def test_a_tax_notice_gets_its_deadline_and_an_objection(archive):
    alice, bob = archive.user("alice"), archive.user("bob")
    notice = arrive(archive, alice, title="Einkommensteuerbescheid 2025")
    facts = archive.document(notice).facts
    assert facts["respond_by"].value == "2026-04-07"  # 6 April 2026 is Easter Monday
    assert facts["notice_date"].value == "2026-03-02"
    assert facts["reference"].value == "12/345/67890"
    assert facts["amount_due"].value == "420.00"
    assert (
        facts["authority_address"].value == "Finanzamt Musterstadt, Postfach 1, 12345 Musterstadt"
    )

    [row] = call(archive, "data", "open_notices", alice)
    assert (row["kind"], row["respond_by"], row["state"]) == (
        "Tax assessment",
        "2026-04-07",
        "Overdue",
    )
    assert call(archive, "data", "open_notices", bob) == []
    with pytest.raises(NotFound):  # not bob's letter
        call(archive, "data", "notice", bob, id=notice)
    assert call(archive, "data", "can_object", alice, id=notice) is True

    refused = call(archive, "action", "objection", alice, id=notice, authority_address="x")
    assert refused.errors == {"profile_id": "Choose who is objecting"}
    me = save(
        alice,
        ProfileIn(
            kind="person",
            name="Alex Muster",
            tax_number="12/345/67890",
            address={"street": "Beispielweg 1", "postcode": "12345", "city": "Musterstadt"},
        ),
    )
    address = call(archive, "data", "notice", alice, id=notice)["authority_address"]
    done = call(
        archive,
        "action",
        "objection",
        alice,
        id=notice,
        profile_id=str(me["id"] if isinstance(me, dict) else me.id),
        authority_address=address,
        reasons="Die Werbungskosten fehlen.",
        suspend=True,
    )
    letter = done.goto.removeprefix("/documents/")
    assert "Einspruch" in done.message
    made = archive.document(letter)
    assert made.title.startswith("Einspruch: Einkommensteuerbescheid")

    assert call(archive, "action", "answered", alice, id=notice).startswith("Marked")
    assert call(archive, "data", "open_notices", alice) == []
    assert [r["id"] for r in call(archive, "data", "answered_notices", alice)] == [notice]
    assert call(archive, "data", "can_object", alice, id=notice) is False
    call(archive, "action", "reopen", alice, id=notice)
    assert len(call(archive, "data", "open_notices", alice)) == 1


def test_a_printed_deadline_wins_and_reminders_have_nothing_to_object(archive):
    alice = archive.user("alice")
    archive.registry("behoerden")  # the scripted model answers every prompt the same
    from docuhive.ai import fake

    fake.REGISTRY["test/model"].outputs["*"] = {
        "letter_date": "2026-03-02",
        "deadline": "2026-03-16",
        "period_amount": 1,
        "period_unit": "months",
        "kind": "reminder",
    }
    notice = arrive(archive, alice, title="Zahlungserinnerung")
    assert archive.document(notice).facts["respond_by"].value == "2026-03-16"
    assert call(archive, "data", "can_object", alice, id=notice) is False
    with pytest.raises(ActionError):
        call(archive, "action", "objection", alice, id=notice, profile_id="1")


def test_id_documents_by_expiry(archive):
    alice = archive.user("alice")
    soon = archive.add(
        alice,
        title="Reisepass",
        document_type="id-document",
        facts={"expiry_date": date.today() + timedelta(days=90), "holder": "Kim"},
    )
    archive.add(
        alice,
        title="Personalausweis",
        document_type="id-document",
        facts={"expiry_date": date.today() + timedelta(days=900), "holder": "Alex"},
    )
    rows = call(archive, "data", "id_documents", alice)
    assert [(r["title"], r["holder"], r["state"]) for r in rows] == [
        ("Reisepass", "Kim", "Renew soon"),
        ("Personalausweis", "Alex", "Valid"),
    ]
    answer = archive.tool("behoerden", "official_deadlines")(alice)
    assert answer["id_documents"][0]["holder"] == "Kim" and soon in answer["documents"]
    labels = [r["label"] for r in call(archive, "data", "overview", alice)]
    assert labels == ["Letters to answer", "ID documents to renew"]
