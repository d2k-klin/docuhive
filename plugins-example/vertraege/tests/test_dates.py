"""The date table: every rule the contract list and the letters rely on."""

from datetime import date as d

import pytest
from vertraege_modules import module

dates = module("dates")


@pytest.mark.parametrize(
    ("end", "amount", "unit", "expected"),
    [
        (d(2026, 12, 31), 3, "months", d(2026, 9, 30)),  # month end stays month end
        (d(2026, 6, 30), 3, "months", d(2026, 3, 31)),
        (d(2026, 3, 31), 1, "months", d(2026, 2, 28)),
        (d(2028, 3, 31), 1, "months", d(2028, 2, 29)),  # leap year
        (d(2026, 3, 15), 1, "months", d(2026, 2, 15)),
        (d(2026, 3, 30), 1, "months", d(2026, 2, 28)),  # no 30 February
        (d(2026, 12, 31), 6, "weeks", d(2026, 11, 19)),
        (d(2026, 12, 31), 14, "days", d(2026, 12, 17)),
    ],
)
def test_notice_by(end, amount, unit, expected):
    assert dates.notice_by(end, amount, unit) == expected


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (d(2026, 1, 1), 24, d(2027, 12, 31)),
        (d(2026, 1, 31), 12, d(2027, 1, 30)),
        (d(2026, 2, 28), 1, d(2026, 3, 27)),  # a start at month end is not a month end rule
        (d(2028, 2, 29), 12, d(2029, 2, 27)),
    ],
)
def test_term_end(start, months, expected):
    assert dates.term_end(start, months) == expected


def test_renewals_roll_the_term_forward():
    assert dates.roll(d(2025, 6, 30), 12, d(2026, 11, 16)) == d(2027, 6, 30)
    assert dates.roll(d(2026, 12, 31), 12, d(2026, 11, 16)) == d(2026, 12, 31)
    assert dates.roll(d(2025, 6, 30), 0, d(2026, 11, 16)) == d(2025, 6, 30)  # no renewal: ended


@pytest.mark.parametrize(
    ("to", "expected"),
    [
        ("month_end", d(2027, 2, 28)),
        ("quarter_end", d(2027, 3, 31)),
        ("any_day", d(2027, 2, 16)),
        ("term_end", d(2027, 6, 30)),  # notice too late for 31 Dec 2026? no: next term end
    ],
)
def test_earliest_end(to, expected):
    today = d(2026, 11, 16)
    assert dates.earliest_end(today, 3, "months", to, d(2026, 12, 31), 6) == expected
