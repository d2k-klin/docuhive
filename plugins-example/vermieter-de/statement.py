"""The service-charge statement, as arithmetic. Pure functions, Decimal only; the golden property
in tests/golden-property.yaml is computed by hand.

Which costs may be passed on, and by which key, is the landlord's choice under the tenancy
agreement and the law; this module only divides. Every share is rounded down to the cent, so
the tenants together never pay more than a bill; the rest, and the vacancies, stay with the
landlord.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal

CENT = Decimal("0.01")


@dataclass
class Unit:
    id: int
    name: str
    area: Decimal
    shares: dict[str, Decimal] = field(default_factory=dict)


@dataclass
class Tenancy:
    id: int
    unit_id: int
    start: date
    end: date | None
    persons: list[tuple[date, int]]  # (from, number of persons), sorted
    monthly_advance: Decimal = Decimal(0)


@dataclass
class Cost:
    cost_type: str
    amount: Decimal
    unit_id: int | None = None
    document_id: str | None = None


def num(value: Decimal) -> str:
    """40.00 → "40", 62.5 → "62.5": numbers as people write them."""
    return format(value.normalize(), "f")


def overlap(
    a_start: date, a_end: date, b_start: date, b_end: date | None
) -> tuple[date, date] | None:
    start, end = max(a_start, b_start), min(a_end, b_end or a_end)
    return (start, end) if start <= end else None


def days(span: tuple[date, date] | None) -> int:
    return (span[1] - span[0]).days + 1 if span else 0


def person_days(t: Tenancy, start: date, end: date) -> int:
    span = overlap(start, end, t.start, t.end)
    if span is None:
        return 0
    total = 0
    for n, (since, persons) in enumerate(t.persons):
        until = t.persons[n + 1][0] - timedelta(days=1) if n + 1 < len(t.persons) else span[1]
        total += days(overlap(span[0], span[1], since, until)) * persons
    return total


def split(amount: Decimal, period: tuple[date, date], year: tuple[date, date]) -> Decimal:
    """The part of a bill that belongs to the accounting year, by days."""
    inside = days(overlap(year[0], year[1], period[0], period[1]))
    return (amount * inside / days(period)).quantize(CENT, ROUND_DOWN)


def advances(t: Tenancy, start: date, end: date) -> Decimal:
    """Advance payments as agreed: one for each month whose first day falls in the period."""
    span = overlap(start, end, t.start, t.end)
    if span is None:
        return Decimal(0)
    months, day = 0, date(span[0].year, span[0].month, 1)
    while day <= span[1]:
        months += day >= span[0]
        day = date(day.year + (day.month == 12), day.month % 12 + 1, 1)
    return t.monthly_advance * months


def compute(
    target: Tenancy,
    year: tuple[date, date],
    units: list[Unit],
    tenancies: list[Tenancy],
    costs: list[Cost],
    keys: dict[str, dict],
    consumption: dict[tuple[str, int], Decimal],
) -> dict:
    """The statement for one tenancy and year: a line per passable cost type, and the balance.
    `keys`: {cost_type: {"key": area|persons|units|consumption|metered|direct|share:<name>,
    "passable": bool}}. `consumption`: {(cost_type, tenancy id): value}."""
    period = overlap(year[0], year[1], target.start, target.end)
    if period is None:
        raise ValueError("The tenancy did not run in this year")
    time = Decimal(days(period)) / Decimal(days(year))
    unit = next(u for u in units if u.id == target.unit_id)
    lines = []
    for cost_type in sorted({c.cost_type for c in costs}):
        rule = keys.get(cost_type, {})
        if not rule.get("passable"):
            continue
        key = rule["key"]
        items = [c for c in costs if c.cost_type == cost_type]
        total = sum((c.amount for c in items), Decimal(0))
        if key == "area":
            whole = sum((u.area for u in units), Decimal(0))
            share, basis = unit.area / whole * time, f"{num(unit.area)} m² of {num(whole)} m²"
        elif key == "units":
            share, basis = time / len(units), f"1 of {len(units)} flats"
        elif key.startswith("share:"):
            name = key.split(":", 1)[1]
            whole = sum((u.shares.get(name, Decimal(0)) for u in units), Decimal(0))
            mine = unit.shares.get(name, Decimal(0))
            share, basis = mine / whole * time, f"{num(mine)} of {num(whole)} ({name})"
        elif key == "persons":
            mine = person_days(target, *year)
            whole = sum(person_days(t, *year) for t in tenancies)
            share, basis = Decimal(mine) / Decimal(whole), f"{mine} of {whole} person-days"
        elif key == "consumption":
            mine = consumption.get((cost_type, target.id), Decimal(0))
            whole = sum((v for (c, _), v in consumption.items() if c == cost_type), Decimal(0))
            share, basis = (
                (mine / whole if whole else Decimal(0)),
                f"{num(mine)} of {num(whole)} measured",
            )
        elif key == "metered":  # heating: the metering company's amount for this tenancy
            amount = consumption.get((cost_type, target.id), Decimal(0))
            lines.append(
                {
                    "cost_type": cost_type,
                    "total": total,
                    "key": key,
                    "basis": "per the metering statement",
                    "time": None,
                    "amount": amount,
                    "documents": [c.document_id for c in items if c.document_id],
                }
            )
            continue
        elif key == "direct":
            items = [c for c in items if c.unit_id == unit.id]
            total = sum((c.amount for c in items), Decimal(0))
            share, basis = time, f"for {unit.name} only"
            if not items:
                continue
        else:
            raise ValueError(f"Unknown key {key} for {cost_type}")
        lines.append(
            {
                "cost_type": cost_type,
                "total": total,
                "key": key,
                "basis": basis,
                "time": time if key not in ("persons", "consumption") else None,
                "amount": (total * share).quantize(CENT, ROUND_DOWN),
                "documents": [c.document_id for c in items if c.document_id],
            }
        )
    costs_total = sum((line["amount"] for line in lines), Decimal(0))
    paid = advances(target, *year)
    return {
        "period": period,
        "days": days(period),
        "lines": lines,
        "costs": costs_total,
        "advances": paid,
        "balance": costs_total - paid,
    }
