"""With the inventory and landlord plugins on, the tax plugin lists equipment and rental income."""

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
