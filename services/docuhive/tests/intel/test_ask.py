import asyncio
import json
from datetime import date

import pytest
from docuhive import auth
from docuhive.agents.ask import ask, citations
from docuhive.agents.tools import WITHHELD, build_tools
from docuhive.agents.tools.facts import query_facts
from docuhive.ai.router import Route
from docuhive.contracts import CurrentUser, SearchFilters
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.fakes.intel import use_routing

OWNER = CurrentUser(id=1, username="dev", role="admin")
OTHER = CurrentUser(id=2, username="member", role="member")
LOCAL, CLOUD = Route("local", "m", True), Route("cloud", "m", False)


def money(v, cur="EUR"):
    return {"type": "money", "value": v, "currency": cur}


@pytest.fixture
def invoices(core):
    ids = [
        core.docs.add(
            "Strom Jan",
            document_type="invoice",
            category="utilities/electricity",
            document_date=date(2025, 1, 15),
            correspondent="Stadtwerke",
            facts={"amount_total": money("84.20")},
        ),
        core.docs.add(
            "Strom Feb",
            document_type="invoice",
            category="utilities/electricity",
            document_date=date(2025, 2, 15),
            correspondent="Stadtwerke",
            facts={"amount_total": money("90.00")},
        ),
        core.docs.add(
            "Gas CHF",
            document_type="invoice",
            category="utilities/gas-heating",
            document_date=date(2025, 2, 20),
            facts={"amount_total": money("50", "CHF")},
        ),
        core.docs.add(
            "Strom 2024",
            document_type="invoice",
            category="utilities/electricity",
            document_date=date(2024, 12, 1),
            facts={"amount_total": money("70.00")},
        ),
        core.docs.add(
            "Other user",
            owner_id=2,
            shared=False,
            document_type="invoice",
            category="utilities/electricity",
            document_date=date(2025, 3, 1),
            facts={"amount_total": money("999.00")},
        ),
        core.docs.add(
            "Arzt",
            document_type="invoice",
            category="health",
            document_date=date(2025, 3, 3),
            facts={"amount_total": money("40.00")},
        ),
    ]
    return ids


def test_sum_by_currency_never_mixed(core, invoices):
    r = query_facts(
        OWNER,
        None,
        "amount_total",
        "sum",
        category="utilities",
        date_from=date(2025, 1, 1),
        date_to=date(2025, 12, 31),
    )
    assert {(a["currency"], a["value"]) for a in r["aggregates"]} == {
        ("EUR", "174.20"),
        ("CHF", "50.00"),
    }
    assert r["row_count"] == 3 and "EUR 174.20" in r["summary"]


def test_group_by_month_and_year(core, invoices):
    r = query_facts(
        OWNER, None, "amount_total", "sum", category="utilities/electricity", group_by="month"
    )
    assert [(a["group"], a["value"]) for a in r["aggregates"]] == [
        ("2024-12", "70.00"),
        ("2025-01", "84.20"),
        ("2025-02", "90.00"),
    ]
    years = query_facts(OWNER, None, "amount_total", "count", group_by="year")
    assert {a["group"]: a["value"] for a in years["aggregates"] if a["currency"] == "EUR"} == {
        "2024": 1,
        "2025": 3,
    }


def test_permissions_and_session_scope_intersection(core, invoices):
    r = query_facts(
        OTHER,
        None,
        "amount_total",
        "sum",
        category="utilities/electricity",
        date_from=date(2025, 1, 1),
    )
    assert {row["document_id"] for row in r["rows"]} == {invoices[0], invoices[1], invoices[4]}
    scoped = query_facts(
        OWNER,
        SearchFilters(categories=["utilities/gas-heating"]),
        "amount_total",
        "sum",
        category="utilities",
    )
    assert [row["document_id"] for row in scoped["rows"]] == [invoices[2]]


def test_tools_mask_restricted_for_cloud_route(core, invoices):
    by_name = {t.tool_name: t for t in build_tools(OWNER, SearchFilters(), CLOUD)}
    doc = invoices[5]
    out = by_name["read_document"](document_id=doc)
    assert out["content"] == WITHHELD and out["title"] == "[restricted]"
    facts = by_name["query_facts"](field="amount_total", agg="sum", date_from="2025-03-01")
    assert facts["excluded_restricted"] == 1 and facts["rows"] == []
    local = {t.tool_name: t for t in build_tools(OWNER, SearchFilters(), LOCAL)}
    assert local["read_document"](document_id=doc)["content"] == "Arzt"


def script_answer(doc_ids, total="174.20"):
    cites = " ".join(f"[doc:{d}]" for d in doc_ids)
    return [
        {
            "tool": "query_facts",
            "input": {
                "field": "amount_total",
                "agg": "sum",
                "category": "utilities/electricity",
                "date_from": "2025-01-01",
            },
        },
        {"text": f"You paid EUR {total} for electricity in 2025 {cites}"},
    ]


def run(gen):
    async def go():
        return [ev async for ev in gen]

    return asyncio.run(go())


def test_ask_citations_and_invisible_ids_dropped(core, fake, invoices):
    fake(script=script_answer([invoices[0], invoices[1], invoices[4]]))
    events = run(ask(OWNER, [], "How much did I spend on electricity in 2025?"))
    kinds = [e["type"] for e in events]
    assert kinds.index("tool_call") < kinds.index("tool_result") < kinds.index("token")
    done = events[-1]
    assert [c["document_id"] for c in done["citations"]] == invoices[:2]  # other user's dropped
    assert done["uncited"] is False
    tr = next(e for e in events if e["type"] == "tool_result")
    assert tr["result"]["aggregates"][0]["value"] == "174.20"


