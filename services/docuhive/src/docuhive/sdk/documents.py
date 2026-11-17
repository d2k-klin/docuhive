"""Documents for plugins. Every listing takes the user it is for: there is no "all documents"."""

from datetime import date
from typing import Any

from sqlalchemy import select

from docuhive import auth, db
from docuhive import documents as core
from docuhive.contracts import (
    CurrentUser,
    DocumentView,
    FactValue,
    MetadataPatch,
    SearchFilters,
)
from docuhive.db.models import Document as Document_

from ._plugin import current

NotFound = core.NotFound


def get(document_id: str) -> DocumentView:
    """A document by id, regardless of who may see it: for event handlers. Use `get_for_user`
    for anything you show to a person."""
    current().require("documents:read")
    return core.get(document_id)


def get_for_user(document_id: str, user: CurrentUser) -> DocumentView:
    current().require("documents:read")
    return core.get_for_user(document_id, user)


def original(document_id: str) -> bytes:
    """The file exactly as it arrived (for example a bank's statement export)."""
    from docuhive import vault
    from docuhive.db.models import Document

    current().require("documents:read")
    with db.session() as s:
        vault_path = s.scalar(select(Document.vault_path).where(Document.id == document_id))
    if not vault_path:
        raise NotFound(document_id)
    root = vault.root().resolve()
    path = vault.original(root / vault_path)
    if path is None or not path.resolve().is_relative_to(root):
        raise NotFound(document_id)
    return path.read_bytes()


def archive_pdf(document_id: str) -> bytes:
    """The searchable PDF the archive keeps for every document (for bundles and letters)."""
    from docuhive import vault
    from docuhive.db.models import Document

    current().require("documents:read")
    with db.session() as s:
        vault_path = s.scalar(select(Document.vault_path).where(Document.id == document_id))
    root = vault.root().resolve()
    path = (root / vault_path / "archive.pdf").resolve() if vault_path else None
    if path is None or not path.is_relative_to(root) or not path.is_file():
        raise NotFound(document_id)
    return path.read_bytes()


def content(document_id: str, max_chars: int | None = 20000) -> str:
    current().require("documents:read")
    return core.get_content(document_id, max_chars)


