"""Rebuild the database from the vault: the proof that the vault is the source of truth.

Walks `<YYYY>/<doc_id>/meta.json`, upserts every document with its owner, sender, tags, facts,
source and notes, re-reads the text from `archive.pdf`, and asks the AI track to re-index
(not re-classify). Safe to repeat; `--dry-run` only validates.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from docuhive import db, documents, jobs, vault
from docuhive.db.models import DocFact, DocSource, Document, DocumentTag, Note, User
from docuhive.ingest.text import extract_text

from . import meta
from .health import YEAR

ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


class RebuildError(BaseModel):
    path: str
    error: str


class RebuildReport(BaseModel):
    dry_run: bool
    documents: int
    created: int
    updated: int
    users_created: list[str]
    errors: list[RebuildError]


def folders(root: Path) -> list[Path]:
    return sorted(
        folder
        for year in root.iterdir()
        if year.is_dir() and YEAR.match(year.name)
        for folder in year.iterdir()
        if folder.is_dir() and ULID.match(folder.name)
    )


def owner_id(session: Session, username: str, created: list[str]) -> int:
    found = session.scalar(select(User.id).where(User.username == username))
    if found is not None:
        return found
    # Disabled until an administrator sets a password (`docuhive user passwd`).
    user = User(username=username, pw_hash="!rebuilt", role="member")
    session.add(user)
    session.flush()
    created.append(username)
    return user.id


def upsert(
    session: Session, data: meta.MetaV1, rel: str, content: str, users: list[str]
) -> tuple[bool, int]:
    """Returns (created, owner id)."""
    owner = owner_id(session, data.owner, users)
    doc = session.get(Document, data.id)
    created = doc is None
    if doc is None:
        doc = Document(id=data.id, added_at=data.added_at)
        session.add(doc)
    doc.owner_id, doc.shared, doc.status = owner, data.shared, "stored"
    doc.sha256, doc.mime, doc.pages, doc.vault_path = data.sha256, data.mime, data.pages, rel
    doc.title, doc.document_date, doc.language = data.title, data.document_date, data.language
    doc.fts_config = documents.FTS_CONFIGS.get(data.language or "", "dh_simple")
    doc.category, doc.document_type = data.category, data.document_type
    doc.manual_fields, doc.ai_provenance = data.manual_fields, data.ai
    doc.content, doc.quarantine_reason, doc.deleted_at = content, None, data.deleted_at
    doc.updated_at = datetime.now(UTC)
    session.flush()
    doc.correspondent_id = documents._correspondent_id(session, data.correspondent)
    session.execute(delete(DocumentTag).where(DocumentTag.document_id == data.id))
    session.flush()
    for tag_id in {documents._tag_id(session, name) for name in data.tags}:
        session.add(DocumentTag(document_id=data.id, tag_id=tag_id))
    stored = session.scalars(select(DocFact.field).where(DocFact.document_id == data.id))
    for field in {*data.facts, *stored}:
        documents._write_fact(session, data.id, field, data.facts.get(field))
    session.merge(DocSource(document_id=data.id, **data.source.model_dump()))
    session.execute(delete(Note).where(Note.document_id == data.id))
    for note in data.notes:
        author = owner_id(session, note.author, users) if note.author else owner
        session.add(
            Note(document_id=data.id, user_id=author, body=note.body, created_at=note.created_at)
        )
    session.flush()
    documents.refresh_tsv(session, data.id)
    return created, owner


def rebuild(*, dry_run: bool = False) -> RebuildReport:
    vault.require()
    root = vault.root()
    report = RebuildReport(
        dry_run=dry_run, documents=0, created=0, updated=0, users_created=[], errors=[]
    )
    for folder in folders(root):
        rel = str(folder.relative_to(root))
        try:
            data = meta.load(folder / "meta.json")
            if data.id != folder.name:
                raise ValueError("meta.json id does not match its folder")
            archive = folder / "archive.pdf"
            content = extract_text(archive) if archive.is_file() else ""
        except Exception as error:  # one unreadable folder must not stop the others
            report.errors.append(RebuildError(path=rel, error=reason(error)))
            continue
        report.documents += 1
        if dry_run:
            continue
        try:
            with db.session() as session:
                created, owner = upsert(session, data, rel, content, report.users_created)
                # Re-index (not re-classify): the metadata came from the vault.
                jobs.enqueue(
                    "document.stored",
                    {
                        "document_id": data.id,
                        "owner_id": owner,
                        "source_kind": data.source.kind.value,
                        "hints": {"rebuild": "true"},
                    },
                    queue="ai",
                    dedupe_key=f"document.stored:{data.id}",
                    in_session=session,
                )
        except SQLAlchemyError as error:
            report.documents -= 1
            report.errors.append(RebuildError(path=rel, error=reason(error)))
            continue
        report.created += created
        report.updated += not created
    return report


def reason(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return f"meta.json does not match the schema ({error.error_count()} problems)"
    if isinstance(error, SQLAlchemyError):
        cause = getattr(error, "orig", None) or error
        return f"database rejected the document ({type(cause).__name__})"
    if isinstance(error, OSError | ValueError):
        return str(error).splitlines()[0][:300]
    return f"{type(error).__name__}: unreadable"


def migrate_files() -> dict:
    """Rewrite every `meta.json` older than the current schema; newer readers stay compatible."""
    vault.require()
    root, rewritten, errors = vault.root(), 0, []
    for folder in folders(root):
        path = folder / "meta.json"
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("schema") != meta.SCHEMA:
                vault.write_atomic(path, meta.load(path).dump())
                rewritten += 1
        except Exception as error:
            errors.append({"path": str(folder.relative_to(root)), "error": reason(error)})
    vault.write_atomic(root / "meta.schema.json", meta.json_schema())
    return {"rewritten": rewritten, "errors": errors}
