"""Documents: list, detail, files, edit, bulk edit, trash, upload and quarantine retry.

Every query applies the one visibility rule (`auth.visible_docs`); changing a document is for
its owner only, and every change goes through `documents.apply_metadata`.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from docuhive import auth, db, documents, taxonomy, vault
from docuhive.auth import current_user
from docuhive.contracts import (
    ApplyResult,
    CurrentUser,
    DocumentView,
    MetadataPatch,
    SearchFilters,
    SourceKind,
)
from docuhive.db.models import AuditLog, Correspondent, Document, DocumentTag, Tag
from docuhive.ingest.process import retry
from docuhive.vault.meta import write_or_queue

from .views import DocumentPage, DocumentRow, document_page, problem

router = APIRouter(prefix="/api", tags=["documents"])
UserDependency = Annotated[CurrentUser, Depends(current_user)]
MAX_BULK = 500
INLINE_ORIGINALS = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
CHUNK = 1 << 20


class DocumentDetail(DocumentView):
    quarantine_reason: str | None
    provenance: dict[str, Any]
    files: list[Literal["original", "archive", "thumb"]]


class DocumentEdit(MetadataPatch):
    shared: bool | None = None


class EditResult(BaseModel):
    document: DocumentDetail
    result: ApplyResult


class BulkEdit(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=MAX_BULK)
    patch: DocumentEdit


class BulkResult(BaseModel):
    updated: int
    skipped: list[str]  # not found or not owned


class HistoryEntry(BaseModel):
    at: datetime
    actor: str
    action: str
    before: dict | None
    after: dict | None


class PendingDocument(BaseModel):
    id: str
    title: str | None
    status: str
    quarantine_reason: str | None
    added_at: datetime


def owned(doc_id: str, user: CurrentUser) -> DocumentView:
    try:
        view = documents.get_for_user(doc_id, user)
    except documents.NotFound:
        view = None
    if view is None or view.owner_id != user.id:
        raise problem(404, "document_not_found", "Document not found.")
    return view


def detail(view: DocumentView) -> DocumentDetail:
    with db.session() as session:
        row = session.get(Document, view.id)
        assert row is not None
        reason, provenance, vault_path = row.quarantine_reason, row.ai_provenance, row.vault_path
    files: list[Literal["original", "archive", "thumb"]] = []
    if vault_path:
        folder = vault.root() / vault_path
        for kind in ("original", "archive", "thumb"):
            if file_path(folder, kind):
                files.append(kind)  # type: ignore[arg-type]
    return DocumentDetail(
        **view.model_dump(),
        quarantine_reason=reason,
        provenance=provenance or {},
        files=files,
    )


def file_path(folder: Path, kind: str) -> Path | None:
    if kind == "original":
        return vault.original(folder)
    path = folder / ("archive.pdf" if kind == "archive" else "thumb.webp")
    return path if path.is_file() else None


def validate(patch: MetadataPatch, current_category: str | None = None) -> None:
    """Category and type ids are checked here; the documents service does not (contracts §2.5)."""
    vocab = taxonomy.load()
    if patch.category and patch.category not in {c.id for c in vocab.categories}:
        raise problem(422, "document_unknown_category", "That category does not exist.")
    if (
        patch.category
        and patch.category != current_category
        and patch.category not in {c.id for c in vocab.categories if c.enabled}
    ):
        raise problem(
            422,
            "document_disabled_category",
            "Choose an enabled category from your archive settings.",
        )
    if patch.document_type and patch.document_type not in {t.id for t in vocab.document_types}:
        raise problem(422, "document_unknown_type", "That document type does not exist.")


def edit(doc_id: str, body: DocumentEdit, user: CurrentUser) -> ApplyResult:
    patch = MetadataPatch.model_validate(body.model_dump(exclude={"shared"}))
    try:
        result = documents.apply_metadata(doc_id, patch, actor=f"user:{user.id}")
    except ValueError as error:
        raise problem(422, "document_invalid_value", str(error)) from error
    if body.shared is not None:
        with db.session() as session:
            row = session.get(Document, doc_id)
            assert row is not None
            if row.shared != body.shared:
                session.add(
                    AuditLog(
                        actor=f"user:{user.id}",
                        document_id=doc_id,
                        action="metadata",
                        before={"shared": row.shared},
                        after={"shared": body.shared},
                    )
                )
                row.shared = body.shared
                result.applied.append("shared")
        if "shared" in result.applied:
            write_or_queue(doc_id)
    return result


def query_filters(
    category: Annotated[list[str], Query()] = [],  # noqa: B006
    document_type: Annotated[list[str], Query()] = [],  # noqa: B006
    correspondent: Annotated[list[str], Query()] = [],  # noqa: B006
    tag: Annotated[list[str], Query()] = [],  # noqa: B006
    source: Annotated[list[SourceKind], Query()] = [],  # noqa: B006
    date_from: date | None = None,
    date_to: date | None = None,
) -> SearchFilters:
    """The same filters for the document list and search, as repeatable query parameters."""
    return SearchFilters(
        categories=category,
        document_types=document_type,
        correspondents=correspondent,
        tags=tag,
        source_kinds=source,
        date_from=date_from,
        date_to=date_to,
    )


FiltersDependency = Annotated[SearchFilters, Depends(query_filters)]


@router.get("/documents", response_model=DocumentPage)
def list_documents(
    user: UserDependency,
    filters: FiltersDependency,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100_000),
) -> DocumentPage:
    return document_page(user, filters, limit, offset)


class SearchResult(BaseModel):
    document_id: str
    title: str | None
    snippet: str | None  # plain text; highlights marked with \u0002 ... \u0003
    score: float
    document_date: date | None
    correspondent: str | None
    category: str | None


@router.get("/search", response_model=list[SearchResult])
def search_documents(
    user: UserDependency,
    filters: FiltersDependency,
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(20, ge=1, le=50),
) -> list[SearchResult]:
    """Words and meaning, fused into one ranking; only documents you may open."""
    from docuhive import search

    hits = search.hybrid(user, q, filters, limit)
    with db.session() as session:
        rows = {
            r[0]: r[1:]
            for r in session.execute(
                select(Document.id, Document.document_date, Correspondent.name, Document.category)
                .outerjoin(Correspondent, Correspondent.id == Document.correspondent_id)
                .where(Document.id.in_([h.document_id for h in hits]))
            )
        }
    return [
        SearchResult(
            document_id=h.document_id,
            title=h.title,
            snippet=h.snippet,
            score=h.score,
            document_date=rows.get(h.document_id, (None, None, None))[0],
            correspondent=rows.get(h.document_id, (None, None, None))[1],
            category=rows.get(h.document_id, (None, None, None))[2],
        )
        for h in hits
    ]


@router.get("/documents/pending", response_model=list[PendingDocument])
def pending(user: UserDependency) -> list[PendingDocument]:
    """The owner's documents still being read, and those in quarantine."""
    with db.session() as session:
        rows = session.scalars(
            select(Document)
            .where(
                Document.owner_id == user.id,
                Document.status != "stored",
                Document.deleted_at.is_(None),
            )
            .order_by(Document.added_at.desc())
            .limit(200)
        )
        return [
            PendingDocument(
                id=r.id,
                title=r.title,
                status=r.status,
                quarantine_reason=r.quarantine_reason,
                added_at=r.added_at,
            )
            for r in rows
        ]


