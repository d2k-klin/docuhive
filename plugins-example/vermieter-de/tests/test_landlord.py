"""The journey: a property with two flats, five bills from the archive confirmed, the draft
statement with what is missing, issued and locked with its bills, the rent ledger, tax figures."""

import os
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
from docuhive import documents as core
from docuhive.contracts import MetadataPatch
from docuhive.documents.holds import Held
from docuhive.profiles import ProfileIn, save
from docuhive.sdk import ActionError
from docuhive.sdk.testing import Archive

pytestmark = pytest.mark.integration
PLUGIN = Path(__file__).resolve().parents[1]
BILLS = [  # title, sender, amount, from, to
    (
        "Grundsteuerbescheid 2026",
        "Stadt Musterstadt",
        "600.00",
        date(2026, 1, 1),
        date(2026, 12, 31),
    ),
    (
        "Wasser und Abwasser 2026",
        "Stadtwerke Beispiel",
        "900.00",
        date(2026, 1, 1),
        date(2026, 12, 31),
    ),
    ("Müllabfuhr 2026", "Entsorgung Beispiel", "400.00", date(2026, 1, 1), date(2026, 12, 31)),
    (
        "Heizkostenabrechnung 2026",
        "Wärmemessung Beispiel",
        "1500.00",
        date(2026, 1, 1),
        date(2026, 12, 31),
    ),
    ("Reparatur Dachrinne", "Handwerker Beispiel", "350.00", date(2026, 5, 1), date(2026, 5, 1)),
]


def call(archive, how, source, user, /, **params):
    registry = archive.registry("vermieter-de")
    fn = registry.data_sources[source] if how == "data" else registry.actions[source][0]
    return fn(user, params)


@pytest.fixture
def archive(monkeypatch):
    monkeypatch.setenv(
        "DOCUHIVE_GOTENBERG_URL",
        os.environ.get("DOCUHIVE_TEST_GOTENBERG_URL", "http://127.0.0.1:53001"),
    )
    with Archive(PLUGIN) as made:
        yield made


def test_from_bills_to_a_locked_statement(archive):
    alice, bob = archive.user("alice"), archive.user("bob")
    me = save(
        alice,
        ProfileIn(
            kind="person",
            name="Alice Muster",
            address={"street": "Beispielweg 1", "postcode": "12345", "city": "Musterstadt"},
            bank={"iban": "DE89 3704 0044 0532 0130 00"},
        ),
    )
    call(
        archive,
        "action",
        "save_property",
        alice,
        name="Hauptstraße 5",
        street="Hauptstraße 5",
        postcode="54321",
        city="Beispielstadt",
        profile_id=str(me.id),
    )
    prop = call(archive, "data", "properties", alice)[0]
    call(archive, "action", "save_unit", alice, property=str(prop["id"]), name="EG", area="40")
    call(archive, "action", "save_unit", alice, property=str(prop["id"]), name="OG", area="60")
    ground, upper = call(archive, "data", "units", alice)
    call(
        archive,
        "action",
        "save_tenancy",
        alice,
        unit=str(ground["id"]),
        tenant_name="Mieter Eins",
        start_date="2025-01-01",
        rent="500",
        advance="100",
        persons="1",
    )
    call(
        archive,
        "action",
        "save_tenancy",
        alice,
        unit=str(upper["id"]),
        tenant_name="Mieterin Zwei",
        start_date="2025-01-01",
        rent="700",
        advance="150",
        persons="3",
    )
    with pytest.raises(ActionError):
        call(archive, "action", "save_unit", bob, property=str(prop["id"]), name="X", area="10")

    bills = []
    for title, sender, amount, start, end in BILLS:
        doc = archive.add(
            alice,
            document_type="invoice",
            title=title,
            category="housing/property",
            date=end,
            facts={"amount_total": (amount, "EUR"), "period_start": start, "period_end": end},
        )
        core.apply_metadata(doc, MetadataPatch(correspondent=sender), actor="system")
        archive.emit("document.classified", document_id=doc, document_type="invoice")
        bills.append(doc)
    archive.run_jobs()
    proposed = {c["document_id"]: c["cost_type"] for c in call(archive, "data", "costs", alice)}
    assert proposed == dict(
        zip(bills, ["property_tax", "water", "waste", "heating", "repairs"], strict=True)
    )
    for c in call(archive, "data", "costs", alice):
        call(archive, "action", "confirm_cost", alice, id=c["id"])

    tenancy = next(
        t for t in call(archive, "data", "tenancies", alice) if t["tenant_name"] == "Mieter Eins"
    )
    params = {"tenancy": tenancy["id"], "year": 2026}
    steps = call(archive, "data", "missing", alice, **params)
    assert any("Heating" in s["label"] and s["state"] == "problem" for s in steps)
    with pytest.raises(ActionError, match="Before you issue"):
        call(archive, "action", "issue_statement", alice, **params)
    for t, value in (
        (tenancy["id"], "600.00"),
        (
            next(
                x["id"]
                for x in call(archive, "data", "tenancies", alice)
                if x["id"] != tenancy["id"]
            ),
            "900.00",
        ),
    ):
        call(
            archive,
            "action",
            "record_consumption",
            alice,
            tenancy=t,
            year="2026",
            cost_type="heating",
            value=value,
        )

    lines = {
        r["cost"]: r["share"]["value"] for r in call(archive, "data", "statement", alice, **params)
    }
    # area 40 of 100 m²; persons 365 of 4 × 365 person-days; per flat 1 of 2; heating as metered
    assert lines["Property tax (Grundsteuer)"] == D("240.00")
    assert lines["Water and sewage"] == D("225.00") and lines["Waste collection"] == D("100.00")
    assert lines["Heating and hot water"] == D("600.00") and "Repairs and maintenance" not in lines
    assert lines["Advance payments"] == D("-1200")
    assert lines["Balance (negative: the tenant gets money back)"] == D("-35.00")

    issued = call(archive, "action", "issue_statement", alice, **params)
    statement_doc = issued.goto.removeprefix("/documents/")
    assert set(archive.document(statement_doc).source.derived_from) == set(bills[:4])
    for doc in (statement_doc, bills[0]):  # the statement and the bills it rests on are locked
        with pytest.raises(Held):
            core.apply_metadata(doc, MetadataPatch(title="changed"), actor=f"user:{alice.id}")
    core.apply_metadata(
        bills[4], MetadataPatch(title="Not on a statement"), actor=f"user:{alice.id}"
    )
    (row,) = call(archive, "data", "statements", alice)
    assert (row["year"], row["balance"]) == (2026, D("-35.00"))
    assert call(archive, "data", "statements", bob) == []

    # Rent ledger and the figures for the tax return.
    archive.registry("vermieter-de").enqueue("ledger", {})
    archive.run_jobs()
    open_months = [r for r in call(archive, "data", "ledger", alice) if r["state"] == "Open"]
    assert len(open_months) == 2 and open_months[0]["due"] in (D("600.00"), D("850.00"))
    call(
        archive,
        "action",
        "received",
        alice,
        tenancy_id=open_months[0]["tenancy_id"],
        month=open_months[0]["month"].isoformat(),
    )
    (tax,) = call(archive, "data", "tax", alice, year=date.today().year)
    assert tax["received"]["value"] == open_months[0]["due"]
    (tax_2026,) = call(archive, "data", "tax", alice, year=2026)
    assert (tax_2026["passed_on"]["value"], tax_2026["borne"]["value"]) == (
        D("3400.00"),
        D("350.00"),
    )


