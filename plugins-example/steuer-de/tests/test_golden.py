"""The golden books: every period of three made-up businesses must match the hand-worked figures
in golden-books.yaml to the cent."""

from decimal import Decimal as D
from pathlib import Path

import pytest
import yaml
from plugin_modules import module

periods = module("periods")
HERE = Path(__file__).resolve().parent
RULES = HERE.parent / "rules"
YEAR = yaml.safe_load((RULES / "years" / "2026.yaml").read_text())
CODES = {c["id"]: c for c in yaml.safe_load((RULES / "vat-codes.yaml").read_text())["codes"]}
CHART = yaml.safe_load((RULES / "accounts-skr03.yaml").read_text())
CHART["by_id"] = {a["id"]: a for a in CHART["accounts"]}
BOOKS = yaml.safe_load((HERE / "golden-books.yaml").read_text())


def load(name: str):
    spec = BOOKS[name]
    settings = {"kind": "euer", "chart": "skr03", "vat_status": "regular"} | spec["book"]
    if "special_advance" in settings:
        settings["special_advance"] = D(settings["special_advance"])
    book = periods.Book(id=1, **settings)
    entries = []
    for direction, day, net, vat, code, account, paid in spec["entries"]:
        entries.append(
            periods.Entry(
                direction,
                day,
                D(net),
                D(vat),
                D(net) + D(vat),
                code,
                account=account,
                paid_on=paid,
                deductible=D(str(CHART["by_id"][account].get("deductible", 1))),
            )
        )
    return spec, book, entries


@pytest.mark.parametrize("name", list(BOOKS))
def test_vat_returns(name):
    spec, book, entries = load(name)
    if not spec["vat"]:
        assert {periods.vat_period(book, e) for e in entries} == {None}  # no returns at all
    for key, expected in spec["vat"].items():
        mine = [
            e
            for e in entries
            if (p := periods.vat_period(book, e)) and (p == key or p.startswith(f"{key}-"))
        ]
        result = periods.vat_figures(book, mine, CODES, YEAR["forms"]["ustva"], key)
        got = {f["field"]: f["value"] for f in result["fields"]}
        assert got == {k: D(v) for k, v in expected.items()}, key


@pytest.mark.parametrize("name", list(BOOKS))
def test_income_surplus(name):
    spec, book, entries = load(name)
    expected = dict(spec["euer"])
    year = expected.pop("year")
    surplus = D(expected.pop("surplus"))
    paid = [e for e in entries if periods.income_year(e) == year]
    result = periods.income_statement(paid, CHART, CODES, YEAR["euer"])
    assert {p["position"]: p["amount"] for p in result["positions"]} == {
        k: D(v) for k, v in expected.items()
    }
    assert result["surplus"] == surplus