@router.get("/documents/trash", response_model=list[DocumentRow])
def trash(user: UserDependency) -> list[DocumentRow]:
    with db.session() as session:
        rows = session.execute(
            select(
                Document.id,
                Document.title,
                Document.document_date,
                Document.category,
                Document.document_type,
                Correspondent.name,
                Document.added_at,
            )
            .outerjoin(Correspondent, Correspondent.id == Document.correspondent_id)
            .where(Document.owner_id == user.id, Document.deleted_at.is_not(None))
            .order_by(Document.deleted_at.desc())
            .limit(500)
        ).all()
        tags: dict[str, list[str]] = {}
        for doc_id, name in session.execute(
            select(DocumentTag.document_id, Tag.name)
            .join(Tag, Tag.id == DocumentTag.tag_id)
            .where(DocumentTag.document_id.in_([r[0] for r in rows]))
            .order_by(Tag.name)
        ):
            tags.setdefault(doc_id, []).append(name)
    return [
        DocumentRow(
            id=r[0],
            title=r[1],
            document_date=r[2],
            category=r[3],
            document_type=r[4],
            correspondent=r[5],
            tags=tags.get(r[0], []),
            added_at=r[6],
        )
        for r in rows
    ]


@router.post("/documents/bulk", response_model=BulkResult)
def bulk_edit(body: BulkEdit, user: UserDependency) -> BulkResult:
    validate(body.patch)
    # ponytail: synchronous up to 500 documents; a job per 50 when bulk edits get slow.
    updated, skipped = 0, []
    for doc_id in dict.fromkeys(body.ids):
        try:
            owned(doc_id, user)
        except HTTPException:
            skipped.append(doc_id)
            continue
        edit(doc_id, body.patch, user)
        updated += 1
    return BulkResult(updated=updated, skipped=skipped)


