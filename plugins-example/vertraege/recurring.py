"""Regular payments: the same payee, a similar amount, at a steady rhythm. Pure functions.

Used to say "you pay this every month and the archive has no contract for it". A hint for a
person to check, never a contract by itself.
"""

import re
from datetime import date
from decimal import Decimal
from statistics import median

RHYTHMS = (("month", 25, 35, 3), ("quarter", 80, 100, 3), ("year", 350, 380, 2))


def payee_key(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def find(transactions: list[dict], since: date) -> list[dict]:
    """[{payee, amount, period, last, count}] for outgoing payments since `since`."""
    groups: dict[str, list[dict]] = {}
    for t in transactions:
        if t["amount"] < 0 and t["booking_date"] >= since and not t.get("ignored_reason"):
            if key := payee_key(t["counterparty"]):
                groups.setdefault(key, []).append(t)
    found = []
    for rows in groups.values():
        rows.sort(key=lambda r: r["booking_date"])
        amounts = [-Decimal(str(r["amount"])) for r in rows]
        typical = Decimal(str(median(amounts)))
        if any(abs(a - typical) > typical / 10 for a in amounts):
            continue  # amounts vary too much: probably not one contract
        gaps = [
            (b["booking_date"] - a["booking_date"]).days
            for a, b in zip(rows, rows[1:], strict=False)
        ]
        if not gaps:
            continue
        gap = median(gaps)
        for period, low, high, least in RHYTHMS:
            if low <= gap <= high and len(rows) >= least:
                found.append(
                    {
                        "payee": rows[-1]["counterparty"],
                        "amount": typical.quantize(Decimal("0.01")),
                        "period": period,
                        "last": rows[-1]["booking_date"],
                        "count": len(rows),
                    }
                )
                break
    return sorted(found, key=lambda f: -f["amount"])
