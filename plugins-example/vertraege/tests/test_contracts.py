"""The journey: a contract arrives, is listed with its notice date, a person corrects it, a price
changes, the cancellation letter is made, and the provider's confirmation ends the contract."""

import os
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
from docuhive import documents as core
from docuhive.contracts import MetadataPatch
from docuhive.profiles import ProfileIn, save
from docuhive.sdk import ActionError
from docuhive.sdk.testing import Archive

pytestmark = pytest.mark.integration
PLUGIN = Path(__file__).resolve().parents[1]
TERMS = {
    "provider": "Stromwerk Beispiel GmbH",
    "provider_address": ["Stromwerk Beispiel GmbH", "Kundenservice", "12345 Musterstadt"],
    "product": "Öko Strom 24",
    "customer_number": "K-4711",
    "start_date": "2026-01-01",
    "minimum_term_months": 24,
    "renewal_months": 12,
    "notice_amount": 1,
    "notice_unit": "months",
    "notice_to": "term_end",
    "price": "89.00",
    "price_period": "month",
}
AI = {
    "You read a contract": TERMS,
    "confirmation that a contract was cancelled": {
        "is_confirmation": True,
        "ends_on": "2027-12-31",
    },
}


def call(archive, how, source, user, /, **params):
    registry = archive.registry("vertraege")
    fn = registry.data_sources[source] if how == "data" else registry.actions[source][0]
    return fn(user, params)


def arrive(archive, owner, **doc):
    doc_id = archive.add(owner, **doc)
    archive.emit("document.classified", document_id=doc_id, document_type=doc["document_type"])
    archive.run_jobs()
    return doc_id


@pytest.fixture
def archive(monkeypatch):
    monkeypatch.setenv(
        "DOCUHIVE_GOTENBERG_URL",
        os.environ.get("DOCUHIVE_TEST_GOTENBERG_URL", "http://127.0.0.1:53001"),
    )
    monkeypatch.setenv("DOCUHIVE_OCR_LANGUAGES", "eng")
    with Archive(PLUGIN, ai=AI) as made:
        yield made


def test_a_contract_from_arrival_to_its_end(archive):
    alice, bob = archive.user("alice"), archive.user("bob")
    common = dict(document_type="contract", category="utilities/electricity", date=date(2026, 1, 1))
    scan = arrive(archive, alice, title="Stromvertrag (Scan)", **common)
    mailed = arrive(archive, alice, title="Stromvertrag (E-Mail)", **common)

    (c,) = call(archive, "data", "contracts", alice)  # two copies, one contract
    assert (c["provider"], c["kind"], c["term_end"]) == (
        TERMS["provider"],
        "energy",
        date(2027, 12, 31),
    )
    assert c["notice_by"] == date(2027, 11, 30) and c["per_year"]["value"] == D("1068.00")
    docs = {d["id"] for d in call(archive, "data", "contract_documents", alice, id=c["id"])}
    assert docs == {scan, mailed}
    facts = archive.document(scan).facts  # the archive's own reminder now uses these dates
    assert facts["end_date"].value == "2027-12-31" and facts["notice_period_days"].value == "31"
    assert call(archive, "data", "contracts", bob) == []

    # A person's correction is theirs: a later reading does not change it.
    call(archive, "action", "save_contract", alice, id=c["id"], notice_amount="3")
    arrive(archive, alice, title="Stromvertrag (again)", **common)
    (c,) = call(archive, "data", "contracts", alice)
    assert c["notice_amount"] == 3 and c["notice_by"] == date(2027, 9, 30)
    with pytest.raises(ActionError):
        call(archive, "action", "save_contract", bob, id=c["id"], notice_amount="1")

    # A new amount on a letter is a note until accepted.
    change = archive.add(
        alice,
        document_type="contract_change",
        title="Preisanpassung",
        date=date(2026, 3, 1),
        facts={"new_price": ("94.50", "EUR"), "effective_date": date(2026, 4, 1)},
    )
    core.apply_metadata(change, MetadataPatch(correspondent=TERMS["provider"]), actor="system")
    archive.emit("document.classified", document_id=change, document_type="contract_change")
    archive.run_jobs()
    (note,) = call(archive, "data", "prices", alice, id=c["id"])
    assert note["status"] == "New: check it" and call(archive, "data", "contracts", alice)[0][
        "price"
    ] == D("89.00")
    call(archive, "action", "accept_price", alice, id=note["id"])
    assert call(archive, "data", "contracts", alice)[0]["price"] == D("94.50")

    # The letter needs an identity and an address; then it is a draft document, nothing is sent.
    with pytest.raises(ActionError, match="identity"):
        call(archive, "action", "prepare_cancellation", alice, id=c["id"])
    me = save(
        alice,
        ProfileIn(
            kind="person",
            name="Alice Muster",
            address={"street": "Beispielweg 1", "postcode": "12345", "city": "Musterstadt"},
        ),
    )
    call(archive, "action", "save_contract", alice, id=c["id"], profile_id=str(me.id))
    made = call(archive, "action", "prepare_cancellation", alice, id=c["id"])
    letter = made.goto.removeprefix("/documents/")
    archive.run_jobs(queues=("default", "ocr"))
    text = core.get_content(letter)
    assert "K-4711" in text and "30.09.2027" not in text  # the date is the term end, not notice
    assert "31.12.2027" in text and "Kündigung" in text
    assert archive.document(letter).source.derived_from

    call(archive, "action", "mark_sent", alice, id=c["id"])
    assert call(archive, "data", "contracts", alice)[0]["state"] == "cancelled"

    # The provider confirms: the contract has ended.
    confirm = archive.add(
        alice,
        document_type="letter",
        title="Kündigungsbestätigung",
        date=date(2026, 10, 1),
        content="Wir bestätigen Ihre Kündigung.",
    )
    core.apply_metadata(confirm, MetadataPatch(correspondent=TERMS["provider"]), actor="system")
    archive.emit("document.classified", document_id=confirm, document_type="letter")
    archive.run_jobs()
    (c,) = call(archive, "data", "contracts", alice)
    assert c["state"] == "ended" and c["cancel_effective"] == date(2027, 12, 31)


