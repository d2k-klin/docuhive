"""`meta.json`: each document's description in the vault, always rendered from the database.

The file is what keeps the archive readable without DocuHive, so it holds everything except
the text (which `archive.pdf` carries).
"""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from docuhive import db, jobs, vault
from docuhive.contracts import FactValue, SourceInfo
from docuhive.db.models import Document, Note, User

from .migrate import CURRENT as SCHEMA
from .migrate import upgrade


class NoteV1(BaseModel):
    author: str
    body: str
    created_at: datetime


class MetaV1(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_: int = Field(default=SCHEMA, alias="schema")
    id: str
    sha256: str
    original_filename: str
    mime: str
    pages: int | None
    added_at: datetime
    owner: str
    shared: bool
    source: SourceInfo
    title: str | None
    document_date: date | None
    language: str | None
    category: str | None
    document_type: str | None
    correspondent: str | None
    tags: list[str]
    facts: dict[str, FactValue]
    notes: list[NoteV1]
    ai: dict[str, Any]
    manual_fields: list[str]
    deleted_at: datetime | None

    def dump(self) -> bytes:
        data = self.model_dump(mode="json", by_alias=True)
        return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()


def load(path: Path) -> MetaV1:
    """Read a `meta.json`, upgrading older schema versions in memory."""
    return MetaV1.model_validate(upgrade(json.loads(path.read_text(encoding="utf-8"))))


def json_schema() -> bytes:
    schema = MetaV1.model_json_schema(by_alias=True)
    return (json.dumps(schema, indent=2) + "\n").encode()


def render(doc_id: str) -> MetaV1:
    from docuhive import documents

    view = documents.get(doc_id)
    with db.session() as session:
        doc = session.get(Document, doc_id)
        assert doc is not None
        owner = session.scalar(select(User.username).where(User.id == doc.owner_id)) or ""
        notes = [
            NoteV1(author=author or "", body=note.body, created_at=note.created_at)
            for note, author in session.execute(
                select(Note, User.username)
                .outerjoin(User, User.id == Note.user_id)
                .where(Note.document_id == doc_id)
                .order_by(Note.created_at, Note.id)
            )
        ]
        sha, ai = doc.sha256, dict(doc.ai_provenance or {})
    return MetaV1(
        id=view.id,
        sha256=sha,
        original_filename=view.source.original_filename,
        mime=view.mime,
        pages=view.pages,
        added_at=view.added_at,
        owner=owner,
        shared=view.shared,
        source=view.source,
        title=view.title,
        document_date=view.document_date,
        language=view.language,
        category=view.category,
        document_type=view.document_type,
        correspondent=view.correspondent,
        tags=view.tags,
        facts=view.facts,
        notes=notes,
        ai=ai,
        manual_fields=view.manual_fields,
        deleted_at=view.deleted_at,
    )


def write(doc_id: str) -> None:
    """Render and write `meta.json`; raises VaultUnavailable or OSError."""
    with db.session() as session:
        vault_path = session.scalar(select(Document.vault_path).where(Document.id == doc_id))
    if not vault_path:
        return  # not stored yet: ingest writes it with the files
    vault.require()
    vault.write_atomic(vault.root() / vault_path / "meta.json", render(doc_id).dump())


def write_or_queue(doc_id: str) -> None:
    try:
        write(doc_id)
    except (vault.VaultUnavailable, OSError):  # the database already holds the truth
        jobs.enqueue(
            "vault.repair_meta", {"document_id": doc_id}, dedupe_key=f"vault.repair_meta:{doc_id}"
        )


@jobs.handler("vault.repair_meta", max_attempts=20)
def repair(payload: dict, ctx: Any) -> None:
    try:
        write(payload["document_id"])
    except vault.VaultUnavailable as error:
        ctx.defer(datetime.now(UTC) + timedelta(minutes=2), f"vault unavailable: {error}")
