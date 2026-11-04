"""The documents service: reading documents and applying metadata changes with locks and audit.

Every change commits to the database first; `meta.json` in the vault is then re-rendered
from the database (contracts §2.5), and `document.metadata_changed` tells the AI track.
"""

import re
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from docuhive import auth, db, jobs
from docuhive.contracts import (
    ApplyResult,
    CurrentUser,
    DocStatus,
    DocumentView,
    FactValue,
    MetadataPatch,
    Provenance,
    SearchFilters,
    SourceInfo,
)
from docuhive.db.models import (
    AuditLog,
    Correspondent,
    DocFact,
    DocSource,
    Document,
    DocumentTag,
    Tag,
)

from .metadata import apply_view

FTS_CONFIGS = {"de": "dh_german", "en": "dh_english"}
TSV_MAX_CHARS = 1_000_000
SCALARS = ("title", "document_date", "language", "category", "document_type")


class NotFound(Exception):
    pass


def norm_name(name: str) -> str:
    """Same rule the AI track uses to match senders: casefold, trimmed, collapsed spaces."""
    return " ".join(name.casefold().split())


def slug(name: str) -> str:
    return re.sub(r"\s+", "-", name.strip().casefold())


def _row(session: Session, doc_id: str, *, lock: bool = False) -> Document:
    """With `lock`, concurrent changes to this document wait for this transaction."""
    doc = session.get(Document, doc_id, with_for_update=lock, populate_existing=lock)
    if doc is None:
        raise NotFound(doc_id)
    return doc


def _view(session: Session, doc: Document) -> DocumentView:
    correspondent = (
        session.scalar(select(Correspondent.name).where(Correspondent.id == doc.correspondent_id))
        if doc.correspondent_id
        else None
    )
    tags = session.scalars(
        select(Tag.name)
        .join(DocumentTag, DocumentTag.tag_id == Tag.id)
        .where(DocumentTag.document_id == doc.id)
        .order_by(Tag.name)
    ).all()
    facts = {
        f.field: FactValue(
            type=f.type, value=f.value_text, currency=f.currency, confidence=f.confidence
        )  # type: ignore[arg-type]
        for f in session.scalars(select(DocFact).where(DocFact.document_id == doc.id))
    }
    source = session.get(DocSource, doc.id)
    return DocumentView(
        id=doc.id,
        owner_id=doc.owner_id,
        shared=doc.shared,
        status=DocStatus(doc.status),
        mime=doc.mime,
        pages=doc.pages,
        added_at=doc.added_at,
        title=doc.title,
        document_date=doc.document_date,
        language=doc.language,
        category=doc.category,
        document_type=doc.document_type,
        correspondent=correspondent,
        tags=list(tags),
        facts=facts,
        manual_fields=list(doc.manual_fields or []),
        source=SourceInfo(
            kind=source.kind if source else "upload",  # type: ignore[arg-type]
            original_filename=source.original_filename if source else "",
            account_id=source.account_id if source else None,
            message_id=source.message_id if source else None,
            email_from=source.email_from if source else None,
            subject=source.subject if source else None,
            received_at=source.received_at if source else None,
        ),
        deleted_at=doc.deleted_at,
    )


def get(doc_id: str) -> DocumentView:
    with db.session() as session:
        return _view(session, _row(session, doc_id))


def get_for_user(doc_id: str, user: CurrentUser) -> DocumentView:
    with db.session() as session:
        doc = session.scalar(select(Document).where(Document.id == doc_id, auth.visible_docs(user)))
        if doc is None:
            raise NotFound(doc_id)
        return _view(session, doc)


def get_content(doc_id: str, max_chars: int | None = None) -> str:
    if max_chars is not None and max_chars < 0:
        raise ValueError("max_chars must not be negative")
    with db.session() as session:
        content = _row(session, doc_id).content or ""
    return content[:max_chars]


def refresh_tsv(session: Session, doc_id: str) -> None:
    """Weighted search vector: title A, sender B, content C. PostgreSQL only."""
    if session.get_bind().dialect.name != "postgresql":
        return  # ponytail: the SQLite test fake searches the computed vector instead
    # ponytail: content is cut at 1 MB, the tsvector size limit; longer texts lose their tail.
    session.execute(
        text(
            """
            UPDATE documents d SET content_tsv =
              setweight(to_tsvector(d.fts_config, coalesce(d.title, '')), 'A') ||
              setweight(to_tsvector(d.fts_config, coalesce(
                (SELECT c.name FROM correspondents c WHERE c.id = d.correspondent_id), '')), 'B') ||
              setweight(to_tsvector(d.fts_config, left(coalesce(d.content, ''), :max)), 'C')
            WHERE d.id = :id
            """
        ),
        {"id": doc_id, "max": TSV_MAX_CHARS},
    )


def _correspondent_id(session: Session, name: str | None) -> int | None:
    if not name:
        return None
    norm = norm_name(name)
    row = _find_or_create(
        session,
        select(Correspondent).where(Correspondent.norm_name == norm),
        Correspondent(name=" ".join(name.split()), norm_name=norm),
    )
    return _resolve(session, Correspondent, row).id


def _tag_id(session: Session, name: str) -> int:
    row = _find_or_create(
        session, select(Tag).where(Tag.slug == slug(name)), Tag(name=name.strip(), slug=slug(name))
    )
    return _resolve(session, Tag, row).id


