"""Near-duplicate detection: the same document arriving twice in different forms, such as an
email PDF and a paper scan. Byte-identical files are caught at ingest by SHA-256; this compares
what the documents say instead.

Signals between two documents of the same owner:
- same_sender: the same correspondent
- same_amount: a money fact with the same value and currency
- close_date: document dates at most CLOSE_DAYS apart
- similar_content: embedding similarity of at least SIMILAR (only when embeddings exist)

Dates that are both known and further apart rule a pair out: a monthly invoice from the same
sender, with the same amount and template, is a new period, not a copy. Otherwise a pair needs
two of the other three signals (three when a date is missing), or near-identical content.
Nothing is ever deleted; a person confirms or dismisses each pair.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select

from docuhive import db, jobs
from docuhive.ai import coretables
from docuhive.contracts import CurrentUser

CLOSE_DAYS = 7
SIMILAR = 0.92
NEAR_IDENTICAL = 0.97
MAX_CANDIDATES = 200
STRONG = {"same_sender", "same_amount", "similar_content"}


def signals(
    doc: dict, other: dict, amounts: set, other_amounts: set, similarity: float | None
) -> list[str]:
    reasons = []
    if doc["correspondent_id"] is not None and doc["correspondent_id"] == other["correspondent_id"]:
        reasons.append("same_sender")
    if amounts & other_amounts:
        reasons.append("same_amount")
    if doc["document_date"] and other["document_date"]:
        if abs((doc["document_date"] - other["document_date"]).days) <= CLOSE_DAYS:
            reasons.append("close_date")
    if similarity is not None and similarity >= SIMILAR:
        reasons.append("similar_content")
    return reasons


def is_duplicate(reasons: list[str], similarity: float | None, dates_known: bool) -> bool:
    if dates_known and "close_date" not in reasons:
        return False
    if similarity is not None and similarity >= NEAR_IDENTICAL:
        return True
    return len(STRONG & set(reasons)) >= (2 if dates_known else 3)


def money(session: Any, ids: list[str]) -> dict[str, set[tuple[str, str | None]]]:
    f = coretables.table("doc_facts")
    out: dict[str, set[tuple[str, str | None]]] = {}
    for doc_id, value, currency in session.execute(
        select(f.c.document_id, f.c.value_text, f.c.currency).where(
            f.c.document_id.in_(ids), f.c.type == "money"
        )
    ):
        out.setdefault(doc_id, set()).add((value, currency))
    return out


def similarities(owner_id: int, doc_id: str) -> dict[str, float]:
    from docuhive.index import semantic

    if not semantic.available():
        return {}
    user = CurrentUser(id=owner_id, username="owner", role="member")
    return {hit.document_id: hit.score for hit in semantic.similar(user, doc_id, k=10)}


def scan(doc_id: str) -> int:
    """Record new near-duplicate pairs for one document; returns how many were added."""
    d, pairs = coretables.table("documents"), coretables.table("duplicate_pairs")
    columns = [d.c.id, d.c.owner_id, d.c.correspondent_id, d.c.document_date]
    live = and_(d.c.status == "stored", d.c.deleted_at.is_(None))
    with db.session() as session:
        row = session.execute(select(*columns).where(d.c.id == doc_id, live)).first()
        if row is None:
            return 0
        doc = row._asdict()
    similar = similarities(doc["owner_id"], doc_id)
    near: list[Any] = [d.c.id.in_(list(similar))]
    if doc["correspondent_id"] is not None:
        near.append(d.c.correspondent_id == doc["correspondent_id"])
    if doc["document_date"]:
        window = timedelta(days=CLOSE_DAYS)
        near.append(
            d.c.document_date.between(doc["document_date"] - window, doc["document_date"] + window)
        )
    added = 0
    with db.session() as session:
        others = [
            r._asdict()
            for r in session.execute(
                select(*columns)
                .where(live, d.c.owner_id == doc["owner_id"], d.c.id != doc_id, or_(*near))
                .order_by(d.c.id)
                .limit(MAX_CANDIDATES)
            )
        ]
        amounts = money(session, [doc_id, *(o["id"] for o in others)])
        for other in others:
            score = similar.get(other["id"])
            reasons = signals(
                doc, other, amounts.get(doc_id, set()), amounts.get(other["id"], set()), score
            )
            dates_known = bool(doc["document_date"] and other["document_date"])
            if not is_duplicate(reasons, score, dates_known):
                continue
            first, second = sorted([doc_id, other["id"]])
            exists = session.scalar(
                select(func.count()).where(pairs.c.document_id == first, pairs.c.other_id == second)
            )
            if exists:  # a dismissed pair stays dismissed
                continue
            session.execute(
                pairs.insert().values(
                    document_id=first,
                    other_id=second,
                    score=round(len(reasons) / 4, 2),
                    reasons=reasons,
                    status="open",
                )
            )
            added += 1
    return added


@jobs.handler("duplicates.scan")
def run_scan(payload: dict, ctx: Any) -> None:
    scan(payload["document_id"])


def queue_scan(doc_id: str) -> int:
    return jobs.enqueue(
        "duplicates.scan", {"document_id": doc_id}, dedupe_key=f"duplicates:{doc_id}"
    )
