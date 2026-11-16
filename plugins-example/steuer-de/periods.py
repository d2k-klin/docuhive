"""Periods and their figures. Pure functions over bookings: no database, no AI, Decimal only.

These rules decide which period a booking counts in. They follow the general rules (invoice
basis: when the service was provided; payment basis: when the money arrived; income-surplus:
when the money moved) and must be confirmed by a tax advisor before real use.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
EURO = Decimal("1")


@dataclass
class Book:
    id: int
    kind: str  # euer, hand_over, private
    chart: str | None
    vat_status: str  # regular, small_business, exempt
    vat_period: str  # monthly, quarterly, yearly, none
    vat_basis: str  # invoice, payment
    standing_extension: bool = False
    special_advance: Decimal = Decimal(0)
    federal_state: str | None = None

    @property
    def files_vat(self) -> bool:
        return self.vat_status == "regular" and self.vat_period != "none"


@dataclass
class Entry:
    direction: str  # income, expense
    entry_date: date
    net: Decimal
    vat: Decimal
    gross: Decimal
    vat_code: str | None
    account: str | None = None
    service_date: date | None = None
    paid_on: date | None = None
    deductible: Decimal = Decimal(1)
    id: int | None = None
    document_id: str | None = None


def key(period: str, day: date) -> str:
    if period == "monthly":
        return f"{day.year}-{day.month:02d}"
    if period == "quarterly":
        return f"{day.year}-Q{(day.month - 1) // 3 + 1}"
    return str(day.year)


def bounds(period_key: str) -> tuple[date, date]:
    """First and last day of a period key such as 2026-03, 2026-Q1 or 2026."""
    if "-Q" in period_key:
        year, q = int(period_key[:4]), int(period_key[-1])
        start = date(year, 3 * q - 2, 1)
        end_month = 3 * q
    elif "-" in period_key:
        year, month = int(period_key[:4]), int(period_key[5:7])
        start, end_month = date(year, month, 1), month
    else:
        year = int(period_key)
        start, end_month = date(year, 1, 1), 12
    following = date(year + (end_month == 12), end_month % 12 + 1, 1)
    return start, following - timedelta(days=1)


def vat_period(book: Book, entry: Entry) -> str | None:
    """The VAT period a booking counts in, or None (no VAT returns, or not paid yet)."""
    if not book.files_vat:
        return None
    if entry.direction == "income":
        when = (
            entry.paid_on
            if book.vat_basis == "payment"
            else (entry.service_date or entry.entry_date)
        )
    else:
        when = entry.entry_date  # input tax: when the invoice is there
    return key(book.vat_period, when) if when else None


def income_year(entry: Entry) -> int | None:
    """Income-surplus accounting counts money when it moves."""
    return entry.paid_on.year if entry.paid_on else None


def _round(value: Decimal, how: str) -> Decimal:
    if how == "euro_down":
        return value.quantize(EURO, rounding=ROUND_DOWN)
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def vat_figures(
    book: Book, entries: list[Entry], codes: dict[str, dict], form: dict, period_key: str
) -> dict:
    """The advance return for one period: every form field with its exact and form value."""
    bases: dict[str, Decimal] = {}
    taxes: dict[str, Decimal] = {}
    inputs: dict[str, Decimal] = {}
    counts: dict[str, int] = {}
    for e in entries:
        code = codes.get(e.vat_code or "")
        if code is None:
            continue
        rate = Decimal(str(code.get("rate", 0)))
        if field := code.get("base"):
            bases[field] = bases.get(field, Decimal(0)) + e.net
            counts[field] = counts.get(field, 0) + 1
        if field := code.get("tax"):  # reverse charge: the buyer owes the VAT
            taxes[field] = taxes.get(field, Decimal(0)) + (e.net * rate / 100)
            counts[field] = counts.get(field, 0) + 1
        if field := code.get("input"):
            amount = e.net * rate / 100 if code.get("reverse_charge") else e.vat
            inputs[field] = inputs.get(field, Decimal(0)) + amount
            counts[field] = counts.get(field, 0) + 1
    fields: list[dict] = []
    output_tax = Decimal(0)
    input_tax = Decimal(0)
    for number, spec in form.items():
        kind = spec["kind"]
        if kind == "base" and number in bases:
            value = _round(bases[number], spec["round"])
            tax = (value * Decimal(str(spec.get("rate", 0))) / 100).quantize(CENT, ROUND_HALF_UP)
            output_tax += tax
            fields.append(
                {
                    "field": number,
                    "label": spec["label"],
                    "exact": bases[number],
                    "value": value,
                    "tax": tax if spec.get("rate") else None,
                    "entries": counts[number],
                }
            )
        elif kind == "tax" and number in taxes:
            value = _round(taxes[number], spec["round"])
            output_tax += value
            fields.append(
                {
                    "field": number,
                    "label": spec["label"],
                    "exact": taxes[number],
                    "value": value,
                    "tax": None,
                    "entries": counts[number],
                }
            )
        elif kind == "input" and number in inputs:
            value = _round(inputs[number], spec["round"])
            input_tax += value
            fields.append(
                {
                    "field": number,
                    "label": spec["label"],
                    "exact": inputs[number],
                    "value": value,
                    "tax": None,
                    "entries": counts[number],
                }
            )
    deduct = Decimal(0)
    last_of_year = period_key.endswith(("-12", "-Q4")) or "-" not in period_key
    if (
        book.standing_extension
        and book.vat_period == "monthly"
        and last_of_year
        and book.special_advance
    ):
        deduct = book.special_advance
        fields.append(
            {
                "field": "39",
                "label": form["39"]["label"],
                "exact": deduct,
                "value": deduct,
                "tax": None,
                "entries": 0,
            }
        )
    payable = output_tax - input_tax - deduct
    fields.append(
        {
            "field": "83",
            "label": form["83"]["label"],
            "exact": payable,
            "value": payable,
            "tax": None,
            "entries": len(entries),
        }
    )
    order = list(form)
    fields.sort(key=lambda f: order.index(f["field"]) if f["field"] in order else 99)
    return {
        "period": period_key,
        "fields": fields,
        "output_tax": output_tax,
        "input_tax": input_tax,
        "payable": payable,
    }


def income_statement(
    entries: list[Entry], chart: dict, codes: dict[str, dict], positions: dict
) -> dict:
    """The income-surplus statement for a year: income and expenses by position."""
    totals: dict[str, Decimal] = {
        p: Decimal(0) for p in positions["income"] + positions["expenses"]
    }
    not_deductible = Decimal(0)
    for e in entries:
        account = chart["by_id"].get(str(e.account or ""), {})
        position = account.get("euer") or ("other_income" if e.direction == "income" else "other")
        if e.direction == "income":
            totals[position] = totals.get(position, Decimal(0)) + e.net
            totals["vat_received"] += e.vat
        else:
            share = (e.net * e.deductible).quantize(CENT, ROUND_HALF_UP)
            totals[position] = totals.get(position, Decimal(0)) + share
            not_deductible += e.net - share
            code = codes.get(e.vat_code or "", {})
            if code.get("input") and not code.get("reverse_charge"):
                totals["input_tax"] += e.vat
    income = sum((totals[p] for p in positions["income"]), Decimal(0))
    expenses = sum((totals[p] for p in positions["expenses"]), Decimal(0))
    return {
        "positions": [
            {"position": p, "label": positions["labels"][p], "side": side, "amount": totals[p]}
            for side in ("income", "expenses")
            for p in positions[side]
            if totals[p]
        ],
        "income": income,
        "expenses": expenses,
        "surplus": income - expenses,
        "not_deductible": not_deductible,
    }


# Deadlines ------------------------------------------------------------------------------------


def easter(year: int) -> date:
    """Gregorian Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month = (h + m - 7 * n + 114) // 31
    day = (h + m - 7 * n + 114) % 31 + 1
    return date(year, month, day)


def holidays(year: int) -> set[date]:
    """Public holidays in every German state. ponytail: state-only holidays are not counted;
    a deadline on one of those is shown a day early, which is safe."""
    e = easter(year)
    return {
        date(year, 1, 1),
        e - timedelta(days=2),
        e + timedelta(days=1),
        date(year, 5, 1),
        e + timedelta(days=39),
        e + timedelta(days=50),
        date(year, 10, 3),
        date(year, 12, 25),
        date(year, 12, 26),
    }


def next_working_day(day: date) -> date:
    while day.weekday() >= 5 or day in holidays(day.year):
        day += timedelta(days=1)
    return day


def due_date(book: Book, period_key: str, rules: dict) -> date:
    """When the advance return for a period is due (AO § 108 (3): moved to the next working day)."""
    end = bounds(period_key)[1]
    months = rules["extension_months"] if book.standing_extension else 0
    month = end.month + 1 + months
    year = end.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return next_working_day(date(year, month, int(rules["due_day"])))
