"""The regular-payments finder on made-up bank lines."""

from datetime import date, timedelta
from decimal import Decimal as D

from vertraege_modules import module

recurring = module("recurring")


def paid(payee, amount, day):
    return {"counterparty": payee, "amount": D(amount), "booking_date": day, "ignored_reason": None}


def test_monthly_yearly_and_noise():
    start = date(2026, 1, 15)
    rows = [paid("Streaming Beispiel", "-9.99", start + timedelta(days=30 * n)) for n in range(5)]
    rows += [
        paid("Versicherung Beispiel", "-240.00", date(2025, 2, 1)),
        paid("Versicherung Beispiel", "-240.00", date(2026, 2, 1)),
    ]
    rows += [
        paid("Supermarkt", f"-{20 + n * 13}.00", start + timedelta(days=7 * n)) for n in range(8)
    ]
    rows += [paid("Arbeitgeber", "2500.00", start + timedelta(days=30 * n)) for n in range(5)]
    found = {
        f["payee"]: (f["period"], f["amount"], f["count"])
        for f in recurring.find(rows, date(2025, 1, 1))
    }
    assert found == {
        "Streaming Beispiel": ("month", D("9.99"), 5),
        "Versicherung Beispiel": ("year", D("240.00"), 2),
    }


def test_two_monthly_payments_are_not_enough():
    rows = [paid("Neu", "-5.00", date(2026, 1, 1)), paid("Neu", "-5.00", date(2026, 2, 1))]
    assert recurring.find(rows, date(2025, 1, 1)) == []
