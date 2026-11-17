"""Answer deadlines of official letters. Pure: dates in, dates out."""

import calendar
from datetime import date, timedelta


def easter(year: int) -> date:
    """Easter Sunday (Gregorian calendar, anonymous algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


def holidays(year: int) -> set[date]:
    """Public holidays in every German state."""
    e = easter(year)
    return {
        date(year, 1, 1),
        e - timedelta(days=2),  # Good Friday
        e + timedelta(days=1),  # Easter Monday
        date(year, 5, 1),
        e + timedelta(days=39),  # Ascension
        e + timedelta(days=50),  # Whit Monday
        date(year, 10, 3),
        date(year, 12, 25),
        date(year, 12, 26),
    }


def working_day(day: date) -> date:
    """The day itself, or the next day that is neither a weekend nor a holiday."""
    while day.weekday() >= 5 or day in holidays(day.year):
        day += timedelta(days=1)
    return day


def add_months(day: date, months: int) -> date:
    """One month after 31 January is 28/29 February (§ 188 (3) BGB)."""
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def respond_by(
    letter_date: date, amount: int, unit: str, *, delivery_days: int, delivered: date | None = None
) -> date:
    """The last day to answer: delivered (the date written on the envelope of a formal service,
    else the letter date plus the delivery days, moved to a working day) plus the period, moved
    to a working day."""
    start = delivered or working_day(letter_date + timedelta(days=delivery_days))
    if unit == "months":
        end = add_months(start, amount)
    elif unit == "weeks":
        end = start + timedelta(weeks=amount)
    elif unit == "days":
        end = start + timedelta(days=amount)
    else:
        raise ValueError(f"unknown period unit: {unit}")
    return working_day(end)