def test_ask_tools_and_costs(archive):
    alice = archive.user("alice")
    arrive(
        archive, alice, document_type="contract", category="utilities/electricity", title="Strom"
    )
    tool = archive.tool("vertraege", "contracts_list")
    assert tool(alice)["contracts"][0]["per_month"] == "89.00"
    assert tool(alice, cancellable_within_days=30)["contracts"] == []
    assert archive.tool("vertraege", "monthly_cost")(alice)["per_month"] == {"energy": "89.00"}


def test_regular_payments_without_a_contract(archive, monkeypatch):
    from datetime import timedelta

    from docuhive.plugins import install

    alice = archive.user("alice")
    start = date.today() - timedelta(days=150)
    rows = [
        {
            "id": n,
            "counterparty": "Streaming Beispiel",
            "amount": D("-9.99"),
            "booking_date": start + timedelta(days=30 * n),
            "ignored_reason": None,
        }
        for n in range(5)
    ]
    rows += [
        {
            "id": 9 + n,
            "counterparty": "Stromwerk Beispiel GmbH",
            "amount": D("-89.00"),
            "booking_date": start + timedelta(days=30 * n),
            "ignored_reason": None,
        }
        for n in range(5)
    ]
    monkeypatch.setitem(install.SERVICES, "bank.transactions", lambda user, **kw: rows)
    arrive(
        archive, alice, document_type="contract", category="utilities/electricity", title="Strom"
    )

    found = call(archive, "data", "unknown_recurring", alice)
    assert [f["payee"] for f in found] == ["Streaming Beispiel"]  # the power contract is known
    made = call(archive, "action", "contract_from_payment", alice, key=found[0]["key"])
    contract_id = made.goto.split("=")[1]
    c = call(archive, "data", "contract", alice, id=contract_id)
    assert (c["provider"], c["price"], c["price_period"]) == (
        "Streaming Beispiel",
        D("9.99"),
        "month",
    )
    assert call(archive, "data", "unknown_recurring", alice) == []

    rows.extend(
        {
            "id": 20 + n,
            "counterparty": "Verein Beispiel",
            "amount": D("-12.00"),
            "booking_date": start + timedelta(days=30 * n),
            "ignored_reason": None,
        }
        for n in range(4)
    )
    call(
        archive,
        "action",
        "not_a_contract",
        alice,
        key=call(archive, "data", "unknown_recurring", alice)[0]["key"],
    )
    assert call(archive, "data", "unknown_recurring", alice) == []
