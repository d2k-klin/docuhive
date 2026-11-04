"""Semantic search (contract I8) and similar documents over doc_chunks.

Postgres: pgvector cosine distance with the HNSW index. Other databases (SQLite tests):
cosine in Python over the visible chunks, same results at small scale.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Float, Select, func, literal, select, text

from docuhive import auth, db
from docuhive.ai import coretables
from docuhive.ai.embeddings import cosine, embedder
from docuhive.contracts import CurrentUser, SearchFilters, SemanticHit
from docuhive.index.filters import conditions
from docuhive.index.models import DocChunk


def _visible(user: CurrentUser, filters: SearchFilters | None) -> Select:
    d = coretables.table("documents")
    rule = (
        auth.visible_docs_incl_trash(user)
        if filters and filters.include_trashed
        else auth.visible_docs(user)
    )
    return (
        select(DocChunk.document_id, DocChunk.chunk_no, DocChunk.text)
        .join(d, d.c.id == DocChunk.document_id)
        .where(rule, d.c.status == "stored", *conditions(filters))
    )


def _nearest(
    base: Select, vector: list[float], k: int, exclude: str | None = None
) -> list[SemanticHit]:
    if exclude:
        base = base.where(DocChunk.document_id != exclude)
    with db.session() as s:
        if s.get_bind().dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            s.execute(text("SET LOCAL hnsw.ef_search = 100"))
            dist = DocChunk.embedding.op("<=>", return_type=Float)(
                literal(vector, Vector(len(vector)))
            )
            rows: Sequence[Any] = s.execute(
                base.add_columns((1 - dist).label("score")).order_by(dist).limit(k * 4)
            ).all()
        else:
            scored = [
                (*r[:3], cosine(r[3], vector))
                for r in s.execute(base.add_columns(DocChunk.embedding)).all()
            ]
            rows = sorted(scored, key=lambda r: -r[3])[: k * 4]
    best: dict[str, SemanticHit] = {}
    for doc_id, chunk_no, chunk_text, score in rows:  # best chunk per document
        if doc_id not in best or score > best[doc_id].score:
            best[doc_id] = SemanticHit(
                document_id=doc_id, score=float(score), chunk_no=chunk_no, text=chunk_text
            )
    return sorted(best.values(), key=lambda h: -h.score)[:k]


def semantic_search(
    user: CurrentUser, query: str, filters: SearchFilters, k: int
) -> list[SemanticHit]:
    emb = embedder()
    if emb is None or not query.strip():
        return []
    return _nearest(_visible(user, filters), emb.embed([query])[0], k)


def available() -> bool:
    return embedder() is not None


def similar(user: CurrentUser, doc_id: str, k: int = 8) -> list[SemanticHit]:
    """Nearest documents to the mean of this document's chunk vectors."""
    with db.session() as s:
        if s.get_bind().dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            from docuhive.index.models import DIMS

            vec = s.scalar(
                select(func.avg(DocChunk.embedding, type_=Vector(DIMS))).where(
                    DocChunk.document_id == doc_id
                )
            )
            vector = [float(x) for x in vec] if vec is not None else None
        else:
            vs = list(s.scalars(select(DocChunk.embedding).where(DocChunk.document_id == doc_id)))
            vector = [sum(col) / len(vs) for col in zip(*vs, strict=True)] if vs else None
    if vector is None:
        return []
    return _nearest(_visible(user, None), vector, k, exclude=doc_id)
