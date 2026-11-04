"""Tags and senders are shared by the household: rename them, or merge duplicates into one.

A merge re-points every document, keeps the old row with `merged_into` (so the AI's later
"Stadtwerke Muster GmbH" still resolves to the survivor), records the change, and refreshes
the affected documents' `meta.json` and search vectors.
"""

from typing import Any, Literal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from docuhive import db, jobs
from docuhive.db.models import (
    AuditLog,
    Correspondent,
    Document,
    DocumentTag,
    KnowledgeBase,
    SavedView,
    Tag,
)
from docuhive.vault import meta

from . import norm_name, refresh_tsv, slug

Kind = Literal["tag", "correspondent"]


class VocabularyError(ValueError):
    pass


def _lock(session: Session, kind: Kind, item_ids: list[int]) -> dict[int, Any]:
    """Lock every participant in id order (no deadlocks), then re-check them under the lock:
    overlapping merges or renames wait for each other instead of interleaving."""
    model: Any = Tag if kind == "tag" else Correspondent
    rows = {
        row.id: row
        for row in session.scalars(
            select(model).where(model.id.in_(item_ids)).order_by(model.id).with_for_update()
        )
    }
    for item_id in item_ids:
        row = rows.get(item_id)
        if row is None or row.merged_into is not None:
            raise VocabularyError(f"Unknown {kind}: {item_id}")
    return rows


def restricted_tags() -> set[str]:
    """Tags that keep documents on local AI (routing.yaml privacy settings)."""
    try:
        from docuhive.ai import routing
    except ImportError:  # the platform without the AI extension has no restricted tags
        return set()
    return {slug(tag) for tag in routing.load().privacy.restricted_tags}


def _rewrite_filters(session: Session, kind: Kind, old: list[str], new: str) -> None:
    """Saved views and knowledge bases match by name: keep them pointing at the survivor."""
    field = "tags" if kind == "tag" else "correspondents"
    models: tuple[Any, ...] = (SavedView, KnowledgeBase)
    for model in models:
        for row in session.scalars(select(model).with_for_update()):
            names = list((row.filters or {}).get(field) or [])
            if any(name in old for name in names):
                updated = list(dict.fromkeys(new if name in old else name for name in names))
                row.filters = {**row.filters, field: updated}


def rename(kind: Kind, item_id: int, name: str, *, actor: str) -> list[str]:
    """Returns the affected document ids. Renaming onto an existing name is a merge instead."""
    name = " ".join(name.split())
    if not 1 <= len(name) <= (64 if kind == "tag" else 200):
        raise VocabularyError("Choose a name of 1–64 characters for a tag, 200 for a sender")
    with db.session() as session:
        row = _lock(session, kind, [item_id])[item_id]
        if kind == "tag" and row.slug in restricted_tags() and slug(name) != row.slug:
            raise VocabularyError(
                "This tag keeps documents on local AI; change the privacy settings first"
            )
        key = slug(name) if kind == "tag" else norm_name(name)
        column = Tag.slug if kind == "tag" else Correspondent.norm_name
        model = Tag if kind == "tag" else Correspondent
        clash = session.scalar(select(model.id).where(column == key, model.id != item_id))
        if clash is not None:
            raise VocabularyError("That name is taken; merge the two instead")
        before = row.name
        row.name = name
        if isinstance(row, Tag):
            row.slug = key
        else:
            row.norm_name = key
        ids = _documents(session, kind, [item_id])
        _rewrite_filters(session, kind, [before], name)
        session.add(
            AuditLog(
                actor=actor,
                action=f"vocabulary.rename_{kind}",
                before={"id": item_id, "name": before},
                after={"id": item_id, "name": name},
            )
        )
        session.flush()
        _changed(session, kind, ids, actor)
    return ids


def merge(kind: Kind, source_ids: list[int], target_id: int, *, actor: str) -> list[str]:
    """Move every document from the sources to the target; returns the affected document ids."""
    sources = sorted(set(source_ids) - {target_id})
    if not sources:
        raise VocabularyError("Choose at least one item to merge into another")
    with db.session() as session:
        rows = _lock(session, kind, sorted([*sources, target_id]))
        target, names = rows[target_id], [rows[item].name for item in sources]
        if kind == "tag":
            restricted = restricted_tags()
            if target.slug not in restricted and any(rows[i].slug in restricted for i in sources):
                raise VocabularyError(
                    "A tag that keeps documents on local AI can only be merged into another one"
                )
        ids = _documents(session, kind, sources)
        _rewrite_filters(session, kind, names, target.name)
        if kind == "tag":
            for doc_id in ids:
                linked = set(
                    session.scalars(
                        select(DocumentTag.tag_id).where(DocumentTag.document_id == doc_id)
                    )
                )
                for tag_id in linked & set(sources):
                    session.delete(session.get(DocumentTag, (doc_id, tag_id)))
                if target_id not in linked:
                    session.add(DocumentTag(document_id=doc_id, tag_id=target_id))
            session.execute(update(Tag).where(Tag.id.in_(sources)).values(merged_into=target_id))
        else:
            session.execute(
                update(Document)
                .where(Document.correspondent_id.in_(sources))
                .values(correspondent_id=target_id)
            )
            session.execute(
                update(Correspondent)
                .where(Correspondent.id.in_(sources))
                .values(merged_into=target_id)
            )
        # Rows merged into a source now follow it to the target.
        model = Tag if kind == "tag" else Correspondent
        session.execute(
            update(model).where(model.merged_into.in_(sources)).values(merged_into=target_id)
        )
        session.add(
            AuditLog(
                actor=actor,
                action=f"vocabulary.merge_{kind}",
                before={"ids": sources, "names": names},
                after={"id": target_id, "name": target.name, "documents": len(ids)},
            )
        )
        session.flush()
        _changed(session, kind, ids, actor)
    return ids


def _documents(session: Session, kind: Kind, item_ids: list[int]) -> list[str]:
    if kind == "tag":
        query = select(DocumentTag.document_id).where(DocumentTag.tag_id.in_(item_ids))
    else:
        query = select(Document.id).where(Document.correspondent_id.in_(item_ids))
    return sorted(set(session.scalars(query)))


def _changed(session: Session, kind: Kind, ids: list[str], actor: str) -> None:
    """Search vectors, `meta.json` re-renders and AI events, all in the change's transaction."""
    field = "tags" if kind == "tag" else "correspondent"
    # ponytail: one job per document; batch the vault writes if merges reach thousands.
    for doc_id in ids:
        if kind == "correspondent":
            refresh_tsv(session, doc_id)
        meta.queue(session, doc_id)
        jobs.enqueue(
            "document.metadata_changed",
            {"document_id": doc_id, "fields": [field], "actor": actor},
            queue="ai",
            in_session=session,
        )
