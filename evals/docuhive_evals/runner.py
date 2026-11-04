"""Run the real agents in-process against an eval set, one route at a time.

The harness writes ai_runs into a throwaway in-memory SQLite DB, so evals need no Postgres and
no OA services. The privacy gate applies: restricted cases only run on local routes.
"""

import os
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from docuhive import db, taxonomy
from docuhive.agents.base import (
    AIDisabled,
    AllRoutesFailed,
    InvalidOutput,
    NoAllowedRoute,
    run_structured,
)
from docuhive.agents.classify import ClassifyOut, make_validator, variables
from docuhive.agents.extract import run_extract
from docuhive.ai import routing
from docuhive.ai.models import AIRun
from docuhive.contracts import DocStatus, DocumentView, SourceInfo, SourceKind
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from docuhive_evals import scorers
from docuhive_evals.datasets import Case


@contextmanager
def eval_env(task: str, route: str, fakes: dict | None = None) -> Iterator[None]:
    """Route `task` to `route` only, with ai_runs in an in-memory DB."""
    import docuhive.notify.models  # noqa: F401  (budget warnings log here)
    from docuhive.ai import router
    from docuhive.db import IntelBase

    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    IntelBase.metadata.create_all(engine)
    lock = threading.Lock()

    @contextmanager
    def session() -> Iterator[Session]:
        with lock, Session(engine) as s, s.begin():
            yield s

    base = routing.load()
    provider = route.split("/", 1)[0]
    providers = dict(base.providers)
    if provider == "fake":
        os.environ["DOCUHIVE_ENV"] = "test"
        providers["fake"] = routing.Provider(kind="fake", local=True)
    tasks = dict(base.tasks)
    tasks[task] = tasks[task].model_copy(update={"route": route, "fallback": []})
    cfg = base.model_copy(update={"providers": providers, "tasks": tasks})
    old_session, old_load = db.session, routing.load
    db.session, routing.load = session, lambda: cfg  # type: ignore[assignment]
    router.clear_cache()
    if fakes:
        from docuhive.ai.fake import REGISTRY

        REGISTRY.update(fakes)
    try:
        yield
    finally:
        db.session, routing.load = old_session, old_load  # type: ignore[assignment]
        router.clear_cache()


def _view(case: Case) -> DocumentView:
    return DocumentView(
        id=case.id,
        owner_id=1,
        shared=True,
        status=DocStatus.stored,
        mime="text/plain",
        pages=1,
        added_at=datetime.now(UTC),
        title=None,
        document_date=None,
        language=None,
        category=None,
        document_type=None,
        correspondent=None,
        tags=[],
        facts={},
        manual_fields=[],
        source=SourceInfo(kind=SourceKind.upload, original_filename=f"{case.id}.pdf"),
        deleted_at=None,
    )


def _runs_after(last_id: int) -> list[AIRun]:
    with db.session() as s:
        rows = list(s.scalars(select(AIRun).where(AIRun.id > last_id).order_by(AIRun.id)))
        s.expunge_all()
    return rows


def _attempt(fn: Any) -> tuple[Any, str]:
    try:
        return fn(), "ok"
    except NoAllowedRoute:
        return None, "skipped"
    except InvalidOutput:
        return None, "invalid"
    except (AllRoutesFailed, AIDisabled) as e:
        return None, f"error: {e}"


def run_cases(cases: list[Case], one: Any, concurrency: int) -> list[dict]:
    if concurrency <= 1:
        return [one(c) for c in cases]
    with ThreadPoolExecutor(concurrency) as pool:
        return list(pool.map(one, cases))


def classify_set(
    cases: list[Case], route: str, *, concurrency: int = 1, fakes: dict | None = None
) -> dict:
    with eval_env("classify", route, fakes):
        tax = taxonomy.load()
        known = sorted({c.expect.correspondent for c in cases if c.expect.correspondent})

        def one(case: Case) -> dict:
            t0 = time.monotonic()
            with db.session() as s:
                last = s.scalar(select(AIRun.id).order_by(AIRun.id.desc()).limit(1)) or 0
            res, status = _attempt(
                lambda: run_structured(
                    "classify",
                    "classify",
                    variables(_view(case), case.text, tax, known),
                    ClassifyOut,
                    restricted=case.restricted,
                    validate=make_validator(tax, known),
                )
            )
            return {
                "case": case,
                "res": res,
                "status": status,
                "latency": time.monotonic() - t0,
                "runs": _runs_after(last),
            }

        results = run_cases(cases, one, concurrency)
        policy = routing.load().tasks["classify"].apply
        return score_classify(route, results, policy)


