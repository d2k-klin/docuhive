"""Our own invoices without a database: the arithmetic, and every invoice the writer can make
read back by the reader for incoming e-invoices, to the cent."""

import itertools
import os
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
import yaml
from plugin_modules import module

invoices, einvoice = module("invoices"), module("einvoice")
RULES = Path(__file__).resolve().parents[1] / "rules"
CODES = {c["id"]: c for c in yaml.safe_load((RULES / "vat-codes.yaml").read_text())["codes"]}
SELLER = {
    "name": "Muster Design",
    "street": "Beispielweg 1",
    "postcode": "12345",
    "city": "Musterstadt",
    "country": "DE",
    "vat_id": "DE987654328",
    "tax_number": "12/345/67890",
    "email": "post@example.org",
    "phone": "+49 30 1234567",
    "iban": "DE89370400440532013000",
}
BUYER = {
    "name": "Kunde & Söhne <GmbH>",
    "street": "Hauptstraße 5",
    "postcode": "54321",
    "city": "Beispielstadt",
    "country": "DE",
    "vat_id": "ATU12345678",
    "routing_id": "04011000-12345-67",
}


def lines(spec):
    out = []
    for n, (qty, price, discount, code) in enumerate(spec, start=1):
        qty, price, discount = D(qty), D(price), D(discount)
        out.append(
            {
                "position": n,
                "description": f"Leistung {n} – “Sonderzeichen” & <Test>",
                "quantity": qty,
                "unit": "HUR",
                "unit_price": price,
                "discount_percent": discount,
                "vat_code": code,
                "account": None,
                "net": invoices.line_net(qty, price, discount),
                "net_price": invoices.net_price(price, discount),
                "category": CODES[code].get("category", "S"),
                "rate": D(str(CODES[code]["rate"])),
            }
        )
    return out


@pytest.mark.parametrize(
    ("spec", "net", "tax"),
    [
        ([("1", "100.00", "0", "sale_19")], "100.00", "19.00"),
        ([("3", "0.33", "0", "sale_19")], "0.99", "0.19"),  # 0.1881 → 0.19
        # rounded once per rate: 3 × 0.05 → 0.15 net, 0.0285 → 0.03 (per line it would be 0.03)
        ([("1", "0.05", "0", "sale_19")] * 3, "0.15", "0.03"),
        ([("1", "10.00", "0", "sale_19"), ("1", "10.00", "0", "sale_7")], "20.00", "2.60"),
        ([("2.5", "80.00", "10", "sale_19")], "180.00", "34.20"),
        ([("1", "0.125", "0", "sale_19")], "0.13", "0.02"),  # half up at the cent
    ],
)
def test_totals(spec, net, tax):
    result = invoices.totals(lines(spec), CODES)
    assert (result["net"], result["tax"]) == (D(net), D(tax))
    assert result["gross"] == D(net) + D(tax)


CASES = list(
    itertools.product(
        [
            [("1", "1200.00", "0", "sale_19")],
            [("2", "99.95", "0", "sale_19"), ("1", "49.00", "0", "sale_7")],
            [("1", "500.00", "0", "sale_eu_service")],
            [("3", "250.00", "0", "sale_eu_goods")],
            [("1", "800.00", "0", "sale_small_business")],
            [("7.5", "85.00", "5", "sale_19"), ("1", "0.01", "0", "sale_7")],
            [("1", "1.00", "0", "sale_19")] * 100,
            [("12", "33.33", "12.5", "sale_19"), ("4", "17.17", "0", "sale_7")],
        ],
        ["380", "381"],
        ["zugferd", "xrechnung"],
        [None, "with period"],
    )
)


@pytest.mark.parametrize(("spec", "type_code", "flavour", "period"), CASES)
def test_writer_and_reader_agree(spec, type_code, flavour, period):
    ls = lines(spec)
    calc = invoices.totals(ls, CODES)
    model = {
        "number": "RE-2026-0042",
        "type_code": type_code,
        "issue_date": date(2026, 3, 31),
        "currency": "EUR",
        "seller": SELLER,
        "buyer": BUYER,
        "service_from": date(2026, 3, 1) if period else None,
        "service_to": date(2026, 3, 31),
        "due_date": date(2026, 4, 14),
        "payment_text": "Zahlbar bis 14.04.2026.",
        "lines": ls,
        "breakdown": [
            b | {"reason": "Grund" if b["category"] != "S" else None} for b in calc["breakdown"]
        ],
        "net": calc["net"],
        "tax": calc["tax"],
        "gross": calc["gross"],
        "refers_to": {"number": "RE-2026-0041", "issue_date": date(2026, 3, 1)}
        if type_code == "381"
        else None,
    }
    xml = einvoice.write_cii(model, flavour)
    if out := os.environ.get("EINVOICE_CORPUS_DIR"):  # for the official validator in CI
        name = f"{flavour}-{type_code}-{len(ls)}-{period or 'day'}-{hash(str(spec)) & 0xFFFF}.xml"
        (Path(out) / name).write_bytes(xml)
    read = einvoice.parse_xml(xml)
    assert read.problems == []
    assert (read.number, read.type_code, read.issue_date) == (
        "RE-2026-0042",
        type_code,
        date(2026, 3, 31),
    )
    assert (read.net, read.tax, read.gross, read.payable) == (
        calc["net"],
        calc["tax"],
        calc["gross"],
        calc["gross"],
    )
    assert sorted((v.category, v.rate, v.base, v.tax) for v in read.vat) == sorted(
        (b["category"], b["rate"], b["base"], b["tax"]) for b in calc["breakdown"]
    )
    assert (read.seller, read.seller_vat_id, read.buyer) == (
        SELLER["name"],
        SELLER["vat_id"],
        BUYER["name"],
    )
    assert (read.iban, read.due_date, read.service_date) == (
        SELLER["iban"],
        date(2026, 4, 14),
        date(2026, 3, 31),
    )


def test_corpus_size():
    assert len(CASES) >= 60  # the design's release gate counts at least 60 generated invoices


def test_pre_issue_checks_name_what_is_missing():
    book = {"vat_status": "small_business"}
    inv = {
        "kind": "invoice",
        "service_from": None,
        "service_to": None,
        "refers_to_invoice_id": None,
        "gross_estimate": D("500"),
    }
    problems = invoices.checks(
        inv,
        lines([("1", "500", "0", "sale_19")]),
        {},
        {"e_invoice_format": "xrechnung"},
        book,
        CODES,
    )
    text = " ".join(problems)
    for expected in (
        "Your name and address",
        "tax number or VAT id",
        "customer's name",
        "small-business",
        "date or period",
        "routing id",
        "bank account",
    ):
        assert expected in text
    good = invoices.checks(
        inv | {"service_to": date(2026, 3, 1)},
        lines([("1", "500", "0", "sale_small_business")]),
        SELLER,
        BUYER | {"e_invoice_format": "zugferd"},
        book,
        CODES,
    )
    assert good == []
