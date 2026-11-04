"""Search and Ask evals: ingest the set into the SQLite fakes, then query it.

ponytail: uses the CL test fakes (services/docuhive/tests/fakes/intel.py) as the throwaway
store, so `--mode semantic` works anywhere. hybrid/fts need OA's DB-backed search (OA-M4).
"""

import asyncio
import re
import sys
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest
from docuhive import taxonomy
from docuhive.contracts import CurrentUser, FactValue, SearchFilters

from docuhive_evals.datasets import Case

USER = CurrentUser(id=1, username="eval", role="admin")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "docuhive"))


def _store(mp: pytest.MonkeyPatch, cases: list[Case], routes: dict[str, str]):  # type: ignore[no-untyped-def]
    import os

    from docuhive.ai import router, routing
    from docuhive.index.jobs import embed_document
    from docuhive.index.semantic import semantic_search
    from tests.fakes.intel import FakeCore

    core = FakeCore(Path(tempfile.mkdtemp())).install(mp)
    base = routing.load()
    providers, tasks = dict(base.providers), dict(base.tasks)
    if any(r.startswith("fake/") for r in routes.values()):
        os.environ["DOCUHIVE_ENV"] = "test"
        providers["fake"] = routing.Provider(kind="fake", local=True)
    for task, route in routes.items():
        tasks[task] = tasks[task].model_copy(update={"route": route, "fallback": []})
    cfg = base.model_copy(update={"providers": providers, "tasks": tasks})
    mp.setattr(routing, "load", lambda: cfg)
    router.clear_cache()
    tax = taxonomy.load()
    for c in cases:
        e = c.expect
        dt = taxonomy.document_type(tax, e.document_type)
        types = {f.name: f.type for f in (dt.facts if dt else [])}
        facts = {}
        for name, v in e.facts.items():
            if isinstance(v, dict):
                facts[name] = FactValue(
                    type="money", value=str(v["value"]), currency=v.get("currency")
                )
            elif name in types:
                facts[name] = FactValue(type=types[name], value=str(v))
        core.docs.add(
            c.text,
            doc_id=c.id,
            title=c.text.splitlines()[1][:80] if "\n" in c.text else c.id,
            category=e.category,
            document_type=e.document_type,
            correspondent=e.correspondent,
            document_date=e.document_date,
            tags=e.tags,
            facts=facts,
        )
        embed_document(c.id)
    core.semantic = semantic_search
    return core


def search_set(cases: list[Case], queries: list[dict], embed_route: str, mode: str) -> dict:
    if mode != "semantic":
        return {
            "route": embed_route,
            "mode": mode,
            "error": "hybrid/fts need OA's search over a database (OA-M4)",
        }
    from docuhive.index.semantic import semantic_search

    with pytest.MonkeyPatch.context() as mp:
        _store(mp, cases, {"embed": embed_route})
        recalls, rrs = [], []
        for q in queries:
            k = q.get("k", 10)
            ids = [h.document_id for h in semantic_search(USER, q["query"], SearchFilters(), k)]
            want = set(q["expect"])
            recalls.append(len(want & set(ids)) / len(want))
            rank = next((i + 1 for i, d in enumerate(ids) if d in want), None)
            rrs.append(1 / rank if rank else 0.0)
    return {
        "route": embed_route,
        "mode": mode,
        "queries": len(queries),
        "recall_at_k": round(sum(recalls) / len(recalls), 3),
        "mrr": round(sum(rrs) / len(rrs), 3),
    }


def numbers(text: str) -> list[Decimal]:
    out = []
    for raw in re.findall(r"\d[\d.,']*\d|\d", text):
        s = raw.replace("'", "")
        if "," in s and "." in s:
            s = (
                s.replace(".", "").replace(",", ".")
                if s.rfind(",") > s.rfind(".")
                else s.replace(",", "")
            )
        elif "," in s:
            s = s.replace(",", ".") if len(s.rsplit(",", 1)[1]) == 2 else s.replace(",", "")
        try:
            out.append(Decimal(s))
        except InvalidOperation:
            continue
    return out


def ask_set(cases: list[Case], qa: list[dict], chat_route: str, embed_route: str) -> dict:
    from docuhive.agents.ask import ask

    async def run(question: str) -> list[dict]:
        return [e async for e in ask(USER, [], question)]

    with pytest.MonkeyPatch.context() as mp:
        _store(mp, cases, {"chat": chat_route, "embed": embed_route})
        recall, correct, numeric, uncited = [], [], 0, 0
        for item in qa:
            done = asyncio.run(run(item["question"]))[-1]
            cited = {c["document_id"] for c in done.get("citations", [])}
            want = set(item.get("expect_citations", []))
            if want:
                recall.append(len(want & cited) / len(want))
            if exp := item.get("expect_number"):
                numeric += 1
                tol = Decimal(str(exp.get("tolerance", 0)))
                correct.append(
                    any(
                        abs(n - Decimal(str(exp["value"]))) <= tol
                        for n in numbers(done.get("text", ""))
                    )
                )
            uncited += bool(done.get("uncited"))
    return {
        "route": chat_route,
        "questions": len(qa),
        "citation_recall": round(sum(recall) / len(recall), 3) if recall else None,
        "number_correct": round(sum(correct) / numeric, 3) if numeric else None,
        "uncited_rate": round(uncited / len(qa), 3) if qa else None,
    }