def test_uncited_flag(core, fake):
    fake(script=[{"text": "It was about 120 euros."}])
    done = run(ask(OWNER, [], "How much?"))[-1]
    assert done["uncited"] is True and done["citations"] == []


def test_max_tool_calls_enforced(core, fake, monkeypatch):
    use_routing(monkeypatch, tasks={"chat": {"route": "local/m", "max_tool_calls": 2}})
    fake(script=[{"tool": "list_vocabulary", "input": {}}] * 10 + [{"text": "done"}])
    events = run(ask(OWNER, [], "loop"))
    assert sum(e["type"] == "tool_call" for e in events) <= 3
    assert events[-1]["limited"] is True


def test_local_only_session_uses_local_route(core, fake, monkeypatch, invoices):
    use_routing(monkeypatch, tasks={"chat": {"route": "cloud/m", "fallback": ["local/m"]}})
    cloud = fake("cloud/m", script=[{"text": "cloud"}])
    fake(
        "local/m",
        script=[
            {"tool": "read_document", "input": {"document_id": invoices[5]}},
            {"text": f"Arzt [doc:{invoices[5]}]"},
        ],
    )
    events = run(ask(OWNER, [], "Arzt?", local_only=True))
    assert cloud.calls == []
    assert next(e for e in events if e["type"] == "tool_result")["result"]["content"] == "Arzt"


def test_citations_helper(core, invoices):
    assert citations(f"see [doc:{invoices[4]}]", OWNER) == []


@pytest.fixture
def client(core):
    from docuhive.chat.routes import analyses_router, router

    app = FastAPI()
    app.include_router(router)
    app.include_router(analyses_router)
    app.dependency_overrides[auth.current_user] = lambda: OWNER
    return TestClient(app)


def parse_sse(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        if block.startswith(":"):
            continue
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_sse_event_order_and_stored_messages(core, fake, client, invoices):
    fake(script=script_answer(invoices[:2]))
    sid = client.post("/api/chat/sessions", json={}).json()["id"]
    r = client.post(f"/api/chat/sessions/{sid}/messages", json={"content": "Strom 2025?"})
    assert r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    names = [e for e, _ in events]
    assert names[0] == "tool_call" and names[-1] == "done" and "citation" in names
    msgs = client.get(f"/api/chat/sessions/{sid}/messages").json()["items"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["citations"] == invoices[:2]
    assert msgs[1]["tool_calls"][0]["result"]["aggregates"][0]["value"] == "174.20"


def test_sse_error_event_on_budget(core, fake, client, monkeypatch):
    use_routing(monkeypatch, tasks={"chat": {"route": "cloud/m"}}, budgets={"cloud": 0.0})
    sid = client.post("/api/chat/sessions", json={}).json()["id"]
    events = parse_sse(
        client.post(f"/api/chat/sessions/{sid}/messages", json={"content": "hi"}).text
    )
    assert events == [("error", {"code": "budget_exceeded", "message": events[0][1]["message"]})]


def test_sse_heartbeat_and_disconnect(core, fake, monkeypatch):
    from docuhive.chat import routes

    monkeypatch.setattr(routes, "HEARTBEAT_S", 0.01)

    async def slow_ask(*a, **kw):
        await asyncio.sleep(0.05)
        yield {"type": "token", "text": "partial "}
        await asyncio.sleep(10)

    monkeypatch.setattr(routes, "ask", slow_ask)
    with core.session() as s:
        from docuhive.chat.models import ChatSession

        sess = ChatSession(user_id=1, filters={})
        s.add(sess)
        s.flush()
        sid = sess.id

    async def consume():
        gen = routes.answer_stream(sid, OWNER, "q")
        chunks = [await gen.__anext__() for _ in range(6)]
        await gen.aclose()  # the client went away
        return chunks

    chunks = asyncio.run(consume())
    assert ": ping\n\n" in chunks and any("partial" in c for c in chunks)
    stored = core.rows("chat_messages", session_id=sid)
    assert stored[-1]["flags"] == {"truncated": True} and stored[-1]["content"] == "partial "


def test_chat_sessions_owner_only(core, client):
    sid = client.post("/api/chat/sessions", json={"title": "mine"}).json()["id"]
    client.app.dependency_overrides[auth.current_user] = lambda: OTHER
    assert client.get(f"/api/chat/sessions/{sid}").status_code == 404


def test_saved_analysis_runs_as_job(core, fake, client, invoices):
    import docuhive.chat.jobs  # noqa: F401  registers analyses.run

    fake(script=script_answer(invoices[:2]))
    tpl = client.get("/api/analyses/templates").json()["items"]
    assert any(t["id"] == "contracts-ending" for t in tpl)
    aid = client.post("/api/analyses", json={"name": "Strom", "prompt": "Strom 2025?"}).json()["id"]
    assert client.post(f"/api/analyses/{aid}/run").json()["status"] == "queued"
    core.jobs.run({"analyses.run"})
    res = client.get(f"/api/analyses/{aid}").json()["last_result"]
    assert res["facts_rows"] and [c["document_id"] for c in res["citations"]] == invoices[:2]