def test_rent_changes_and_the_arrears_letter(archive):
    from datetime import timedelta

    from sqlalchemy import text

    alice = archive.user("alice")
    me = save(
        alice,
        ProfileIn(
            kind="person",
            name="Alice Muster",
            address={"street": "Beispielweg 1", "postcode": "12345", "city": "Musterstadt"},
        ),
    )
    call(
        archive,
        "action",
        "save_property",
        alice,
        name="Ring 1",
        street="Ring 1",
        postcode="1",
        city="X",
        profile_id=str(me.id),
    )
    prop = str(call(archive, "data", "properties", alice)[0]["id"])
    call(archive, "action", "save_unit", alice, property=prop, name="EG", area="50")
    unit = str(call(archive, "data", "units", alice)[0]["id"])
    call(
        archive,
        "action",
        "save_tenancy",
        alice,
        unit=unit,
        tenant_name="Mieter Drei",
        start_date="2024-01-01",
        rent="500",
        advance="100",
        persons="1",
    )
    tenancy = call(archive, "data", "tenancies", alice)[0]["id"]
    this_month = date.today().replace(day=1)
    call(
        archive,
        "action",
        "change_tenancy",
        alice,
        tenancy=tenancy,
        rent_from=this_month.isoformat(),
        new_rent="520",
        new_advance="120",
    )
    archive.registry("vermieter-de").enqueue("ledger", {})
    archive.run_jobs()
    (row,) = call(archive, "data", "ledger", alice)
    assert row["due"] == D("640.00")  # the new rent and advance apply from this month

    with pytest.raises(ActionError, match="Nothing is outstanding"):
        call(archive, "action", "rent_reminder", alice, tenancy=tenancy)
    last_month = (this_month - timedelta(days=1)).replace(day=1)
    with archive.registry("vermieter-de").db.session() as s:
        s.execute(
            text("INSERT INTO rent_ledger (tenancy_id, month, due) VALUES (:t, :m, 600)"),
            {"t": tenancy, "m": last_month},
        )
    made = call(archive, "action", "rent_reminder", alice, tenancy=tenancy)
    assert (
        archive.document(made.goto.removeprefix("/documents/")).title
        == "Rent reminder: Mieter Drei"
    )
