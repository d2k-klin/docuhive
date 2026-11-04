from datetime import date

from docuhive.contracts import CurrentUser, SearchFilters
from docuhive.index import chunking, semantic
from docuhive.index.jobs import embed_document, rebuild

from tests.fakes.intel import use_routing

OWNER = CurrentUser(id=1, username="dev", role="admin")
OTHER = CurrentUser(id=2, username="member", role="member")


def test_chunker_overlap_header_long_paragraph_empty(core):
    view = core.docs.get(
        core.docs.add(
            "x", title="Stromrechnung", category="utilities", document_date=date(2025, 11, 1)
        )
    )
    text = "\n\n".join(f"Absatz {i} " + "wort " * 150 for i in range(10))
    chunks = chunking.chunk(view, text)
    assert len(chunks) > 1 and all(c.startswith("Title: Stromrechnung\n") for c in chunks)
    assert "Date: 2025-11-01" in chunks[0]
    body = [c.split("---\n", 1)[1] for c in chunks]
    assert body[0][-100:] in body[1]  # overlap carried into the next chunk
    long = chunking.split("y" * 10_000)
    assert len(long) >= 4 and all(len(c) <= chunking.CHUNK_CHARS for c in long)
    assert chunking.chunk(view, "") == [chunking.header(view).rstrip("-\n")]


def test_reembed_replaces_chunks(core):
    doc = core.docs.add("Stromrechnung November " * 10)
    embed_document(doc)
    first = core.rows("doc_chunks", document_id=doc)
    embed_document(doc)
    assert len(core.rows("doc_chunks", document_id=doc)) == len(first)
    assert core.rows("ai_runs", task="embed")[0]["status"] == "ok"


def test_restricted_doc_with_cloud_embedder_gets_no_chunks(core, monkeypatch):
    use_routing(monkeypatch, tasks={"embed": {"route": "cloud/embed", "dims": 1024}})
    doc = core.docs.add("Befund", category="health/medical")
    assert embed_document(doc) == {"skipped": "restricted"}
    assert core.count("doc_chunks", document_id=doc) == 0
    assert core.count("ai_runs") == 0  # nothing was sent anywhere


def test_semantic_permissions_filters_best_chunk(core):
    mine = core.docs.add(
        "Stromrechnung Stadtwerke Strom Verbrauch",
        owner_id=1,
        shared=False,
        category="utilities/electricity",
    )
    private_other = core.docs.add(
        "Stromrechnung Stadtwerke Strom Verbrauch Strom",
        owner_id=2,
        shared=False,
        category="utilities/electricity",
    )
    contract = core.docs.add("Mietvertrag Wohnung Kaution", owner_id=1, category="housing/rent")
    for d in (mine, private_other, contract):
        embed_document(d)
    hits = semantic.semantic_search(OWNER, "Stromrechnung Strom", SearchFilters(), 5)
    ids = [h.document_id for h in hits]
    assert ids[0] == mine and private_other not in ids
    assert len(ids) == len(set(ids))  # best chunk per document
    only_housing = semantic.semantic_search(
        OWNER, "Strom", SearchFilters(categories=["housing"]), 5
    )
    assert [h.document_id for h in only_housing] == [contract]
    assert (
        semantic.semantic_search(OTHER, "Strom", SearchFilters(), 5)[0].document_id == private_other
    )


def test_trashed_documents_not_returned(core):
    doc = core.docs.add("Stromrechnung")
    embed_document(doc)
    core.docs.trash(doc)
    assert semantic.semantic_search(OWNER, "Stromrechnung", SearchFilters(), 5) == []


def test_similar_documents(core):
    a = core.docs.add("Stromrechnung Stadtwerke Musterstadt Verbrauch kWh")
    b = core.docs.add("Stromrechnung Stadtwerke Musterstadt Verbrauch kWh Oktober")
    c = core.docs.add("Kfz Versicherung Police Beitrag")
    for d in (a, b, c):
        embed_document(d)
    hits = semantic.similar(OWNER, a)
    assert hits[0].document_id == b and a not in [h.document_id for h in hits]


def test_rebuild_missing_only(core):
    a, b = core.docs.add("eins"), core.docs.add("zwei")
    embed_document(a)
    assert rebuild(missing_only=True) == 1
    assert [j.payload["document_id"] for j in core.jobs.pending("index.embed")] == [b]


def test_startup_registers_semantic(core):
    from docuhive.ai.startup import startup

    startup()
    startup()  # safe twice
    assert core.semantic is semantic.semantic_search