def _find_or_create(session: Session, query: Any, new: Any) -> Any:
    """Two edits creating the same tag at once: the loser re-reads the winner's row."""
    if (row := session.scalar(query)) is not None:
        return row
    try:
        with session.begin_nested():
            session.add(new)
        return new
    except IntegrityError:
        return session.scalar(query)


def _resolve(session: Session, model: type[Tag] | type[Correspondent], row: Any) -> Any:
    """Follow `merged_into` to the surviving row; a vocabulary merge keeps the old one."""
    seen = {row.id}
    while row.merged_into and row.merged_into not in seen:
        target: Any = session.get(model, row.merged_into)
        if target is None:
            break
        seen.add(target.id)
        row = target
    return row


def _write_fact(session: Session, doc_id: str, key: str, value: FactValue | None) -> None:
    session.execute(delete(DocFact).where(DocFact.document_id == doc_id, DocFact.field == key))
    if value is None:
        return
    session.add(
        DocFact(
            document_id=doc_id,
            field=key,
            type=value.type,
            value_text=value.value,
            value_num=Decimal(value.value) if value.type in {"money", "number"} else None,
            value_date=date.fromisoformat(value.value) if value.type == "date" else None,
            currency=value.currency,
            confidence=value.confidence,
        )
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, FactValue):
        return value.model_dump(mode="json")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def apply_metadata(
    doc_id: str,
    patch: MetadataPatch,
    *,
    actor: str,
    provenance: Provenance | None = None,
    force: bool = False,
) -> ApplyResult:
    with db.session() as session:
        doc = _row(session, doc_id, lock=True)
        before = _view(session, doc)
        after = before.model_copy(deep=True)
        result = apply_view(after, patch, actor=actor, force=force)
        unlocked = sorted(set(before.manual_fields) - set(after.manual_fields))
        for name in SCALARS:
            setattr(doc, name, getattr(after, name))
        if after.language != before.language:
            doc.fts_config = FTS_CONFIGS.get(after.language or "", "dh_simple")
        if after.correspondent != before.correspondent:
            doc.correspondent_id = _correspondent_id(session, after.correspondent)
        if after.tags != before.tags:
            session.execute(delete(DocumentTag).where(DocumentTag.document_id == doc_id))
            session.flush()
            for tag_id in {_tag_id(session, name) for name in after.tags}:
                session.add(DocumentTag(document_id=doc_id, tag_id=tag_id))
        for field in result.applied:
            if field.startswith("facts."):
                _write_fact(session, doc_id, field[6:], after.facts.get(field[6:]))
        doc.manual_fields = after.manual_fields
        if not (result.applied or unlocked):
            return result
        if provenance and result.applied:
            doc.ai_provenance = {
                **(doc.ai_provenance or {}),
                provenance.task: provenance.model_dump(mode="json"),
            }
        doc.updated_at = datetime.now(UTC)
        changed = result.applied
        session.add(
            AuditLog(
                actor=actor,
                document_id=doc_id,
                action="metadata",
                before={f: _jsonable(_field(before, f)) for f in changed} or None,
                after={f: _jsonable(_field(after, f)) for f in changed}
                | ({"unlocked": unlocked} if unlocked else {}),
            )
        )
        session.flush()
        if {"title", "correspondent", "language"} & set(changed):
            refresh_tsv(session, doc_id)
        payload: dict = {"document_id": doc_id, "fields": result.applied, "actor": actor}
        if unlocked:
            payload["unlocked"] = unlocked
        jobs.enqueue("document.metadata_changed", payload, queue="ai", in_session=session)
        _meta().queue(session, doc_id)
    _meta().write_or_queue(doc_id)
    return result


def _field(view: DocumentView, field: str) -> Any:
    if field.startswith("facts."):
        return view.facts.get(field[6:])
    return getattr(view, field)


def iter_ids(
    *,
    status: DocStatus = DocStatus.stored,
    added_since: datetime | None = None,
    filters: SearchFilters | None = None,
) -> Iterator[str]:
    from docuhive.search.filters import conditions

    query = select(Document.id).where(Document.status == status.value).order_by(Document.id)
    if added_since:
        query = query.where(Document.added_at >= added_since)
    if filters is not None:
        query = query.where(*conditions(filters))
        if not filters.include_trashed:
            query = query.where(Document.deleted_at.is_(None))
    with db.session() as session:
        # ponytail: ids only, so a plain list stays small; stream with yield_per past ~1M docs.
        ids = list(session.scalars(query))
    yield from ids


def set_trashed(doc_id: str, user: CurrentUser, trashed: bool) -> None:
    """Soft delete or restore; only the owner may do either (a shared reader cannot)."""
    with db.session() as session:
        doc = session.scalar(
            select(Document)
            .where(Document.id == doc_id, auth.visible_docs_incl_trash(user))
            .with_for_update()
        )
        if doc is None or doc.owner_id != user.id:
            raise NotFound(doc_id)
        if (doc.deleted_at is not None) == trashed:
            return
        doc.deleted_at = datetime.now(UTC) if trashed else None
        session.add(
            AuditLog(
                actor=f"user:{user.id}",
                document_id=doc_id,
                action="trash" if trashed else "restore",
            )
        )
        kind = "document.trashed" if trashed else "document.restored"
        jobs.enqueue(kind, {"document_id": doc_id}, queue="ai", in_session=session)
        _meta().queue(session, doc_id)
    _meta().write_or_queue(doc_id)


def _meta() -> Any:
    from docuhive.vault import meta

    return meta
