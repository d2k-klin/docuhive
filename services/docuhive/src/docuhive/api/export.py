"""Filtered export: the documents behind a filter, saved view or knowledge base as one ZIP with
their archive PDFs and a CSV of their metadata and facts. Read-only; every export is audited.
"""

import csv
import io
import re
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import model_validator
from sqlalchemy import select

from docuhive import db, kb
from docuhive.auth import current_user
from docuhive.config.settings import get_settings
from docuhive.contracts import CurrentUser, SearchFilters
from docuhive.db.models import (
    AuditLog,
    Correspondent,
    DocFact,
    DocSource,
    Document,
    DocumentTag,
    Tag,
)
from docuhive.vault.health import folder_of

from .knowledge import FilterScope
from .views import find as find_view

router = APIRouter(prefix="/api/export", tags=["export"])
UserDependency = Annotated[CurrentUser, Depends(current_user)]
MAX_DOCUMENTS = 1000
COLUMNS = [
    "id",
    "title",
    "document_date",
    "category",
    "document_type",
    "correspondent",
    "tags",
    "source",
    "original_filename",
    "file",
]
UNSAFE = re.compile(r"[^\w .,()&+-]+")


class ExportRequest(FilterScope):
    view_id: int | None = None
    kb_id: int | None = None

    @model_validator(mode="after")
    def one_source(self) -> "ExportRequest":
        given = sum(x is not None for x in (self.view_id, self.kb_id))
        if given > 1 or (given and "filters" in self.model_fields_set):
            raise ValueError("Choose filters, a saved view or a knowledge base, not several")
        return self


def problem(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, "details": {}})


def cell(value: Any) -> str:
    """Spreadsheets run cells starting with these characters as formulas; OCR text is untrusted."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in {"=", "+", "-", "@", "\t", "\r"} else text


def filename(row: Any, used: set[str]) -> str:
    title = UNSAFE.sub("_", row.title or "Untitled").strip(" ._")[:80] or "Untitled"
    name = f"{row.document_date or 'undated'} {title} ({row.id[-8:]}).pdf"
    while name in used:
        name = name[:-4] + "_.pdf"
    used.add(name)
    return name


def resolve(session: Any, user: CurrentUser, body: ExportRequest) -> SearchFilters:
    if body.view_id is not None:
        return SearchFilters.model_validate(find_view(session, user, body.view_id).filters)
    if body.kb_id is not None:
        return kb.get(user, body.kb_id).filters
    kb.validate_filters(session, user, body.filters)
    return body.filters


def collect(user: CurrentUser, filters: SearchFilters) -> tuple[list[Any], dict, dict, list[str]]:
    scope = select(kb.document_scope(user, filters).subquery().c.id)
    with db.session() as session:
        rows: list[Any] = session.execute(
            select(
                Document.id,
                Document.title,
                Document.document_date,
                Document.category,
                Document.document_type,
                Document.vault_path,
                Correspondent.name.label("sender"),
                DocSource.kind,
                DocSource.original_filename,
            )
            .outerjoin(Correspondent, Correspondent.id == Document.correspondent_id)
            .outerjoin(DocSource, DocSource.document_id == Document.id)
            .where(Document.id.in_(scope))
            .order_by(Document.document_date.nulls_last(), Document.id)
            .limit(MAX_DOCUMENTS + 1)
        ).all()  # type: ignore[assignment]
        if len(rows) > MAX_DOCUMENTS:
            raise problem(
                422,
                "export_too_large",
                f"Exports are limited to {MAX_DOCUMENTS} documents. Narrow the filter, "
                "for example to one year.",
            )
        ids = [r.id for r in rows]
        tags: dict[str, list[str]] = {}
        for doc_id, name in session.execute(
            select(DocumentTag.document_id, Tag.name)
            .join(Tag, Tag.id == DocumentTag.tag_id)
            .where(DocumentTag.document_id.in_(ids))
            .order_by(Tag.name)
        ):
            tags.setdefault(doc_id, []).append(name)
        facts: dict[str, dict[str, str]] = {}
        for fact in session.scalars(select(DocFact).where(DocFact.document_id.in_(ids))):
            value = f"{fact.value_text} {fact.currency}" if fact.currency else fact.value_text
            facts.setdefault(fact.document_id, {})[fact.field] = value
        if ids:
            session.add(
                AuditLog(
                    actor=f"user:{user.id}",
                    action="export",
                    after={"documents": len(ids), "filters": filters.model_dump(mode="json")},
                )
            )
    fields = sorted({name for doc in facts.values() for name in doc})
    return rows, tags, facts, fields


def build(rows: list[Any], tags: dict, facts: dict, fields: list[str]) -> Any:
    vault = get_settings().vault_dir.resolve()
    spool = tempfile.SpooledTemporaryFile(max_size=32 << 20)
    used: set[str] = set()
    missing: list[str] = []
    table = io.StringIO()
    writer = csv.writer(table)
    writer.writerow(COLUMNS + [f"fact:{name}" for name in fields])
    with zipfile.ZipFile(spool, "w", compression=zipfile.ZIP_STORED) as archive:
        for row in rows:
            source = folder_of(vault, row.vault_path) / "archive.pdf" if row.vault_path else None
            name = ""
            if source is not None and source.resolve().is_relative_to(vault) and source.is_file():
                name = filename(row, used)
                with source.open("rb") as src, archive.open(f"documents/{name}", "w") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
            else:
                missing.append(f"{row.id}\t{row.title or 'Untitled'}")
            doc_facts = facts.get(row.id, {})
            writer.writerow(
                [
                    cell(v)
                    for v in (
                        row.id,
                        row.title,
                        row.document_date,
                        row.category,
                        row.document_type,
                        row.sender,
                        "; ".join(tags.get(row.id, [])),
                        row.kind,
                        row.original_filename,
                        f"documents/{name}" if name else "",
                    )
                ]
                + [cell(doc_facts.get(f)) for f in fields]
            )
        archive.writestr("documents.csv", "﻿" + table.getvalue())  # BOM: Excel reads UTF-8
        if missing:
            archive.writestr(
                "MISSING.txt",
                "These documents have no archive copy in the vault yet:\n" + "\n".join(missing),
            )
    spool.seek(0)
    return spool


def chunks(spool: Any) -> Iterator[bytes]:
    try:
        while block := spool.read(1 << 20):
            yield block
    finally:
        spool.close()


@router.post("", response_class=StreamingResponse)
def export(body: ExportRequest, user: UserDependency) -> StreamingResponse:
    with db.session() as session:
        filters = resolve(session, user, body)
    rows, tags, facts, fields = collect(user, filters)
    if not rows:
        raise problem(
            422, "export_empty", "No documents match this filter, so there is nothing to export."
        )
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    return StreamingResponse(
        chunks(build(rows, tags, facts, fields)),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="docuhive-export-{stamp}.zip"'},
    )
