"""PostgreSQL full-text candidates for hybrid search: documents, and knowledge-base chunks."""

from datetime import date
from functools import reduce

from sqlalchemy import (
    ColumnElement,
    Table,
    cast,
    column,
    func,
    literal,
    literal_column,
    select,
    table,
    true,
)
from sqlalchemy.dialects.postgresql import REGCONFIG, TSQUERY, TSVECTOR
from sqlalchemy.orm import Session

from docuhive import auth, db
from docuhive.ai import coretables
from docuhive.contracts import CurrentUser, SearchFilters
from docuhive.search import MAX_CHUNKS_PER_DOC
from docuhive.search.filters import conditions

# ponytail: the three configurations migration 0001 creates; derive from the taxonomy's
# `languages` once a fourth language gets its own configuration.
CONFIGS = ("dh_german", "dh_english", "dh_simple")
HEADLINE = "StartSel=\u0002, StopSel=\u0003, MaxFragments=2, MaxWords=25, MinWords=8"
TYPO_MIN_HITS = 5  # below this, add trigram matches on titles and senders
TYPO_SIMILARITY = 0.3

# doc_chunks belongs to the index module (intel migrations); refer to it by name only.
# ponytail: tsvector computed per query until doc_chunks.tsv lands (integration point I13).
CHUNKS = table("doc_chunks", column("document_id"), column("chunk_no"), column("text"))


def tsquery(query: str) -> ColumnElement:
    """`websearch_to_tsquery` in every configuration, ORed: stems from any language match."""
    parts = [
        func.websearch_to_tsquery(cast(literal(c), REGCONFIG), query, type_=TSQUERY)
        for c in CONFIGS
    ]
    return reduce(lambda a, b: a.op("||", return_type=TSQUERY)(b), parts)


def _documents() -> Table:
    return coretables.table("documents")


def _visible(user: CurrentUser, filters: SearchFilters) -> list[ColumnElement[bool]]:
    d = _documents()
    rule = (
        auth.visible_docs_incl_trash(user) if filters.include_trashed else auth.visible_docs(user)
    )
    return [rule, d.c.status == "stored", *conditions(filters)]


def _doc_vector(d: Table) -> ColumnElement:
    # ponytail: computed when content_tsv is empty (ingest fills it); the GIN index only
    # helps once it is filled.
    computed = func.setweight(
        func.to_tsvector(d.c.fts_config, func.coalesce(d.c.title, ""), type_=TSVECTOR),
        literal_column("'A'"),  # setweight takes "char"; a bound parameter would be varchar
    ).op("||", return_type=TSVECTOR)(
        func.to_tsvector(d.c.fts_config, func.coalesce(d.c.content, ""), type_=TSVECTOR)
    )
    return func.coalesce(d.c.content_tsv, computed, type_=TSVECTOR)


def documents(user: CurrentUser, query: str, filters: SearchFilters, limit: int) -> list[str]:
    """Visible document ids, best first; trigram matches on titles and senders rank last."""
    d = _documents()
    q, vec = tsquery(query), _doc_vector(d)
    visible = _visible(user, filters)
    with db.session() as s:
        ids = list(
            s.scalars(
                select(d.c.id)
                .where(*visible, vec.op("@@")(q))
                .order_by(func.ts_rank_cd(vec, q, 32).desc(), d.c.id)
                .limit(limit)
            )
        )
        if len(ids) < TYPO_MIN_HITS:
            ids += _typos(s, user, query, filters, ids, limit - len(ids))
    return ids


def _typos(
    session: Session,
    user: CurrentUser,
    query: str,
    filters: SearchFilters,
    excluded: list[str],
    limit: int,
    *,
    chunked: bool = False,
) -> list[str]:
    d, c = _documents(), coretables.table("correspondents")
    sim = func.greatest(
        func.similarity(func.coalesce(d.c.title, ""), query),
        func.similarity(func.coalesce(c.c.name, ""), query),
    )
    return list(
        session.scalars(
            select(d.c.id)
            .outerjoin(c, c.c.id == d.c.correspondent_id)
            .where(
                *_visible(user, filters),
                sim >= TYPO_SIMILARITY,
                d.c.id.not_in(excluded) if excluded else true(),
                d.c.id.in_(select(CHUNKS.c.document_id)) if chunked else true(),
            )
            .order_by(sim.desc(), d.c.id)
            .limit(max(0, limit))
        )
    )


def headlines(ids: list[str], query: str) -> dict[str, tuple[str | None, str]]:
    """{id: (title, highlighted snippet)}; `ts_headline` is expensive, so only for one page."""
    if not ids:
        return {}
    d = _documents()
    hl = func.ts_headline(d.c.fts_config, func.coalesce(d.c.content, ""), tsquery(query), HEADLINE)
    with db.session() as s:
        rows = s.execute(select(d.c.id, d.c.title, hl).where(d.c.id.in_(ids))).all()
    return {r[0]: (r[1], r[2]) for r in rows}


def chunks(
    user: CurrentUser, query: str, filters: SearchFilters, limit: int
) -> list[tuple[str, int, str]]:
    """Visible chunks matching the query, best first: (document_id, chunk_no, text)."""
    d = _documents()
    q = tsquery(query)
    vec = func.to_tsvector(d.c.fts_config, CHUNKS.c.text, type_=TSVECTOR)
    rank = func.ts_rank_cd(vec, q, 32)
    ranked = (
        select(
            CHUNKS.c.document_id,
            CHUNKS.c.chunk_no,
            CHUNKS.c.text,
            rank.label("score"),
            func.row_number()
            .over(
                partition_by=CHUNKS.c.document_id,
                order_by=(rank.desc(), CHUNKS.c.chunk_no),
            )
            .label("position"),
        )
        .join(d, d.c.id == CHUNKS.c.document_id)
        .where(*_visible(user, filters), vec.op("@@")(q))
        .subquery()
    )
    with db.session() as s:
        rows = s.execute(
            select(ranked.c.document_id, ranked.c.chunk_no, ranked.c.text)
            .where(ranked.c.position <= MAX_CHUNKS_PER_DOC)
            .order_by(ranked.c.score.desc(), ranked.c.document_id, ranked.c.chunk_no)
            .limit(limit)
        ).all()
        ids = list(dict.fromkeys(r[0] for r in rows))
        if len(ids) < TYPO_MIN_HITS and len(rows) < limit:
            typo_ids = _typos(s, user, query, filters, ids, limit - len(rows), chunked=True)
            if typo_ids:
                first = (
                    select(CHUNKS.c.document_id, func.min(CHUNKS.c.chunk_no).label("n"))
                    .where(CHUNKS.c.document_id.in_(typo_ids))
                    .group_by(CHUNKS.c.document_id)
                    .subquery()
                )
                extra = s.execute(
                    select(CHUNKS.c.document_id, CHUNKS.c.chunk_no, CHUNKS.c.text).join(
                        first,
                        (first.c.document_id == CHUNKS.c.document_id)
                        & (first.c.n == CHUNKS.c.chunk_no),
                    )
                ).all()
                by_id = {r[0]: r for r in extra}
                rows = [*rows, *(by_id[doc_id] for doc_id in typo_ids if doc_id in by_id)]
    return [(r[0], r[1], r[2]) for r in rows]


def details(ids: list[str]) -> dict[str, tuple[str | None, date | None, str | None]]:
    """{id: (title, document_date, category)} for the documents behind retrieved chunks."""
    if not ids:
        return {}
    d = _documents()
    with db.session() as s:
        rows = s.execute(
            select(d.c.id, d.c.title, d.c.document_date, d.c.category).where(d.c.id.in_(ids))
        ).all()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}
