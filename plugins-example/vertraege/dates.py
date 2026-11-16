"""Contract dates. Pure functions; every case is in tests/test_dates.py.

A term that ends on the last day of a month keeps ending on the last day of a month: three
months before 30 June is 31 March, not 30 March. This is a reading of the contract, not a
check of what the law allows (a statutory period may be shorter).
"""

import calendar
from datetime import date, timedelta


def last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def add_months(day: date, months: int, *, keep_month_end: bool = True) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    if keep_month_end and day.day == last_day(day.year, day.month):
        return date(year, month, last_day(year, month))
    return date(year, month, min(day.day, last_day(year, month)))


def shift(day: date, amount: int, unit: str) -> date:
    if unit == "months":
        return add_months(day, amount)
    return day + timedelta(days=amount * (7 if unit == "weeks" else 1))


def term_end(start: date, minimum_months: int) -> date:
    """The last day of a term that starts on `start` and runs `minimum_months`."""
    return add_months(start, minimum_months, keep_month_end=False) - timedelta(days=1)


def notice_by(end: date, amount: int, unit: str) -> date:
    """The last day notice can arrive for a term ending on `end`."""
    return shift(end, -amount, unit)


def roll(end: date, renewal_months: int, today: date) -> date:
    """The end of the term that is running today, after automatic renewals."""
    while end < today and renewal_months > 0:
        end = add_months(end, renewal_months)
    return end


def earliest_end(
    today: date,
    amount: int,
    unit: str,
    to: str,
    end: date | None = None,
    renewal_months: int | None = None,
) -> date:
    """The first day the contract can end if notice is given today."""
    after = shift(today, amount, unit)
    if to == "term_end" and end is not None:
        while end < after and renewal_months:
            end = add_months(end, renewal_months)
        return end
    if to == "month_end":
        return date(after.year, after.month, last_day(after.year, after.month))
    if to == "quarter_end":
        month = (after.month - 1) // 3 * 3 + 3
        return date(after.year, month, last_day(after.year, month))
    return after