def find(
    user: CurrentUser,
    *,
    document_type: str | list[str] | None = None,
    category: str | list[str] | None = None,
    tags: list[str] | None = None,
    correspondent: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    year: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[DocumentView]:
    """Documents this user may see, newest first. A category includes its subcategories."""
    from docuhive.db.models import Document
    from docuhive.search.filters import conditions

    current().require("documents:read")
    if year is not None:
        date_from, date_to = date(year, 1, 1), date(year, 12, 31)
    filters = SearchFilters(
        document_types=[document_type] if isinstance(document_type, str) else document_type or [],
        categories=[category] if isinstance(category, str) else category or [],
        tags=tags or [],
        correspondents=[correspondent] if correspondent else [],
        date_from=date_from,
        date_to=date_to,
    )
    with db.session() as s:
        ids = list(
            s.scalars(
                select(Document.id)
                .where(auth.visible_docs(user), Document.status == "stored", *conditions(filters))
                .order_by(Document.document_date.desc().nulls_last(), Document.id.desc())
                .limit(min(limit, 1000))
                .offset(offset)
            )
        )
    return [core.get(i) for i in ids]


def _describe(plugin_id: str, document_id: str, **changes: Any) -> list[str]:
    if "facts" in changes and changes["facts"] is not None:
        changes["facts"] = {
            k: (FactValue.model_validate(v) if isinstance(v, dict) else v)
            for k, v in changes["facts"].items()
        }
    return core.apply_metadata(
        document_id, MetadataPatch(**changes), actor=f"plugin:{plugin_id}"
    ).applied


def apply_metadata(document_id: str, **changes: Any) -> list[str]:
    """Set title, category, document_type, correspondent, document_date, tags_add, tags_remove
    or facts ({name: FactValue | dict | None}). Values a person set are never overwritten.
    Returns the fields that changed."""
    registry = current()
    registry.require("documents:write-metadata")
    return _describe(registry.id, document_id, **changes)


def hold(
    document_id: str,
    reason: str,
    *,
    fields: list[str] | None = None,
    until: date | None = None,
) -> int:
    """Make a document (or the listed fields: "title", "facts.amount_total", "facts") unchangeable
    for everyone, people included, until `until` or until an administrator lifts it. Use
    `sdk.retention.until(kind, year)` for retention dates. Returns the hold's id."""
    from docuhive.documents import holds

    registry = current()
    registry.require("documents:hold")
    with db.session() as s:
        if s.get(Document_, document_id) is None:
            raise NotFound(document_id)
        made = holds.place(
            s, document_id, reason, placed_by=f"plugin:{registry.id}", fields=fields, until=until
        )
        hold_id = made.id
    from docuhive.vault.meta import write_or_queue

    write_or_queue(document_id)
    return hold_id


def holds(document_id: str) -> list[dict]:
    """The active holds of a document: [{id, reason, fields, until, placed_by}]."""
    from docuhive.documents import holds as held

    current().require("documents:read")
    with db.session() as s:
        return [
            {
                "id": h.id,
                "reason": h.reason,
                "fields": h.fields,
                "until": h.until,
                "placed_by": h.placed_by,
            }
            for h in held.active(s, document_id)
        ]


def create(
    user: CurrentUser,
    content: bytes,
    *,
    filename: str,
    title: str | None = None,
    category: str | None = None,
    document_type: str | None = None,
    tags: list[str] | tuple[str, ...] = (),
    facts: dict[str, Any] | None = None,
    shared: bool = False,
    derived_from: list[str] | tuple[str, ...] = (),
    document_date: date | None = None,
    correspondent: str | None = None,
) -> str:
    """Add a document the plugin made (a PDF invoice, a letter, a sent mail) to `user`'s archive.

    It is stored, converted and made searchable like an upload, but not classified: you say
    what it is. Private unless `shared`. The same bytes again return the existing document's
    id. `derived_from` links it to the documents it was made from, both ways."""
    registry = current()
    registry.require("documents:create")
    for source in derived_from:
        core.get_for_user(source, user)  # only from documents this person may see
    result = _submit(
        user,
        content,
        filename,
        shared=shared,
        derived_from=list(derived_from),
        hints={"plugin": registry.id, "skip_ai": "1"},
    )
    if result.status == "staged":  # describing what it created is part of creating it
        _describe(
            registry.id,
            result.document_id,
            title=title,
            category=category,
            document_type=document_type,
            tags_add=list(tags),
            facts=facts,
            document_date=document_date,
            correspondent=correspondent,
        )
    return result.document_id


def _submit(
    user: CurrentUser,
    content: bytes,
    filename: str,
    *,
    shared: bool,
    derived_from: list[str],
    hints: dict[str, str],
) -> Any:
    import re
    import tempfile
    from pathlib import Path

    from docuhive import ingest
    from docuhive.contracts import IngestRequest, SourceInfo, SourceKind

    safe = re.sub(r"[^\w.\- ]+", "_", Path(filename).name).strip() or "document.pdf"
    folder = Path(tempfile.mkdtemp(dir=ingest.incoming_dir()))
    path = folder / safe
    path.write_bytes(content)
    try:
        return ingest.submit(
            [path],
            IngestRequest(
                owner_id=user.id,
                shared=shared,
                source=SourceInfo(
                    kind=SourceKind.plugin,
                    original_filename=safe,
                    generator=current().id,
                    derived_from=derived_from,
                ),
                hints=hints,
            ),
        )
    finally:
        path.unlink(missing_ok=True)
        folder.rmdir()


def import_file(
    user: CurrentUser,
    content: bytes,
    *,
    filename: str,
    title: str | None = None,
    tags: list[str] | tuple[str, ...] = (),
    correspondent: str | None = None,
    document_date: date | None = None,
    shared: bool = False,
    analyse: bool = True,
) -> tuple[str, str]:
    """Add a file from another archive as if `user` uploaded it: stored, OCRed, indexed and,
    with `analyse`, read by the AI like any upload. The values given are the person's own (they
    set them in the other archive), so the AI never overwrites them. Only for an import the
    person started. Returns (document id, "staged" or "duplicate")."""
    registry = current()
    registry.require("documents:import")
    hints = {"plugin": registry.id} | ({} if analyse else {"skip_ai": "1"})
    result = _submit(user, content, filename, shared=shared, derived_from=[], hints=hints)
    if result.status == "staged":
        patch = MetadataPatch(
            title=" ".join((title or "").split())[:120] or None,
            correspondent=correspondent or None,
            document_date=document_date,
            tags_add=[t.strip()[:64] for t in tags if t.strip()],
        )
        core.apply_metadata(result.document_id, patch, actor=f"user:{user.id}")
    return result.document_id, result.status
