from datetime import date
from decimal import Decimal

import pytest
from docuhive.agents import validators as v

MONEY = [
    ("84,20 €", None, "84.20", "EUR"),
    ("1.234,56 €", None, "1234.56", "EUR"),
    ("1,234.56", "USD", "1234.56", "USD"),
    ("1234.56 €", None, "1234.56", "EUR"),
    ("EUR 84.20", None, "84.20", "EUR"),
    ("€ 12", None, "12.00", "EUR"),
    ("$19.99", None, "19.99", "USD"),
    ("£ 7,50", None, "7.50", "GBP"),
    ("CHF 1'250.00", None, "1250.00", "CHF"),
    ("1.234.567,89", None, "1234567.89", "EUR"),
    ("1,234", None, "1234.00", "EUR"),
    ("1.234", None, "1234.00", "EUR"),
    ("0,99", "€", "0.99", "EUR"),
    ("Gesamt: 1.012,40 EUR", None, "1012.40", "EUR"),
    ("12.5", "eur", "12.50", "EUR"),
]


@pytest.mark.parametrize(("raw", "cur", "value", "currency"), MONEY)
def test_money(raw, cur, value, currency):
    assert v.parse_money(raw, cur) == (Decimal(value), currency)


@pytest.mark.parametrize("raw", ["0,00 €", "-5", "abc", "€"])
def test_money_invalid(raw):
    with pytest.raises(v.Invalid):
        v.parse_money(raw)


DATES = [
    ("2025-11-01", date(2025, 11, 1)),
    ("01.11.2025", date(2025, 11, 1)),
    ("1.11.2025", date(2025, 11, 1)),
    ("01/11/2025", date(2025, 11, 1)),
    ("01.11.25", date(2025, 11, 1)),
    ("1. November 2025", date(2025, 11, 1)),
    ("3. März 2024", date(2024, 3, 3)),
    ("15 Dezember 2023", date(2023, 12, 15)),
    ("November 1, 2025", date(2025, 11, 1)),
    ("Nov 1st, 2025", date(2025, 11, 1)),
    ("March 3 2024", date(2024, 3, 3)),
]


@pytest.mark.parametrize(("raw", "expected"), DATES)
def test_dates(raw, expected):
    assert v.parse_date(raw, today=date(2026, 11, 3)) == expected


@pytest.mark.parametrize("raw", ["1949-12-31", "2030-01-01", "31.02.2025", "soon", "13/13/2025"])
def test_dates_invalid(raw):
    with pytest.raises(v.Invalid):
        v.parse_date(raw, today=date(2026, 11, 3))


IBANS_OK = [
    "DE89 3704 0044 0532 0130 00",
    "GB82WEST12345698765432",
    "AT61 1904 3002 3457 3201",
    "ch9300762011623852957",
]
IBANS_BAD = ["DE89370400440532013001", "DE8937040044053201300", "XX00", "GB82 WEST 1234"]


@pytest.mark.parametrize("raw", IBANS_OK)
def test_iban_ok(raw):
    assert v.parse_iban(raw) == raw.replace(" ", "").upper()


@pytest.mark.parametrize("raw", IBANS_BAD)
def test_iban_bad(raw):
    with pytest.raises(v.Invalid):
        v.parse_iban(raw)


@pytest.mark.parametrize(("raw", "expected"), [("12,5", "12.5"), ("90", "90"), ("1 000", "1000")])
def test_number(raw, expected):
    assert v.parse_number(raw) == Decimal(expected)


def test_string_trimmed_and_capped():
    assert v.clean_string("  Stadtwerke   Musterstadt ") == "Stadtwerke Musterstadt"
    assert len(v.clean_string("x" * 500)) == 200


def test_similarity_matches_pg_trgm_spirit():
    assert v.similarity("Stadtwerke Musterstadt", "Stadtwerke Musterstadt") == 1.0
    assert (
        v.best_match("Stadtwerke Musterstadt GmbH", ["Stadtwerke Musterstadt", "Telekom"])
        == "Stadtwerke Musterstadt"
    )
    assert v.best_match("Allianz", ["Stadtwerke Musterstadt"]) is None


def test_fact_dates_may_be_decades_ahead():
    assert v.canonical("date", "30.06.2031") == ("2031-06-30", None)
    with pytest.raises(v.Invalid):
        v.parse_date("30.06.2031", today=date(2026, 11, 3))  # but not as an issue date


def test_canonical_by_type():
    assert v.canonical("money", "84,20", None) == ("84.20", "EUR")
    assert v.canonical("date", "20.11.2025") == ("2025-11-20", None)
    assert v.canonical("iban", "de89 3704 0044 0532 0130 00") == ("DE89370400440532013000", None)
