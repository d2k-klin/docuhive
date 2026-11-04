"""AI-03 audit: restricted documents never reach a non-local model, through any flow."""

import asyncio

import pytest
from docuhive.agents.ask import ask
from docuhive.agents.pipeline import run_classify, run_extract
from docuhive.contracts import CurrentUser
from docuhive.index.jobs import embed_document

from tests.fakes.intel import Ctx, use_routing

OWNER = CurrentUser(id=1, username="dev", role="admin")
SECRET = {
    "health/medical": "SECRET-DIAGNOSIS Befund Kardiologie",
    "government/identity": "SECRET-PASSPORT Reisepass Nummer C01X00T47",
    "insurance/health": "SECRET-KRANKENKASSE Beitrag Krankenversicherung",
}
TASKS = ("triage", "classify", "extract", "chat", "analyse")
CLASSIFY = {
    "title": "t",
    "category": "other",
    "document_type": "letter",
    "correspondent": None,
    "tags": [],
    "document_date": None,
    "language": "de",
    "confidence": {},
}


def cloud_only(mp):
    use_routing(
        mp,
        tasks={t: {"route": "cloud/m"} for t in TASKS}
        | {"embed": {"route": "cloud/embed", "dims": 1024}},
        budgets={},
    )


def seed(core):
    docs = [
        core.docs.add(text, category=cat, document_type="invoice") for cat, text in SECRET.items()
    ]
    docs.append(
        core.docs.add(
            "SECRET-TAGGED Privatbrief",
            category="personal",
            tags=["private"],
            document_type="letter",
        )
    )
    public = core.docs.add(
        "PUBLIC Stromrechnung Stadtwerke", category="utilities", document_type="invoice"
    )
    return docs, public


def all_flows(core, docs, public):
    for d in [*docs, public]:
        run_classify({"document_id": d}, Ctx(1))
        run_extract({"document_id": d, "document_type": "invoice"}, Ctx(1))
        embed_document(d)

    async def chat():
        script = [{"tool": "read_document", "input": {"document_id": d}} for d in docs]
        script += [{"tool": "search_documents", "input": {"query": "SECRET"}}, {"text": "done"}]
        from tests.fakes.intel import REGISTRY

        for route in ("cloud/m", "local/m"):
            if route in REGISTRY:
                REGISTRY[route].script = list(script)
        return [e async for e in ask(OWNER, [], "Show me everything")]

    return asyncio.run(chat())


@pytest.fixture
def fakes(core, fake, monkeypatch):
    cloud_only(monkeypatch)
    out = {"*": CLASSIFY | {"category": "other"}}
    return fake("cloud/m", outputs=out), out


def test_cloud_only_never_sees_restricted_text(core, fakes):
    cloud, _ = fakes
    docs, public = seed(core)
    core.semantic = None
    from docuhive.index.semantic import semantic_search

    core.semantic = semantic_search
    all_flows(core, docs, public)
    seen = cloud.seen_text()
    assert "SECRET" not in seen, "a restricted document reached a cloud model"
    assert "PUBLIC" in seen  # the unrestricted document was processed in the cloud
    for row in core.rows("ai_runs"):
        assert not row["restricted"] or row["local"]  # also the DB CHECK constraint
    notices = {r["document_id"] for r in core.rows("review_items", kind="notice")}
    assert set(docs) <= notices  # skipped tasks explain themselves
    assert all(core.count("doc_chunks", document_id=d) == 0 for d in docs)


def test_with_local_route_restricted_docs_are_processed_locally(core, fake, monkeypatch):
    use_routing(
        monkeypatch,
        tasks={t: {"route": "cloud/m", "fallback": ["local/m"]} for t in TASKS}
        | {"embed": {"route": "local/embed", "dims": 1024}},
        budgets={},
    )
    cloud = fake("cloud/m", outputs={"*": CLASSIFY})
    local = fake("local/m", outputs={"*": CLASSIFY})
    docs, public = seed(core)
    for d in docs:
        run_classify({"document_id": d}, Ctx(1))
        embed_document(d)
    assert "SECRET" not in cloud.seen_text()
    assert all(
        s in local.seen_text() for s in ("SECRET-DIAGNOSIS", "SECRET-PASSPORT", "SECRET-TAGGED")
    )
    restricted = [r for r in core.rows("ai_runs") if r["restricted"]]
    assert restricted and all(r["local"] for r in restricted)
    assert all(core.count("doc_chunks", document_id=d) > 0 for d in docs)


def test_chat_masks_restricted_for_cloud_and_local_only_reads(core, fake, monkeypatch):
    use_routing(monkeypatch, tasks={"chat": {"route": "cloud/m", "fallback": ["local/m"]}})
    docs, _ = seed(core)
    cloud = fake(
        "cloud/m",
        script=[{"tool": "read_document", "input": {"document_id": docs[0]}}, {"text": "ok"}],
    )
    events = asyncio.run(_collect(ask(OWNER, [], "Befund?")))
    result = next(e for e in events if e["type"] == "tool_result")["result"]
    assert result["title"] == "[restricted]" and "SECRET" not in cloud.seen_text()
    local = fake(
        "local/m",
        script=[{"tool": "read_document", "input": {"document_id": docs[0]}}, {"text": "ok"}],
    )
    events = asyncio.run(_collect(ask(OWNER, [], "Befund?", local_only=True)))
    assert (
        "SECRET-DIAGNOSIS"
        in next(e for e in events if e["type"] == "tool_result")["result"]["content"]
    )
    assert local.calls


async def _collect(gen):
    return [e async for e in gen]


def test_triage_route_warning_flag(core, monkeypatch):
    from docuhive import auth
    from docuhive.mail.routes import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[auth.current_user] = lambda: OWNER
    client = TestClient(app)
    assert client.get("/api/sources/accounts").json()["triage_local"] is True
    use_routing(monkeypatch, tasks={"triage": {"route": "cloud/m"}})
    assert client.get("/api/sources/accounts").json()["triage_local"] is False