def score_classify(route: str, results: list[dict], policy: routing.ApplyPolicy) -> dict:
    done = [r for r in results if r["res"] is not None]
    pairs: dict[str, list] = {f: [] for f in scorers.FIELDS}
    tags, calib, parents, fuzzy = [], [], [], []
    for r in done:
        exp, out = r["case"].expect, r["res"].value
        got = {
            "category": out.category,
            "document_type": out.document_type,
            "correspondent": out.correspondent,
            "document_date": out.document_date,
            "language": out.language,
        }
        for f in ("category", "document_type", "document_date", "language"):
            pairs[f].append((getattr(exp, f), got[f]))
        ok_corr = scorers.correspondent_match(exp.correspondent, out.correspondent, False)
        pairs["correspondent"].append((True, ok_corr))
        fuzzy.append(
            (True, scorers.correspondent_match(exp.correspondent, out.correspondent, True))
        )
        parents.append((scorers.parent(exp.category), scorers.parent(out.category)))
        tags.append((exp.tags, out.tags))
        for f in scorers.FIELDS:
            correct = ok_corr if f == "correspondent" else getattr(exp, f) == got[f]
            calib.append((correct, out.confidence.get(f, 0.0), policy.threshold_for(f)))
    return _summary(
        route,
        results,
        {
            **{f"{f}_accuracy": scorers.accuracy(p) for f, p in pairs.items()},
            "category_parent_accuracy": scorers.accuracy(parents),
            "correspondent_fuzzy_accuracy": scorers.accuracy(fuzzy),
            "tags": scorers.tag_prf(tags),
            **scorers.calibration(calib),
            "threshold": policy.threshold,
        },
    )


def extract_set(
    cases: list[Case], route: str, *, concurrency: int = 1, fakes: dict | None = None
) -> dict:
    with eval_env("extract", route, fakes):
        tax = taxonomy.load()

        def one(case: Case) -> dict:
            dt = taxonomy.document_type(tax, case.expect.document_type)
            t0 = time.monotonic()
            with db.session() as s:
                last = s.scalar(select(AIRun.id).order_by(AIRun.id.desc()).limit(1)) or 0
            if dt is None or not dt.facts:
                return {"case": case, "res": None, "status": "no facts", "latency": 0, "runs": []}
            res, status = _attempt(
                lambda: run_extract(dt, case.text, tax, restricted=case.restricted)
            )
            return {
                "case": case,
                "res": res,
                "status": status,
                "latency": time.monotonic() - t0,
                "runs": _runs_after(last),
            }

        results = [r for r in run_cases(cases, one, concurrency) if r["status"] != "no facts"]
        policy = routing.load().tasks["extract"].apply
        exact, coverage, calib = [], [], []
        for r in results:
            if r["res"] is None:
                continue
            got = {s.field[6:]: s for s in r["res"].facts}
            for name, expected in r["case"].expect.facts.items():
                s = got.get(name)
                ok = scorers.fact_equal(expected, s.payload if s else None)
                exact.append((True, ok))
                coverage.append((True, s is not None))
                if s is not None:
                    calib.append((ok, s.confidence or 0.0, policy.threshold_for(f"facts.{name}")))
        return _summary(
            route,
            results,
            {
                "facts_exact": scorers.accuracy(exact),
                "facts_coverage": scorers.accuracy(coverage),
                **scorers.calibration(calib),
                "threshold": policy.threshold,
            },
        )


def _summary(route: str, results: list[dict], metrics: dict) -> dict:
    n = len(results)
    first_ok = sum(bool(r["runs"]) and r["runs"][0].status == "ok" for r in results)
    retried = sum(len(r["runs"]) > 1 and r["status"] == "ok" for r in results)
    skipped = sum(r["status"] == "skipped" for r in results)
    unknown = sum(
        any(
            x.status == "invalid" and x.error and "not one of the listed" in x.error
            for x in r["runs"]
        )
        for r in results
    )
    lat = [r["latency"] * 1000 for r in results if r["status"] == "ok"]
    runs = [x for r in results for x in r["runs"]]
    cost = sum(float(x.cost_usd or 0) for x in runs)
    ran = max(1, n - skipped)
    return {
        "route": route,
        "n": n,
        "ok": sum(r["status"] == "ok" for r in results),
        "skipped_privacy": skipped,
        "schema_valid_first_try": round(first_ok / ran, 3),
        "retry_rate": round(retried / ran, 3),
        "unknown_label_rate": round(unknown / ran, 3),
        "latency_ms": scorers.latency(lat),
        "tokens_in": sum(x.tokens_in or 0 for x in runs),
        "tokens_out": sum(x.tokens_out or 0 for x in runs),
        "usd_per_100_docs": round(100 * cost / ran, 4),
        "prompt_version": runs[0].prompt_version if runs else None,
        **metrics,
    }
