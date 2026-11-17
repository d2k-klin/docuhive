"""With other plugins on, the tax plugin lists equipment, rental income, § 35a work and
health costs."""

from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
from docuhive.sdk.testing import Archive

pytestmark = pytest.mark.integration
PLUGIN = Path(__file__).resolve().parents[1]
EXAMPLES = PLUGIN.parent


def act(archive, plugin, name, user, /, **params):
    return archive.registry(plugin).actions[name][0](user, params)


def data(archive, plugin, name, user, /, **params):
    return archive.registry(plugin).data_sources[name](user, params)


def test_equipment_and_rental_income():
    with Archive(PLUGIN, also=[EXAMPLES / "inventar", EXAMPLES / "vermieter-de"]) as archive:
        alice, bob = archive.user("alice"), archive.user("bob")
        year = date.today().year
        act(
            archive,
            "inventar",
            "save_item",
            alice,
            name="Laptop",
            category="electronics",
            purchase_date=f"{year}-02-01",
            price="1299.00",
        )
        act(
            archive,
            "inventar",
            "save_item",
            alice,
            name="Maus",
            category="electronics",
            purchase_date=f"{year}-02-01",
            price="29.00",
        )
        listed = {
            e["name"]: e["kind"] for e in data(archive, "steuer-de", "equipment", alice, year=year)
        }
        assert listed == {"Laptop": "Asset", "Maus": "Low-value item"}
        assert data(archive, "steuer-de", "equipment", bob, year=year) == []

        act(
            archive,
            "vermieter-de",
            "save_property",
            alice,
            name="Ring 1",
            street="Ring 1",
            postcode="1",
            city="X",
        )
        (row,) = data(archive, "steuer-de", "rental_income", alice, year=year)
        assert row["property"] == "Ring 1" and row["received"]["value"] == D("0")


def test_home_work_and_health_costs_on_the_household_page():
    plugins = [EXAMPLES / "handwerk", EXAMPLES / "gesundheit"]
    answer = {"labour_gross": "1000.00", "total": "1500.00", "kind": "craftsman"}
    with Archive(PLUGIN, also=plugins, ai={"*": answer}) as archive:
        alice = archive.user("alice")
        year = date.today().year
        assert data(archive, "steuer-de", "home_35a", alice, year=year) == []
        assert data(archive, "steuer-de", "health_costs", alice, year=year) == []
        work = archive.add(alice, document_type="craftsman_invoice", date=date(year, 1, 15))
        archive.emit("document.classified", document_id=work, document_type="craftsman_invoice")
        doctor = archive.add(
            alice,
            document_type="medical_bill",
            date=date(year, 1, 20),
            facts={"amount_total": ("80.00", "EUR"), "treatment_date": date(year, 1, 20)},
        )
        archive.emit("document.classified", document_id=doctor, document_type="medical_bill")
        archive.run_jobs()
        (craftsman,) = data(archive, "steuer-de", "home_35a", alice, year=year)
        assert craftsman["reduction"]["value"] == D("200.00")
        act(archive, "gesundheit", "not_claimed", alice, id=1)
        health = {
            r["label"]: r["value"]
            for r in data(archive, "steuer-de", "health_costs", alice, year=year)
        }
        assert health[f"Your own share {year}"]["value"] == D("80.00")
