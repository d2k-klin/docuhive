"""/api/review: the queue grouped by document, resolving items, bulk reclassify."""

from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from docuhive import auth, db, documents, jobs
from docuhive.ai import coretables
from docuhive.ai.http import User, fail, page, summary
from docuhive.contracts import SearchFilters
from docuhive.review import ReviewError, accept, accept_all, accept_term, reject, reject_all
from docuhive.review.models import ReviewItem

router = APIRouter(prefix="/api/review", tags=["review"])


def _call(fn: Callable[..., Any], *args: Any, **kw: Any) -> Any:
    try:
        return fn(*args, **kw)
    except ReviewError as e:
        fail(e.status, e.code, e.message)


def _visible_pending(  # type: ignore[no-untyped-def]
    user: Any, kind: str | None = None, category: str | None = None, doc_id: str | None = None
):
    d = coretables.table("documents")
    q = (
        select(ReviewItem)
        .join(d, d.c.id == ReviewItem.document_id)
        .where(ReviewItem.status == "pending", auth.visible_docs(user))
    )
    if kind:
        q = q.where(ReviewItem.kind == kind)
    if category:
        q = q.where(d.c.category == category)
    if doc_id:
        q = q.where(ReviewItem.document_id == doc_id)
    return q


def _item(i: ReviewItem) -> dict:
    return {
        "id": i.id,
        "kind": i.kind,
        "field": i.field,
        "suggested": i.suggested,
        "current": i.current,
        "confidence": i.confidence,
        "reason": i.reason,
        "evidence": i.evidence,
        "ai_run_id": i.ai_run_id,
        "created_at": i.created_at,
    }


@router.get("/queue")
def queue(
    user: User,
    kind: Literal["field", "new_term", "notice"] | None = None,
    category: str | None = None,
    document_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
) -> dict:
    """Pending items grouped by document, oldest document first."""
    offset = int(cursor or 0)
    with db.session() as s:
        items = list(
            s.scalars(
                _visible_pending(user, kind, category, document_id).order_by(
                    ReviewItem.created_at, ReviewItem.id
                )
            )
        )
        s.expunge_all()
    order: list[str] = []
    by_doc: dict[str, list[dict]] = {}
    for i in items:
        if i.document_id not in by_doc:
            order.append(i.document_id)
            by_doc[i.document_id] = []
        by_doc[i.document_id].append(_item(i))
    groups = []
    for doc_id in order[offset : offset + limit + 1]:
        v = documents.get(doc_id)
        groups.append(
            {
                "document": summary(v) | {"can_resolve": v.owner_id == user.id},
                "items": by_doc[doc_id],
            }
        )
    return page(groups, limit, offset)


@router.get("/count")
def count(user: User) -> dict:
    with db.session() as s:
        n = s.scalar(select(func.count()).select_from(_visible_pending(user).subquery()))
    return {"pending": n or 0}


class AcceptBody(BaseModel):
    value: Any = None
    currency: str | None = None


@router.post("/items/{item_id}/accept")
def accept_item(item_id: int, user: User, body: AcceptBody | None = None) -> dict:
    body = body or AcceptBody()
    res = _call(accept, item_id, user, body.value, body.currency)
    return res.model_dump()


@router.post("/items/{item_id}/reject")
def reject_item(item_id: int, user: User) -> dict:
    _call(reject, item_id, user)
    return {"ok": True}


@router.post("/documents/{doc_id}/accept-all")
def accept_document(doc_id: str, user: User) -> dict:
    return _call(accept_all, doc_id, user).model_dump()


@router.post("/documents/{doc_id}/reject-all")
def reject_document(doc_id: str, user: User) -> dict:
    return {"rejected": _call(reject_all, doc_id, user)}


@router.post("/terms/{item_id}/accept")
def accept_new_term(item_id: int, user: User) -> dict:
    return _call(accept_term, item_id, user)


class Reclassify(BaseModel):
    document_ids: list[str] | None = None
    filters: SearchFilters | None = None
    tasks: list[Literal["classify", "extract"]] = ["classify", "extract"]


@router.post("/reclassify")
def reclassify(body: Reclassify, user: User) -> dict:
    """Re-run AI on documents you own (admins: any visible document). Jobs are deduplicated."""
    if body.document_ids is None and body.filters is None:
        fail(400, "missing_scope", "Pass document_ids or filters")
    ids = (
        body.document_ids
        if body.document_ids is not None
        else list(documents.iter_ids(filters=body.filters))
    )
    n = 0
    for doc_id in ids:
        try:
            v = documents.get_for_user(doc_id, user)
        except documents.NotFound:
            continue
        if v.owner_id != user.id and user.role != "admin":
            continue
        for task in body.tasks:
            kind = f"ai.{task}"
            jobs.enqueue(kind, {"document_id": doc_id}, queue="ai", dedupe_key=f"{task}:{doc_id}")
        n += 1
    return {"documents": n, "jobs": n * len(body.tasks)}
