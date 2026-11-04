"""Search contract (§2.7): document search, chunk retrieval, and the semantic registration points.

Both lists are fused with reciprocal rank fusion (RRF): `score = Σ 1 / (60 + rank)` over the
lists an item appears in, using ranks only, so FTS and cosine scores never need to be compared.
"""

from collections import Counter
from collections.abc import Callable, Hashable, Sequence
from typing import Literal
from urllib.parse import quote

from docuhive.contracts import ChunkHit, CurrentUser, SearchFilters, SearchHit, SemanticHit

SemanticFn = Callable[[CurrentUser, str, SearchFilters, int], list[SemanticHit]]

CANDIDATES = 50  # taken from each list before fusion
RRF_K = 60
MAX_CHUNKS_PER_DOC = 3  # so one long document cannot fill a retrieval result

_semantic: SemanticFn | None = None  # best chunk per document
_chunk_semantic: SemanticFn | None = None  # several chunks per document


class SemanticUnavailable(Exception):
    """mode="semantic" was requested, but no semantic search is registered (AI disabled)."""


def register_semantic(fn: SemanticFn) -> None:
    global _semantic
    _semantic = fn


def register_chunk_semantic(fn: SemanticFn) -> None:
    global _chunk_semantic
    _chunk_semantic = fn


def rrf[K: Hashable](*ranked: Sequence[K]) -> list[tuple[K, float, list[int | None]]]:
    """[(item, fused score, 1-based rank in each list or None)], best first."""
    ranks: dict[K, list[int | None]] = {}
    for i, items in enumerate(ranked):
        for rank, item in enumerate(items, 1):
            slot = ranks.setdefault(item, [None] * len(ranked))
            if slot[i] is None:
                slot[i] = rank
    scored = [(item, sum(1 / (RRF_K + r) for r in rs if r), rs) for item, rs in ranks.items()]
    return sorted(scored, key=lambda t: -t[1])  # stable: ties keep first-seen order


def hybrid(
    user: CurrentUser,
    query: str,
    filters: SearchFilters,
    limit: int = 20,
    mode: Literal["hybrid", "fts", "semantic"] = "hybrid",
) -> list[SearchHit]:
    """Documents for a query. Without a registered semantic search, "hybrid" is FTS only."""
    from docuhive.search import fts  # Postgres-only; keeps the contract importable anywhere

    if mode == "semantic" and _semantic is None:
        raise SemanticUnavailable
    if not query.strip() or limit <= 0:
        return []
    fts_ids = [] if mode == "semantic" else fts.documents(user, query, filters, CANDIDATES)
    sem = _semantic(user, query, filters, CANDIDATES) if _semantic and mode != "fts" else []
    fused = rrf(fts_ids, [h.document_id for h in sem])[:limit]
    meta = fts.headlines([doc_id for doc_id, *_ in fused], query)
    chunk_text = {h.document_id: h.text for h in sem}
    return [
        SearchHit(
            document_id=doc_id,
            title=meta.get(doc_id, (None, ""))[0],
            snippet=meta[doc_id][1] if fts_rank else chunk_text[doc_id][:300],
            score=score,
            fts_rank=fts_rank,
            semantic_rank=semantic_rank,
        )
        for doc_id, score, (fts_rank, semantic_rank) in fused
    ]


def retrieve(
    user: CurrentUser,
    query: str,
    filters: SearchFilters,
    k: int = 20,
    mode: Literal["hybrid", "fts", "semantic"] = "hybrid",
) -> list[ChunkHit]:
    """Chunks for a knowledge base (KB-02), at most MAX_CHUNKS_PER_DOC per document.

    Only documents that have been chunked and embedded have chunks, so FTS here covers the
    indexed part of the archive; `hybrid` covers every stored document.
    """
    from docuhive.search import fts

    if mode == "semantic" and _chunk_semantic is None:
        raise SemanticUnavailable
    if not query.strip() or k <= 0:
        return []
    lexical = [] if mode == "semantic" else fts.chunks(user, query, filters, CANDIDATES)
    sem = (
        _chunk_semantic(user, query, filters, CANDIDATES)
        if _chunk_semantic and mode != "fts"
        else []
    )
    text = {(d, n): t for d, n, t in lexical} | {(h.document_id, h.chunk_no): h.text for h in sem}
    picked: list[tuple[tuple[str, int], float, list[int | None]]] = []
    per_doc: Counter[str] = Counter()
    fused = rrf([(d, n) for d, n, _ in lexical], [(h.document_id, h.chunk_no) for h in sem])
    for key, score, ranks in fused:
        if per_doc[key[0]] < MAX_CHUNKS_PER_DOC:
            per_doc[key[0]] += 1
            picked.append((key, score, ranks))
            if len(picked) == k:
                break
    meta = fts.details(list(per_doc))
    hits = []
    for (doc_id, chunk_no), score, (fts_rank, semantic_rank) in picked:
        title, document_date, category = meta.get(doc_id, (None, None, None))
        hits.append(
            ChunkHit(
                document_id=doc_id,
                chunk_no=chunk_no,
                text=text[(doc_id, chunk_no)],
                score=score,
                fts_rank=fts_rank,
                semantic_rank=semantic_rank,
                title=title,
                document_date=document_date,
                category=category,
                url=f"/documents/{quote(doc_id, safe='')}",
            )
        )
    return hits
