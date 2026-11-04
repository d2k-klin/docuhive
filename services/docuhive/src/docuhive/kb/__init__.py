"""Saved scopes over the existing document index; sharing never grants document access."""

from datetime import datetime

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, column, func, or_, select, table
from sqlalchemy.orm import Session

from docuhive import auth, db, taxonomy
from docuhive.config import load_yaml
from docuhive.contracts import CurrentUser, KnowledgeBaseView, SearchFilters
from docuhive.db.models import Document, DocumentTag, Job, KnowledgeBase, Tag
from docuhive.search.filters import conditions

CHUNKS = table("doc_chunks", column("document_id"), column("embed_model"), column("created_at"))


class KnowledgeBaseStatus(BaseModel):
    documents: int
    embedded: int
    pending: int
    failed: int
    stale: int
    last_indexed_at: datetime | None
    embedding_model: str | None


def visible(user: CurrentUser) -> ColumnElement[bool]:
    return or_(KnowledgeBase.owner_id == user.id, KnowledgeBase.shared.is_(True))


def view(row: KnowledgeBase) -> KnowledgeBaseView:
    return KnowledgeBaseView.model_validate(row, from_attributes=True)


def get(user: CurrentUser, kb_id: int) -> KnowledgeBaseView:
    with db.session() as session:
        row = session.scalar(select(KnowledgeBase).where(KnowledgeBase.id == kb_id, visible(user)))
        if row is None:
            raise HTTPException(
                404,
                detail={
                    "code": "kb_not_found",
                    "message": "Knowledge base not found",
                    "details": {},
                },
            )
        return view(row)


def document_scope(user: CurrentUser, filters: SearchFilters) -> Select:
    return select(Document.id).where(
        auth.visible_docs(user), Document.status == "stored", *conditions(filters)
    )


def known_tags(session: Session, user: CurrentUser) -> set[str]:
    return set(taxonomy.load().tags) | set(
        session.scalars(
            select(Tag.name).join(DocumentTag).join(Document).where(auth.visible_docs(user))
        )
    )


def validate_filters(session: Session, user: CurrentUser, filters: SearchFilters) -> None:
    vocab = taxonomy.load()
    categories = {c.id for c in vocab.categories}
    categories |= {c.split("/")[0] for c in categories}
    types = {t.id for t in vocab.document_types}
    tags = known_tags(session, user)
    invalid = (
        set(filters.categories) - categories
        or set(filters.document_types) - types
        or set(filters.tags) - tags
    )
    if (
        invalid
        or filters.include_trashed
        or (filters.date_from and filters.date_to and filters.date_from > filters.date_to)
    ):
        raise HTTPException(
            422,
            detail={
                "code": "kb_invalid_filters",
                "message": "Choose current categories, types and tags, and a valid date range. "
                "Trashed documents cannot be included.",
                "details": {},
            },
        )


def status(user: CurrentUser, kb_id: int) -> KnowledgeBaseStatus:
    kb = get(user, kb_id)
    route = load_yaml("routing.yaml").get("tasks", {}).get("embed", {}).get("route")
    scope = document_scope(user, kb.filters).subquery()
    with db.session() as session:
        documents = set(session.scalars(select(scope.c.id)))
        chunks = session.execute(
            select(CHUNKS.c.document_id, CHUNKS.c.embed_model, func.max(CHUNKS.c.created_at))
            .where(CHUNKS.c.document_id.in_(select(scope.c.id)))
            .group_by(CHUNKS.c.document_id, CHUNKS.c.embed_model)
        ).all()
        # Only the latest embedding job counts: a successful retry replaces an old failure.
        latest: dict[str, str] = {}
        jobs = session.execute(
            select(Job.payload, Job.status)
            .where(
                Job.kind == "index.embed",
                Job.payload["document_id"].as_string().in_(select(scope.c.id)),
            )
            .order_by(Job.id.desc())
        )
        for payload, job_status in jobs:
            doc_id = payload.get("document_id")
            if doc_id in documents:
                latest.setdefault(doc_id, job_status)
    embedded = {r[0] for r in chunks}
    stale = {r[0] for r in chunks if route and r[1] != route}
    failed = {doc_id for doc_id, state in latest.items() if state == "dead"}
    pending = (documents - embedded - failed) | {
        doc_id for doc_id, state in latest.items() if state in {"pending", "running"}
    }
    return KnowledgeBaseStatus(
        documents=len(documents),
        embedded=len(embedded),
        pending=len(pending),
        failed=len(failed),
        stale=len(stale),
        last_indexed_at=max((r[2] for r in chunks), default=None),
        embedding_model=route,
    )


def suggestions(user: CurrentUser) -> list[dict]:
    vocab = taxonomy.load()
    with db.session() as session:
        categories = set(
            session.scalars(
                select(Document.category).where(
                    auth.visible_docs(user), Document.status == "stored"
                )
            )
        )
        has_documents = session.scalar(select(document_scope(user, SearchFilters()).exists()))
    if not has_documents:
        return []
    roots = {c.split("/")[0] for c in categories if c}
    roots &= {c.id.split("/")[0] for c in vocab.categories}
    labels = {c.id: c.label for c in vocab.categories}
    return [{"name": "Everything", "filters": SearchFilters()}] + [
        {
            "name": labels.get(root, root.replace("_", " ").title()),
            "filters": SearchFilters(categories=[root]),
        }
        for root in sorted(roots)
    ]
