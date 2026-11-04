"""SearchFilters -> SQL conditions on OA's documents table.

ponytail: re-implements the subset CL needs; switch to OA's helper once contracts expose one.
"""

from sqlalchemy import ColumnElement, and_, exists, or_, select

from docuhive.ai import coretables
from docuhive.contracts import SearchFilters


def conditions(f: SearchFilters | None) -> list[ColumnElement[bool]]:
    if f is None:
        return []
    d = coretables.table("documents")
    out: list[ColumnElement[bool]] = []
    if f.categories:  # a parent category includes its children
        out.append(
            or_(*[or_(d.c.category == c, d.c.category.like(f"{c}/%")) for c in f.categories])
        )
    if f.document_types:
        out.append(d.c.document_type.in_(f.document_types))
    if f.document_ids:
        out.append(d.c.id.in_(f.document_ids))
    if f.date_from:
        out.append(d.c.document_date >= f.date_from)
    if f.date_to:
        out.append(d.c.document_date <= f.date_to)
    if f.correspondents:
        c = coretables.table("correspondents")
        out.append(d.c.correspondent_id.in_(select(c.c.id).where(c.c.name.in_(f.correspondents))))
    if f.tags:
        t, dt = coretables.table("tags"), coretables.table("document_tags")
        out.append(
            exists(
                select(dt.c.tag_id)
                .join(t, t.c.id == dt.c.tag_id)
                .where(and_(dt.c.document_id == d.c.id, t.c.name.in_(f.tags)))
            )
        )
    if f.source_kinds:
        s = coretables.table("doc_sources")
        out.append(
            d.c.id.in_(
                select(s.c.document_id).where(s.c.kind.in_([k.value for k in f.source_kinds]))
            )
        )
    return out
