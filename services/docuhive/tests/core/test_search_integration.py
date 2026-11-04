"""Real PostgreSQL search: stemming, accents, typos, permissions, hybrid fusion and chunk
retrieval for knowledge bases (SRCH-01, SRCH-03, KB-02)."""

import pytest
from docuhive import db, search
from docuhive.contracts import CurrentUser, SearchFilters
from sqlalchemy import text

pytestmark = pytest.mark.integration
OWNER = CurrentUser(id=1, username="owner", role="admin")
OTHER = CurrentUser(id=2, username="other", role="member")
ALL = SearchFilters()


@pytest.fixture
def pg(postgres, monkeypatch):
    from docuhive.ai import routing
    from docuhive.db import IntelBase

    from tests.fakes.intel import _import_intel_models, use_routing

    _import_intel_models()
    names = ", ".join(f'"{t}"' for t in IntelBase.metadata.tables)
    with db.session() as s:
        s.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        s.execute(
            text(
                "INSERT INTO users (id, username, pw_hash, role) VALUES "
                "(1, 'owner', '!', 'admin'), (2, 'other', '!', 'member')"
            )
        )
    use_routing(monkeypatch)  # the hashed test embedder, no network
    routing.load()
    monkeypatch.setattr(search, "_semantic", None)
    monkeypatch.setattr(search, "_chunk_semantic", None)
    return postgres


def add_doc(doc_id, title, content, *, owner=1, shared=False, config="dh_german", chunks=()):
    from docuhive.ai.embeddings import hashed
    from docuhive.index.models import DocChunk

    with db.session() as s:
        s.execute(
            text(
                "INSERT INTO documents (id, owner_id, shared, status, sha256, mime, title, "
                "category, document_type, document_date, content, fts_config) VALUES "
                "(:id, :o, :sh, 'stored', :id, 'application/pdf', :t, 'utilities/electricity', "
                "'invoice', '2025-11-01', :c, CAST(:cfg AS regconfig))"
            ),
            {"id": doc_id, "o": owner, "sh": shared, "t": title, "c": content, "cfg": config},
        )
        s.add_all(
            DocChunk(
                document_id=doc_id,
                chunk_no=i,
                text=t,
                embedding=hashed(t, 1024),
                embed_model="fake",
            )
            for i, t in enumerate(chunks)
        )


def ids(hits):
    return [h.document_id for h in hits]


def test_fts_handles_stemming_accents_typos_and_permissions(pg):
    add_doc("strom", "Stadtwerke Musterstadt", "Die Rechnungen für Strom im November.")
    add_doc("mueller", "Schreiben von Herrn Müller", "Kündigung der Wohnung.")
    add_doc("secret", "Stadtwerke privat", "Rechnung des anderen Nutzers.", owner=2)
    add_doc("shared", "Gemeinsame Rechnung", "Rechnung für alle.", owner=2, shared=True)

    # "Rechnungen" is found by "Rechnung" (stemmed); the title match ranks first.
    assert ids(search.hybrid(OWNER, "Rechnung", ALL)) == ["shared", "strom"]
    assert ids(search.hybrid(OWNER, "Muller", ALL)) == ["mueller"]  # unaccented
    assert "strom" in ids(search.hybrid(OWNER, "Stadwerke", ALL))  # trigram typo fallback
    assert "secret" not in ids(search.hybrid(OWNER, "Stadtwerke privat", ALL))
    assert "secret" in ids(search.hybrid(OTHER, "Rechnung", ALL))

    hit = search.hybrid(OWNER, "Strom", ALL)[0]
    assert hit.title == "Stadtwerke Musterstadt" and hit.fts_rank == 1
    assert "\u0002Strom\u0003" in (hit.snippet or "")
    filtered = SearchFilters(categories=["insurance"])
    assert search.hybrid(OWNER, "Rechnung", filtered) == []


def test_hybrid_fuses_fts_and_semantic_lists(pg, monkeypatch):
    from docuhive.index.semantic import semantic_search

    add_doc(
        "both", "Stromrechnung", "Stromrechnung Stadtwerke", chunks=["Stromrechnung Stadtwerke"]
    )
    add_doc("words", "Brief", "Stromrechnung erwähnt", chunks=["ganz anderer Inhalt"])
    add_doc("meaning", "Notiz", "nichts davon", chunks=["Stromrechnung Stadtwerke Abschlag"])
    monkeypatch.setattr(search, "_semantic", semantic_search)

    hits = search.hybrid(OWNER, "Stromrechnung Stadtwerke", ALL)

    assert hits[0].document_id == "both"
    assert hits[0].fts_rank and hits[0].semantic_rank
    assert {"words", "meaning"} <= set(ids(hits))
    only = search.hybrid(OWNER, "Stromrechnung Stadtwerke", ALL, mode="fts")
    assert all(h.semantic_rank is None for h in only)


def test_retrieve_returns_chunks_with_metadata_and_respects_visibility(pg, monkeypatch):
    from docuhive.index.semantic import semantic_chunks

    long_doc = [f"Abschnitt {i}: Stromrechnung Abschlag" for i in range(6)]
    add_doc("long", "Jahresabrechnung", " ".join(long_doc), chunks=long_doc)
    add_doc("short", "Mahnung", "Stromrechnung offen", chunks=["Stromrechnung offen"])
    add_doc("hidden", "Fremd", "Stromrechnung", owner=2, chunks=["Stromrechnung Abschlag"])
    monkeypatch.setattr(search, "_chunk_semantic", semantic_chunks)

    hits = search.retrieve(OWNER, "Stromrechnung Abschlag", ALL, k=10)

    assert "hidden" not in ids(hits)
    assert ids(hits).count("long") == search.MAX_CHUNKS_PER_DOC
    assert "short" in ids(hits)
    first = hits[0]
    assert first.title and first.category == "utilities/electricity"
    assert first.document_date.isoformat() == "2025-11-01"
    assert first.text.startswith(("Abschnitt", "Stromrechnung"))
    assert all(h.semantic_rank is None for h in search.retrieve(OWNER, "Abschlag", ALL, mode="fts"))
