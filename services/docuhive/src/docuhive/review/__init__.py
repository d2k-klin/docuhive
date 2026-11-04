"""Review queue: AI suggestions become review_items; people accept, edit or reject them.

Field names: title, category, document_type, correspondent, tags, document_date, language,
and facts.<name>. New-term items use field "<kind>:<value>" (kind: category|document_type|tag).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select, update

from docuhive import db, documents, taxonomy
from docuhive.ai.routing import ApplyPolicy
from docuhive.contracts import (
    ApplyResult,
    CurrentUser,
    DocumentView,
    FactValue,
    MetadataPatch,
    Provenance,
)
from docuhive.review.models import ReviewItem

SCALAR_FIELDS = ("title", "category", "document_type", "correspondent", "document_date", "language")


class ReviewError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


@dataclass
class Suggestion:
    field: str
    payload: dict  # {"value": ..., "currency"?: ..., "type"?: ...} (JSON-able)
    confidence: float | None
    reason: str | None = None
    evidence: str | None = None


def current_of(view: DocumentView, field: str) -> Any:
    if field.startswith("facts."):
        f = view.facts.get(field[6:])
        return f.model_dump(mode="json") if f else None
    value = getattr(view, field)
    return value.isoformat() if isinstance(value, date) else value


def to_patch(field: str, payload: dict) -> MetadataPatch:
    """MetadataPatch for one field; category/type ids are validated (OA does not, by contract)."""
    value = payload.get("value")
    tax = taxonomy.load()
    if field == "category" and value not in {c.id for c in tax.categories}:
        raise ReviewError("invalid_value", f"Unknown category {value!r}")
    if field == "document_type" and value not in {t.id for t in tax.document_types}:
        raise ReviewError("invalid_value", f"Unknown document type {value!r}")
    if field == "tags":
        return MetadataPatch(tags_add=list(value or []))
    if field.startswith("facts."):
        if value in (None, ""):
            raise ReviewError("invalid_value", "Enter a value first")
        fact = FactValue(
            type=payload.get("type", "string"),
            value=str(value),
            currency=payload.get("currency"),
            confidence=payload.get("confidence"),
        )
        return MetadataPatch(facts={field[6:]: fact})
    if field == "document_date":
        return MetadataPatch(document_date=date.fromisoformat(value) if value else None)
    if field in SCALAR_FIELDS:
        return MetadataPatch(**{field: value})
    raise ReviewError("invalid_field", f"Unknown field {field!r}")


def merge(patches: list[MetadataPatch]) -> MetadataPatch:
    out = MetadataPatch()
    for p in patches:
        for name in SCALAR_FIELDS:
            if getattr(p, name) is not None:
                setattr(out, name, getattr(p, name))
        out.tags_add += p.tags_add
        if p.facts:
            out.facts = {**(out.facts or {}), **p.facts}
    return out


def suggest(
    doc_id: str,
    s: Suggestion,
    *,
    current: Any = None,
    ai_run_id: int | None = None,
    kind: str = "field",
) -> int:
    """Insert a pending item; it supersedes a pending item for the same (document, kind, field)."""
    with db.session() as ses:
        ses.execute(
            update(ReviewItem)
            .where(
                ReviewItem.document_id == doc_id,
                ReviewItem.kind == kind,
                ReviewItem.field == s.field,
                ReviewItem.status == "pending",
            )
            .values(status="superseded", resolved_at=datetime.now(UTC))
        )
        ses.flush()
        item = ReviewItem(
            document_id=doc_id,
            kind=kind,
            field=s.field,
            suggested=s.payload,
            current=current,
            confidence=s.confidence,
            reason=s.reason,
            evidence=s.evidence,
            ai_run_id=ai_run_id,
            status="pending",
        )
        ses.add(item)
        ses.flush()
        return item.id


def notice(doc_id: str, reason: str, *, ai_run_id: int | None = None) -> int:
    return suggest(
        doc_id,
        Suggestion(field="notice", payload={}, confidence=None, reason=reason),
        ai_run_id=ai_run_id,
        kind="notice",
    )


def supersede(doc_id: str, fields: list[str]) -> int:
    if not fields:
        return 0
    with db.session() as ses:
        return ses.execute(
            update(ReviewItem)
            .where(
                ReviewItem.document_id == doc_id,
                ReviewItem.kind == "field",
                ReviewItem.field.in_(fields),
                ReviewItem.status == "pending",
            )
            .values(status="superseded", resolved_at=datetime.now(UTC))
        ).rowcount  # type: ignore[attr-defined]


def apply_suggestions(
    view: DocumentView,
    suggestions: list[Suggestion],
    policy: ApplyPolicy,
    provenance: Provenance,
    *,
    always_apply: tuple[str, ...] = (),
) -> list[str]:
    """The apply policy (CL-02 §2.3). Manual fields and unchanged values are dropped silently.
    auto=false: everything goes to review except `always_apply`. auto=true: fields at or above
    their threshold are applied in ONE apply_metadata call; the rest go to review.
    Returns the applied field names."""
    to_apply: list[Suggestion] = []
    for s in suggestions:
        if s.field in view.manual_fields or _same(current_of(view, s.field), s.payload):
            continue
        conf = s.confidence or 0.0
        if s.field in always_apply or (policy.auto and conf >= policy.threshold_for(s.field)):
            to_apply.append(s)
        else:
            suggest(view.id, s, current=current_of(view, s.field), ai_run_id=provenance.ai_run_id)
    if not to_apply:
        return []
    patch = merge([to_patch(s.field, s.payload) for s in to_apply])
    result = documents.apply_metadata(
        view.id, patch, actor=f"ai:{provenance.task}", provenance=provenance
    )
    return result.applied


def _same(current: Any, payload: dict) -> bool:
    value = payload.get("value")
    if isinstance(current, dict):
        return current.get("value") == value and current.get("currency") == payload.get("currency")
    if isinstance(value, list):
        return not value
    return current == value


# ---- resolving -------------------------------------------------------------------------------


def _item(item_id: int) -> ReviewItem:
    with db.session() as ses:
        item = ses.get(ReviewItem, item_id)
        if item is None:
            raise ReviewError("not_found", "Review item not found", 404)
        ses.expunge(item)
    return item


def _owned_view(doc_id: str, user: CurrentUser) -> DocumentView:
    try:
        view = documents.get_for_user(doc_id, user)
    except documents.NotFound:
        raise ReviewError("not_found", "Document not found", 404) from None
    if view.owner_id != user.id:
        raise ReviewError("forbidden", "Only the document owner can resolve suggestions", 403)
    return view


def _resolve(ids: list[int], status: str, user: CurrentUser) -> None:
    with db.session() as ses:
        ses.execute(
            update(ReviewItem)
            .where(ReviewItem.id.in_(ids))
            .values(status=status, resolved_at=datetime.now(UTC), resolved_by=user.id)
        )


def accept(
    item_id: int, user: CurrentUser, value: Any = None, currency: str | None = None
) -> ApplyResult:
    """Apply the suggestion (optionally edited) as the user: the field becomes manual."""
    item = _item(item_id)
    if item.status != "pending" or item.kind != "field":
        raise ReviewError("conflict", "This suggestion is no longer pending", 409)
    _owned_view(item.document_id, user)
    payload = dict(item.suggested or {})
    if value is not None:
        payload["value"] = value
    if currency:
        payload["currency"] = currency
    result = documents.apply_metadata(
        item.document_id, to_patch(item.field or "", payload), actor=f"user:{user.id}"
    )
    _resolve([item.id], "accepted", user)
    return result


def reject(item_id: int, user: CurrentUser, status: str = "rejected") -> None:
    item = _item(item_id)
    if item.status != "pending":
        raise ReviewError("conflict", "This suggestion is no longer pending", 409)
    _owned_view(item.document_id, user)
    _resolve([item.id], "dismissed" if item.kind == "notice" else status, user)


def pending_for(doc_id: str, kind: str | None = "field") -> list[ReviewItem]:
    with db.session() as ses:
        q = select(ReviewItem).where(
            ReviewItem.document_id == doc_id, ReviewItem.status == "pending"
        )
        if kind:
            q = q.where(ReviewItem.kind == kind)
        items = list(ses.scalars(q.order_by(ReviewItem.id)))
        ses.expunge_all()
    return items


def accept_all(doc_id: str, user: CurrentUser) -> ApplyResult:
    _owned_view(doc_id, user)
    items = [i for i in pending_for(doc_id) if (i.suggested or {}).get("value") not in (None, "")]
    if not items:
        return ApplyResult(applied=[], skipped_manual=[])
    patch = merge([to_patch(i.field or "", i.suggested or {}) for i in items])
    result = documents.apply_metadata(doc_id, patch, actor=f"user:{user.id}")
    _resolve([i.id for i in items], "accepted", user)
    return result


def reject_all(doc_id: str, user: CurrentUser) -> int:
    _owned_view(doc_id, user)
    items = pending_for(doc_id)
    _resolve([i.id for i in items], "rejected", user)
    return len(items)


def accept_term(item_id: int, user: CurrentUser) -> dict:
    """The app cannot write the overlay: record the decision and hand back a YAML snippet.
    Tags are applied to the document right away (OA creates the tag)."""
    item = _item(item_id)
    if item.kind != "new_term" or item.status != "pending":
        raise ReviewError("conflict", "This proposal is no longer pending", 409)
    _owned_view(item.document_id, user)
    kind, _, value = (item.field or "").partition(":")
    if kind == "tag":
        documents.apply_metadata(
            item.document_id, MetadataPatch(tags_add=[value]), actor=f"user:{user.id}"
        )
        snippet = f"tags:\n  - {value}   # add to the existing list"
    elif kind == "category":
        snippet = f"categories:\n  - {{ id: {value}, label: {value.rsplit('/', 1)[-1].title()} }}"
    else:
        snippet = f"document_types:\n  - {{ id: {value}, label: {value.title()} }}"
    _resolve([item.id], "accepted", user)
    return {
        "kind": kind,
        "value": value,
        "overlay_file": "overlay/taxonomy.yaml",
        "snippet": snippet,
    }
