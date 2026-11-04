"""query_facts: numbers come from SQL, never from the model (QA-03).

Money is grouped by currency and never summed across currencies.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import select

from docuhive import auth, db
from docuhive.ai import coretables
from docuhive.contracts import CurrentUser, SearchFilters
from docuhive.index.filters import conditions

Agg = Literal["sum", "avg", "min", "max", "count", "list"]
GroupBy = Literal["month", "year", "correspondent", "category"] | None
MAX_ROWS = 200


def _group(by: GroupBy, row: dict) -> str | None:
    d: date | None = row["date"]
    if by == "month":
        return d.strftime("%Y-%m") if d else "unknown"
    if by == "year":
        return str(d.year) if d else "unknown"
    if by in ("correspondent", "category"):
        return row[by] or "unknown"
    return None


def _num(value: object, fact_type: str) -> Decimal | None:
    if value is None:
        return None
    d = Decimal(str(value))
    return d.quantize(Decimal("0.01")) if fact_type == "money" else d.normalize()


def query_facts(
    user: CurrentUser,
    scope: SearchFilters | None,
    field: str,
    agg: Agg = "sum",
    *,
    document_type: str | None = None,
    category: str | None = None,
    correspondent: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    group_by: GroupBy = None,
    exclude_ids: set[str] | None = None,
) -> dict:
    f, d = coretables.table("doc_facts"), coretables.table("documents")
    c = coretables.table("correspondents")
    args = SearchFilters(
        document_types=[document_type] if document_type else [],
        categories=[category] if category else [],
        correspondents=[correspondent] if correspondent else [],
        date_from=date_from,
        date_to=date_to,
    )
    q = (
        select(
            d.c.id,
            d.c.title,
            d.c.document_date,
            d.c.category,
            c.c.name,
            f.c.type,
            f.c.value_text,
            f.c.value_num,
            f.c.currency,
        )
        .join(d, d.c.id == f.c.document_id)
        .join(c, c.c.id == d.c.correspondent_id, isouter=True)
        .where(
            f.c.field == field,
            d.c.status == "stored",
            auth.visible_docs(user),
            *conditions(scope),
            *conditions(args),
        )  # session scope AND tool arguments
        .order_by(d.c.document_date, d.c.id)
    )
    with db.session() as s:
        rows = [
            {
                "document_id": r[0],
                "title": r[1],
                "date": r[2],
                "category": r[3],
                "correspondent": r[4],
                "type": r[5],
                "value": r[6],
                "num": _num(r[7], r[5]),
                "currency": r[8],
            }
            for r in s.execute(q)
        ]
    excluded = 0
    if exclude_ids:
        excluded = sum(r["document_id"] in exclude_ids for r in rows)
        rows = [r for r in rows if r["document_id"] not in exclude_ids]
    buckets: dict[tuple[str | None, str | None], list[dict]] = defaultdict(list)
    for r in rows:
        buckets[(_group(group_by, r), r["currency"])].append(r)
    aggregates = []
    for (group, currency), rs in sorted(
        buckets.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))
    ):
        nums = [r["num"] for r in rs if r["num"] is not None]
        value: Decimal | int | None
        if agg == "count" or agg == "list":
            value = len(rs)
        elif not nums:
            value = None
        elif agg == "sum":
            value = sum(nums, Decimal(0))
        elif agg == "avg":
            value = (sum(nums, Decimal(0)) / len(nums)).quantize(Decimal("0.01"))
        else:
            value = min(nums) if agg == "min" else max(nums)
        aggregates.append(
            {
                "group": group,
                "currency": currency,
                "value": str(value) if isinstance(value, Decimal) else value,
                "count": len(rs),
            }
        )
    out_rows = [
        {
            "document_id": r["document_id"],
            "title": r["title"],
            "date": r["date"].isoformat() if r["date"] else None,
            "value": r["value"],
            "currency": r["currency"],
        }
        for r in rows[:MAX_ROWS]
    ]
    totals = ", ".join(
        f"{a['currency'] or ''} {a['value']}".strip()
        for a in aggregates
        if a["group"] is None and agg not in ("count", "list")
    )
    summary = f"{len(rows)} rows" + (f", {totals}" if totals else "")
    if excluded:
        summary += f", {excluded} restricted documents not included"
    return {
        "field": field,
        "agg": agg,
        "rows": out_rows,
        "aggregates": aggregates,
        "row_count": len(rows),
        "truncated": len(rows) > MAX_ROWS,
        "excluded_restricted": excluded,
        "summary": summary,
    }
