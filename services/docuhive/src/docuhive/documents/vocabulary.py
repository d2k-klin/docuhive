"""Tags and senders are shared by the household: rename them, or merge duplicates into one.

A merge re-points every document, keeps the old row with `merged_into` (so the AI's later
"Stadtwerke Muster GmbH" still resolves to the survivor), records the change, and refreshes
the affected documents' `meta.json` and search vectors.
"""

from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from docuhive import db, jobs
from docuhive.db.models import AuditLog, Correspondent, Document, DocumentTag, Tag
from docuhive.vault import meta

from . import norm_name, refresh_tsv, slug

Kind = Literal["tag", "correspondent"]


class VocabularyError(ValueError):
    pass


def _row(session: Session, kind: Kind, item_id: int) -> Tag | Correspondent:
    row: Tag | Correspondent | None = (
        session.get(Tag, item_id) if kind == "tag" else session.get(Correspondent, item_id)
    )
    if row is None or row.merged_into is not None:
        raise VocabularyError(f"Unknown {kind}: {item_id}")
    return row


def rename(kind: Kind, item_id: int, name: str, *, actor: str) -> list[str]:
    """Returns the affected document ids. Renaming onto an existing name is a merge instead."""
    name = " ".join(name.split())
    if not 1 <= len(name) <= (64 if kind == "tag" else 200):
        raise VocabularyError("Choose a name of 1–64 characters for a tag, 200 for a sender")
    with db.session() as session:
        row = _row(session, kind, item_id)
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
        target = _row(session, kind, target_id)
        names = [_row(session, kind, item).name for item in sources]
        ids = _documents(session, kind, sources)
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
