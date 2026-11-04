"""Search fusion without a database: RRF order, ranks, the per-document cap and modes."""

from datetime import date

import pytest
from docuhive import search
from docuhive.contracts import CurrentUser, SearchFilters, SemanticHit

USER = CurrentUser(id=1, username="owner", role="admin")


def test_rrf_rewards_items_found_by_both_lists():
    fused = search.rrf(["a", "b", "c"], ["c", "d"])
    assert [item for item, *_ in fused] == ["c", "a", "b", "d"]
    item, score, ranks = fused[0]
    assert ranks == [3, 1]
    assert score == pytest.approx(1 / 63 + 1 / 61)
    assert dict((i, r) for i, _, r in fused)["d"] == [None, 2]


def test_rrf_keeps_first_seen_order_on_ties_and_first_rank_on_repeats():
    assert [i for i, *_ in search.rrf(["x"], ["y"])] == ["x", "y"]
    assert search.rrf(["x", "x"])[0][2] == [1]


def test_semantic_mode_needs_a_registered_function(monkeypatch):
    monkeypatch.setattr(search, "_semantic", None)
    monkeypatch.setattr(search, "_chunk_semantic", None)
    with pytest.raises(search.SemanticUnavailable):
        search.hybrid(USER, "Strom", SearchFilters(), mode="semantic")
    with pytest.raises(search.SemanticUnavailable):
        search.retrieve(USER, "Strom", SearchFilters(), mode="semantic")


def test_retrieve_caps_chunks_per_document_and_keeps_both_ranks(monkeypatch):
    from docuhive.search import fts

    lexical = [("doc-a", n, f"a{n}") for n in range(5)] + [("doc-b", 0, "b0")]
    semantic = [SemanticHit(document_id="doc-b", score=0.9, chunk_no=0, text="b0")]
    monkeypatch.setattr(fts, "chunks", lambda *a: lexical)
    monkeypatch.setattr(
        fts, "details", lambda ids: {i: (i.upper(), date(2025, 11, 1), "utilities") for i in ids}
    )
    monkeypatch.setattr(search, "_chunk_semantic", lambda *a: semantic)

    hits = search.retrieve(USER, "Strom", SearchFilters(), k=10)

    assert hits[0].document_id == "doc-b"  # found by both lists
    assert (hits[0].fts_rank, hits[0].semantic_rank) == (6, 1)
    assert [h.chunk_no for h in hits if h.document_id == "doc-a"] == [0, 1, 2]
    assert hits[0].title == "DOC-B" and hits[0].category == "utilities"
    assert search.retrieve(USER, "Strom", SearchFilters(), k=2)[1].document_id == "doc-a"


def test_blank_queries_return_nothing(monkeypatch):
    monkeypatch.setattr(search, "_semantic", None)
    assert search.hybrid(USER, "   ", SearchFilters()) == []
    assert search.retrieve(USER, "", SearchFilters()) == []


class CapturingSession:
    """Records each statement compiled for PostgreSQL and returns canned rows."""

    def __init__(self, rows):
        self.rows, self.sql = rows, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _run(self, stmt):
        from sqlalchemy.dialects import postgresql

        self.sql.append(str(stmt.compile(dialect=postgresql.dialect())))
        return self.rows.pop(0) if self.rows else []

    def scalars(self, stmt):
        return iter(self._run(stmt))

    def execute(self, stmt):
        class Result:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        return Result(self._run(stmt))


def test_fts_queries_or_every_language_apply_visibility_and_fall_back_on_typos(monkeypatch):
    from docuhive import db
    from docuhive.search import fts

    session = CapturingSession([["doc-1"], ["doc-2"]])  # 1 FTS hit < 5, so the typo query runs
    monkeypatch.setattr(db, "session", lambda: session)

    assert fts.documents(USER, "Stadwerke", SearchFilters(tags=["paid"]), 50) == ["doc-1", "doc-2"]

    lexical, typo = session.sql
    # every tsquery is one websearch_to_tsquery per configuration, ORed together
    assert lexical.count("websearch_to_tsquery") % len(fts.CONFIGS) == 0
    assert ") || websearch_to_tsquery(" in lexical
    assert "documents.owner_id" in lexical and "documents.deleted_at IS NULL" in lexical
    assert "document_tags" in lexical  # filters reach the FTS list too
    assert "similarity(" in typo and "NOT IN" in typo


def test_fts_skips_the_typo_query_with_enough_hits_and_builds_chunk_queries(monkeypatch):
    from docuhive import db
    from docuhive.search import fts

    session = CapturingSession(
        [
            [f"doc-{i}" for i in range(5)],
            [("doc-1", "Title", "\u0002Strom\u0003")],
            [("doc-1", 0, "Strom")],
            [("doc-1", "Title", None, "utilities")],
        ]
    )
    monkeypatch.setattr(db, "session", lambda: session)

    assert len(fts.documents(USER, "Strom", SearchFilters(), 50)) == 5
    assert fts.headlines(["doc-1"], "Strom") == {"doc-1": ("Title", "\u0002Strom\u0003")}
    assert fts.chunks(USER, "Strom", SearchFilters(), 10) == [("doc-1", 0, "Strom")]
    assert fts.details(["doc-1"]) == {"doc-1": ("Title", None, "utilities")}
    assert len(session.sql) == 4  # no typo query
    assert "doc_chunks" in session.sql[2] and "to_tsvector(documents.fts_config" in session.sql[2]
    assert fts.headlines([], "x") == {} and fts.details([]) == {}
