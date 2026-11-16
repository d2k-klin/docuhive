"""The arithmetic and the dates, checked by hand: these figures go to the tax office."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from plugin_modules import module
from steuer_samples import CII, UBL, zugferd_pdf

einvoice, periods = module("einvoice"), module("periods")

RULES = Path(__file__).resolve().parents[1] / "rules"
YEAR = yaml.safe_load((RULES / "years" / "2026.yaml").read_text())
CODES = {c["id"]: c for c in yaml.safe_load((RULES / "vat-codes.yaml").read_text())["codes"]}
CHART = yaml.safe_load((RULES / "accounts-skr03.yaml").read_text())
CHART["by_id"] = {a["id"]: a for a in CHART["accounts"]}
D = Decimal


def book(**changes):
    values = dict(
        id=1,
        kind="euer",
        chart="skr03",
        vat_status="regular",
        vat_period="quarterly",
        vat_basis="invoice",
    )
    return periods.Book(**{**values, **changes})


def entry(direction, net, vat, code, day=date(2026, 2, 10), **more):
    return periods.Entry(direction, day, D(net), D(vat), D(net) + D(vat), code, **more)


def test_easter_and_deadlines():
    assert [periods.easter(y) for y in (2024, 2025, 2026, 2027)] == [
        date(2024, 3, 31),
        date(2025, 4, 20),
        date(2026, 4, 5),
        date(2027, 3, 28),
    ]
    rules = YEAR["advance_return"]
    assert periods.due_date(book(), "2026-Q1", rules) == date(2026, 4, 10)  # a Friday
    monthly = book(vat_period="monthly", standing_extension=True)
    assert periods.due_date(monthly, "2026-03", rules) == date(2026, 5, 11)  # 10 May is a Sunday
    assert periods.due_date(book(), "2026-Q4", rules) == date(
        2027, 1, 11
    )  # 10 Jan 2027 is a Sunday
    assert periods.bounds("2026-Q1") == (date(2026, 1, 1), date(2026, 3, 31))
    assert periods.bounds("2026-02") == (date(2026, 2, 1), date(2026, 2, 28))
    assert periods.bounds("2026") == (date(2026, 1, 1), date(2026, 12, 31))


def test_period_assignment():
    sale = entry(
        "income",
        "100",
        "19",
        "sale_19",
        day=date(2026, 3, 30),
        service_date=date(2026, 3, 28),
        paid_on=date(2026, 4, 2),
    )
    assert periods.vat_period(book(), sale) == "2026-Q1"  # invoice basis: when it was provided
    assert (
        periods.vat_period(book(vat_basis="payment"), sale) == "2026-Q2"
    )  # payment basis: when paid
    assert periods.vat_period(book(vat_status="small_business"), sale) is None
    purchase = entry(
        "expense", "10", "1.90", "purchase_19", day=date(2026, 3, 31), paid_on=date(2026, 4, 3)
    )
    assert (
        periods.vat_period(book(vat_basis="payment"), purchase) == "2026-Q1"
    )  # input tax: invoice date
    assert (
        periods.income_year(purchase) == 2026
        and periods.income_year(entry("expense", "1", "0", None)) is None
    )


def test_a_quarter_computed_by_hand():
    entries = [
        entry("income", "1000.55", "190.10", "sale_19"),
        entry("income", "100.00", "7.00", "sale_7"),
        entry("expense", "200.00", "38.00", "purchase_19"),
        entry("expense", "10.00", "0.70", "purchase_7"),
        entry("expense", "200.00", "0.00", "purchase_rc_eu"),
    ]
    result = periods.vat_figures(book(), entries, CODES, YEAR["forms"]["ustva"], "2026-Q1")
    fields = {f["field"]: f for f in result["fields"]}
    assert fields["81"]["value"] == D("1000") and fields["81"]["tax"] == D("190.00")  # whole euros
    assert fields["86"]["value"] == D("100") and fields["86"]["tax"] == D("7.00")
    assert fields["46"]["value"] == D("200") and fields["47"]["value"] == D("38.00")
    assert fields["66"]["value"] == D("38.70") and fields["67"]["value"] == D("38.00")
    # 190.00 + 7.00 + 38.00 owed, minus 38.70 + 38.00 input tax
    assert result["payable"] == D("158.30") and fields["83"]["value"] == D("158.30")
    assert [f["field"] for f in result["fields"]] == ["81", "86", "46", "47", "66", "67", "83"]


def test_special_advance_is_deducted_in_december_only():
    monthly = book(vat_period="monthly", standing_extension=True, special_advance=D("110.00"))
    sale = [entry("income", "1000", "190", "sale_19")]
    december = periods.vat_figures(monthly, sale, CODES, YEAR["forms"]["ustva"], "2026-12")
    november = periods.vat_figures(monthly, sale, CODES, YEAR["forms"]["ustva"], "2026-11")
    assert december["payable"] == D("80.00") and november["payable"] == D("190.00")


def test_income_statement_with_a_partly_deductible_meal():
    entries = [
        entry("income", "1000", "190", "sale_19", account="8400"),
        entry("expense", "100", "19", "purchase_19", account="4650", deductible=D("0.7")),
        entry("expense", "50", "9.50", "purchase_19", account="4930"),
        entry("expense", "200", "0", "purchase_rc_eu", account="3123"),
    ]
    result = periods.income_statement(entries, CHART, CODES, YEAR["euer"])
    amounts = {p["position"]: p["amount"] for p in result["positions"]}
    assert amounts["revenue"] == D("1000") and amounts["vat_received"] == D("190")
    assert amounts["entertainment"] == D("70.00") and result["not_deductible"] == D("30.00")
    assert amounts["input_tax"] == D("28.50")  # reverse-charge input tax is not money paid out
    assert result["surplus"] == D("1190") - D("70.00") - D("50.00") - D("200.00") - D("28.50")


def test_e_invoices_are_read_exactly():
    cii = einvoice.parse_xml(CII.encode())
    assert (cii.syntax, cii.number, cii.seller, cii.seller_vat_id) == (
        "cii",
        "RE-2026-0042",
        "Bürobedarf Beispiel GmbH",
        "DE123456789",
    )
    assert (cii.issue_date, cii.service_date, cii.due_date) == (
        date(2026, 3, 2),
        date(2026, 2, 27),
        date(2026, 3, 16),
    )
    assert [(v.rate, v.base, v.tax) for v in cii.vat] == [
        (D("19"), D("100.00"), D("19.00")),
        (D("7"), D("50.00"), D("3.50")),
    ]
    assert (cii.net, cii.tax, cii.gross, cii.iban) == (
        D("150.00"),
        D("22.50"),
        D("172.50"),
        "DE89370400440532013000",
    )
    assert cii.problems == []
    ubl = einvoice.parse_xml(UBL.encode())
    assert (ubl.syntax, ubl.seller, ubl.seller_vat_id, ubl.service_date) == (
        "ubl",
        "Cloud Beispiel Ltd",
        "IE9876543X",
        date(2026, 2, 28),
    )
    assert (
        [v.category for v in ubl.vat] == ["AE"] and ubl.gross == D("200.00") and ubl.problems == []
    )
    assert einvoice.find(zugferd_pdf(CII)).number == "RE-2026-0042"
    assert einvoice.find(b"%PDF-1.7 a plain pdf") is None


def test_a_wrong_e_invoice_is_reported_not_trusted():
    broken = CII.replace("<ram:CalculatedAmount>19.00", "<ram:CalculatedAmount>91.00")
    problems = einvoice.parse_xml(broken.encode()).problems
    assert any("should be 19.00" in p for p in problems)
    assert any("VAT breakdown does not add up" in p for p in problems)
    attack = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>'
    from defusedxml import EntitiesForbidden

    with pytest.raises(EntitiesForbidden):  # entities are refused, never resolved
        einvoice.parse_xml(attack.encode())
