"""The date rules for answering official letters."""

from datetime import date as d

import pytest
from behoerden_modules import module

deadlines = module("deadlines")


@pytest.mark.parametrize(
    ("year", "sunday"), [(2025, d(2025, 4, 20)), (2026, d(2026, 4, 5)), (2027, d(2027, 3, 28))]
)
def test_easter(year, sunday):
    assert deadlines.easter(year) == sunday


@pytest.mark.parametrize(
    ("letter", "amount", "unit", "delivered", "expected"),
    [
        # Delivered Fri 6 March; one month later is Easter Monday, so Tuesday.
        (d(2026, 3, 2), 1, "months", None, d(2026, 4, 7)),
        (d(2026, 1, 30), 1, "months", None, d(2026, 3, 3)),
        # Delivery would fall on a Sunday: it counts from Monday.
        (d(2026, 6, 3), 1, "months", None, d(2026, 7, 8)),
        # A month later is a Sunday in January.
        (d(2026, 12, 20), 1, "months", None, d(2027, 1, 25)),
        # Formal service: two weeks from the date on the envelope.
        (d(2026, 5, 1), 2, "weeks", d(2026, 5, 15), d(2026, 5, 29)),
        (d(2026, 3, 2), 14, "days", None, d(2026, 3, 20)),
    ],
)
def test_respond_by(letter, amount, unit, delivered, expected):
    got = deadlines.respond_by(letter, amount, unit, delivery_days=4, delivered=delivered)
    assert got == expected


def test_month_ends_and_unknown_units():
    assert deadlines.add_months(d(2026, 1, 31), 1) == d(2026, 2, 28)
    assert deadlines.add_months(d(2028, 1, 31), 1) == d(2028, 2, 29)
    with pytest.raises(ValueError):
        deadlines.respond_by(d(2026, 1, 1), 1, "years", delivery_days=4)
