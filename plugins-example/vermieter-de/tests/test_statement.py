"""The golden property: every tenancy's statement to the cent, and never more than a bill."""

from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
import yaml
from vermieter_modules import module

st = module("statement")
G = yaml.safe_load((Path(__file__).parent / "golden-property.yaml").read_text())
YEAR = tuple(G["year"])
UNITS = [st.Unit(u["id"], u["name"], D(u["area"])) for u in G["units"]]
TENANCIES = [
    st.Tenancy(
        t["id"],
        t["unit"],
        t["start"],
        t["end"],
        [(p[0], p[1]) for p in t["persons"]],
        D(t["advance"]),
    )
    for t in G["tenancies"]
]
COSTS = [st.Cost(c[0], D(c[1]), c[2], f"bill-{c[0]}") for c in G["costs"]]
METERED = {("heating", t): D(v) for t, v in G["metered"].items()}


@pytest.mark.parametrize("tenancy", TENANCIES, ids=lambda t: f"tenancy {t.id}")
def test_each_statement_to_the_cent(tenancy):
    result = st.compute(tenancy, YEAR, UNITS, TENANCIES, COSTS, G["keys"], METERED)
    expected = dict(G["expected"][tenancy.id])
    assert result["advances"] == D(expected.pop("advances"))
    assert result["balance"] == D(expected.pop("balance"))
    assert {line["cost_type"]: line["amount"] for line in result["lines"]} == {
        k: D(v) for k, v in expected.items()
    }
    assert "repairs" not in {line["cost_type"] for line in result["lines"]}


def test_tenants_never_pay_more_than_a_bill():
    shares: dict[str, D] = {}
    for t in TENANCIES:
        for line in st.compute(t, YEAR, UNITS, TENANCIES, COSTS, G["keys"], METERED)["lines"]:
            shares[line["cost_type"]] = shares.get(line["cost_type"], D(0)) + line["amount"]
    for cost in COSTS:
        if cost.cost_type in shares:
            assert shares[cost.cost_type] <= cost.amount, cost.cost_type
    # the vacancy (61 days of flat C) stays with the landlord
    assert D("1200.00") - shares["property_tax"] >= D("1200") * 80 / 300 * 61 / 365 - 1


def test_a_bill_across_two_years_is_split_by_days():
    year = (date(2026, 1, 1), date(2026, 12, 31))
    assert st.split(D("730.00"), (date(2025, 7, 1), date(2026, 6, 30)), year) == D(
        "362.00"
    )  # 181 of 365
    assert st.split(D("100.00"), (date(2026, 2, 1), date(2026, 2, 28)), year) == D("100.00")


def test_basis_is_shown_in_numbers():
    line = st.compute(TENANCIES[0], YEAR, UNITS, TENANCIES, COSTS, G["keys"], METERED)["lines"]
    basis = {x["cost_type"]: x["basis"] for x in line}
    assert (
        basis["property_tax"] == "50 m² of 300 m²" and basis["water"] == "365 of 3133 person-days"
    )


def test_advances_follow_changes_during_the_year():
    t = st.Tenancy(
        9,
        1,
        date(2026, 1, 1),
        None,
        [(date(2026, 1, 1), 1)],
        D("100"),
        [(date(2026, 7, 1), D("130"))],
    )
    assert st.advances(t, date(2026, 1, 1), date(2026, 12, 31)) == D("100") * 6 + D("130") * 6