@router.get("/documents/{doc_id}", response_model=DocumentDetail)
def get_document(doc_id: str, user: UserDependency) -> DocumentDetail:
    try:
        return detail(documents.get_for_user(doc_id, user))
    except documents.NotFound as error:
        raise problem(404, "document_not_found", "Document not found.") from error


@router.get("/documents/{doc_id}/file")
def get_file(
    doc_id: str,
    user: UserDependency,
    kind: Literal["original", "archive", "thumb"] = "archive",
    download: bool = False,
) -> FileResponse:
    view = get_document(doc_id, user)
    with db.session() as session:
        vault_path = session.scalar(select(Document.vault_path).where(Document.id == doc_id))
    root = vault.root().resolve()
    path = file_path(root / vault_path, kind) if vault_path else None
    if path is None or not path.resolve().is_relative_to(root):
        raise problem(404, "document_file_missing", "This file is not in the vault.")
    name = Path(view.source.original_filename or "document").stem or "document"
    filename = {
        "original": f"{name}{path.suffix}",
        "archive": f"{name}.pdf",
        "thumb": f"{name}.webp",
    }[kind]
    # Originals can be HTML or email: opened inline they would run scripts on DocuHive's
    # origin. Only PDFs and plain images are shown; everything else downloads. (A CSP sandbox
    # would also stop Chrome's PDF viewer, which the preview relies on.)
    inline = not download and (kind != "original" or view.mime in INLINE_ORIGINALS)
    return FileResponse(
        path,
        filename=filename,
        content_disposition_type="inline" if inline else "attachment",
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/documents/{doc_id}/thumbnail")
def get_thumbnail(doc_id: str, user: UserDependency) -> FileResponse:
    return get_file(doc_id, user, kind="thumb")


@router.get("/documents/{doc_id}/history", response_model=list[HistoryEntry])
def history(doc_id: str, user: UserDependency) -> list[HistoryEntry]:
    get_document(doc_id, user)
    with db.session() as session:
        rows = session.execute(
            select(AuditLog.at, AuditLog.actor, AuditLog.action, AuditLog.before, AuditLog.after)
            .where(AuditLog.document_id == doc_id)
            .order_by(AuditLog.at.desc(), AuditLog.id.desc())
            .limit(200)
        ).all()
    return [HistoryEntry(at=r[0], actor=r[1], action=r[2], before=r[3], after=r[4]) for r in rows]


@router.patch("/documents/{doc_id}", response_model=EditResult)
def edit_document(doc_id: str, body: DocumentEdit, user: UserDependency) -> EditResult:
    view = owned(doc_id, user)
    validate(body, current_category=view.category)
    result = edit(doc_id, body, user)
    return EditResult(document=detail(documents.get(doc_id)), result=result)


@router.post("/documents/{doc_id}/trash", status_code=204)
def trash_document(doc_id: str, user: UserDependency) -> None:
    try:
        documents.set_trashed(doc_id, user, True)
    except documents.NotFound as error:
        raise problem(404, "document_not_found", "Document not found.") from error


@router.post("/documents/{doc_id}/restore", status_code=204)
def restore_document(doc_id: str, user: UserDependency) -> None:
    try:
        documents.set_trashed(doc_id, user, False)
    except documents.NotFound as error:
        raise problem(404, "document_not_found", "Document not found.") from error


@router.post("/documents/{doc_id}/retry", status_code=202)
def retry_document(doc_id: str, user: UserDependency) -> None:
    with db.session() as session:
        found = session.scalar(
            select(Document.id).where(
                Document.id == doc_id, Document.owner_id == user.id, auth.visible_docs(user)
            )
        )
    if found is None or not retry(doc_id):
        raise problem(404, "document_not_quarantined", "This document is not in quarantine.")
