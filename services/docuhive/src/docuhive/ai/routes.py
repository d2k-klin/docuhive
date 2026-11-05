"""/api/ai: providers, routing, usage, runs ("How was this made?"), setup status."""

import time
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Query
from sqlalchemy import func, select

from docuhive import config, db, documents
from docuhive.ai import budgets, routing
from docuhive.ai.http import User, fail
from docuhive.ai.models import AIRun
from docuhive.ai.progress import document_status
from docuhive.ai.router import parse_route
from docuhive.ai.settings import get_ai_settings
from docuhive.contracts import CurrentUser, SetupCheck

router = APIRouter(prefix="/api/ai", tags=["ai"])
_reach: dict[str, tuple[float, bool, str]] = {}

router.add_api_route("/documents/status", document_status, methods=["POST"])
LEARN = {
    "classify": "docs/learn/02-structured-output.md",
    "extract": "docs/learn/02-structured-output.md",
    "triage": "docs/learn/11-email-triage-agent.md",
    "embed": "docs/learn/08-embeddings-and-chunking.md",
    "chat": "docs/learn/06-tools-and-agent-loop.md",
    "analyse": "docs/learn/06-tools-and-agent-loop.md",
}


def reachable(name: str) -> tuple[bool, str]:
    """Cheap reachability, cached 60 s. Ollama: /api/tags. Cloud: credentials configured."""
    hit = _reach.get(name)
    if hit and time.monotonic() - hit[0] < 60:
        return hit[1], hit[2]
    p, s = routing.load().providers[name], get_ai_settings()
    ok, note = True, "configured"
    if p.kind == "ollama":
        try:
            r = httpx.get(f"{(p.host or s.ollama_host).rstrip('/')}/api/tags", timeout=3)
            ok, note = r.status_code == 200, f"HTTP {r.status_code}"
        except httpx.HTTPError as e:
            ok, note = False, f"cannot reach Ollama: {type(e).__name__}"
    elif p.kind == "anthropic":
        ok, note = (
            bool(s.anthropic_api_key),
            "DOCUHIVE_AI_ANTHROPIC_API_KEY " + ("set" if s.anthropic_api_key else "missing"),
        )
    elif p.kind == "openai" and not p.base_url and not s.openai_base_url:
        ok, note = (
            bool(s.openai_api_key),
            "DOCUHIVE_AI_OPENAI_API_KEY " + ("set" if s.openai_api_key else "missing"),
        )
    _reach[name] = (time.monotonic(), ok, note)
    return ok, note


@router.get("/providers")
def providers(user: User) -> list[dict]:
    cfg = routing.load()
    used = {
        parse_route(r, cfg).provider for t in cfg.tasks.values() for r in [t.route, *t.fallback]
    }
    out = []
    for name, p in cfg.providers.items():
        ok, note = reachable(name) if p.enabled and name in used else (False, "not used")
        out.append(
            {
                "name": name,
                "kind": p.kind,
                "enabled": p.enabled,
                "local": p.local,
                "experimental": p.experimental,
                "reachable": ok,
                "note": note,
            }
        )
    return out


@router.get("/routing")
def effective_routing(user: User) -> dict:
    cfg = routing.load()
    tasks = {}
    for task, t in cfg.tasks.items():
        routes = [parse_route(r, cfg) for r in [t.route, *t.fallback]]
        tasks[task] = {
            "routes": [{"route": str(r), "local": r.local} for r in routes],
            "apply": t.apply.model_dump() if task in ("classify", "extract") else None,
        }
    return {
        "tasks": tasks,
        "privacy": cfg.privacy.model_dump(),
        "budgets": cfg.budgets,
        "ai_enabled": get_ai_settings().enabled,
    }


@router.get("/usage")
def usage(user: User, month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$")) -> dict:
    when = datetime.strptime(month, "%Y-%m").replace(tzinfo=UTC) if month else datetime.now(UTC)
    start, end = budgets.month_start(when), budgets.next_month_start(when)
    in_month = (AIRun.at >= start, AIRun.at < end)
    with db.session() as s:
        rows = s.execute(
            select(
                AIRun.provider,
                func.count(),
                func.coalesce(func.sum(AIRun.tokens_in), 0),
                func.coalesce(func.sum(AIRun.tokens_out), 0),
                func.coalesce(func.sum(AIRun.cost_usd), 0),
            )
            .where(*in_month, AIRun.status != "skipped")
            .group_by(AIRun.provider)
        ).all()
        local_runs, total = s.execute(
            select(
                func.count().filter(AIRun.local.is_(True)),
                func.count(),
            ).where(*in_month, AIRun.status != "skipped")
        ).one()
        restricted = s.scalar(
            select(func.count()).where(
                *in_month, AIRun.restricted.is_(True), AIRun.status != "skipped"
            )
        )
        skipped = s.scalar(
            select(func.count(func.distinct(AIRun.document_id))).where(
                *in_month, AIRun.status == "skipped"
            )
        )
    caps = routing.load().budgets
    providers = []
    for name, runs, tin, tout, cost in rows:
        cap = caps.get(name)
        providers.append(
            {
                "provider": name,
                "runs": runs,
                "tokens_in": tin,
                "tokens_out": tout,
                "cost_usd": float(cost or 0),
                "budget_usd": cap,
                "pct_used": round(100 * float(cost or 0) / cap, 1) if cap else None,
            }
        )
    return {
        "month": start.strftime("%Y-%m"),
        "providers": providers,
        "privacy": {
            "local_runs": local_runs,
            "cloud_runs": total - local_runs,
            "restricted_runs": restricted or 0,
            "skipped_documents": skipped or 0,
        },
    }


def _check_doc(doc_id: str | None, user: CurrentUser) -> None:
    if doc_id is None:
        if user.role != "admin":
            fail(403, "forbidden", "Only admins can list all AI runs")
        return
    try:
        documents.get_for_user(doc_id, user)
    except documents.NotFound:
        fail(404, "not_found", "Document not found")


def _row(r: AIRun, full: bool = False) -> dict:
    out = {
        "id": r.id,
        "at": r.at,
        "task": r.task,
        "document_id": r.document_id,
        "provider": r.provider,
        "model": r.model,
        "local": r.local,
        "restricted": r.restricted,
        "prompt_version": r.prompt_version,
        "status": r.status,
        "tokens_in": r.tokens_in,
        "tokens_out": r.tokens_out,
        "cost_usd": float(r.cost_usd) if r.cost_usd is not None else None,
        "latency_ms": r.latency_ms,
        "error": r.error,
    }
    if full:
        out["output"] = r.output
    return out


@router.get("/runs")
def list_runs(
    user: User,
    task: str | None = None,
    status: str | None = None,
    document_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: int | None = None,
) -> dict:
    _check_doc(document_id, user)
    q = select(AIRun).order_by(AIRun.id.desc()).limit(limit + 1)
    for col, val in ((AIRun.task, task), (AIRun.status, status), (AIRun.document_id, document_id)):
        if val is not None:
            q = q.where(col == val)
    if cursor:
        q = q.where(AIRun.id < cursor)
    with db.session() as s:
        rows = [_row(r) for r in s.scalars(q)]
    more = len(rows) > limit
    return {"items": rows[:limit], "next_cursor": str(rows[limit - 1]["id"]) if more else None}


@router.get("/runs/{run_id}")
def get_run(run_id: int, user: User) -> dict:
    """The 'Under the hood' view: the run, its sibling attempts and the prompt that was used."""
    with db.session() as s:
        r = s.get(AIRun, run_id)
        if r is None:
            fail(404, "not_found", "Run not found")
        out = _row(r, full=True)
        siblings = (
            [
                _row(x)
                for x in s.scalars(
                    select(AIRun)
                    .where(
                        AIRun.task == r.task,
                        AIRun.document_id == r.document_id,
                        AIRun.id.between(run_id - 10, run_id),
                    )
                    .order_by(AIRun.id)
                )
            ]
            if r.document_id
            else []
        )
    _check_doc(out["document_id"], user)
    name = out["prompt_version"].split("@")[0]
    try:
        prompt_text = config.prompt(name)[0]
    except OSError:
        prompt_text = None
    out |= {
        "attempts": siblings,
        "prompt_text": prompt_text,
        "learn": LEARN.get(out["task"]),
        "privacy": (
            "restricted input: local models only"
            if out["restricted"]
            else "not restricted: any configured route"
        ),
    }
    return out


def setup_checks() -> list[SetupCheck]:
    cfg, s = routing.load(), get_ai_settings()
    checks: list[SetupCheck] = []
    categories_chosen = config.get_setting("taxonomy.categories") is not None
    checks.append(
        SetupCheck(
            id="ai.categories",
            area="ai",
            title="Document categories",
            status="ok" if categories_chosen else "optional",
            message="Your shared category list is saved."
            if categories_chosen
            else "Using the predefined categories. Choose the ones you need or add your own.",
            action_label="Choose categories",
            action_href="/vocabulary#categories",
            help_doc="docs/user-guide.md",
        )
    )
    if not s.enabled:
        return [
            *checks,
            SetupCheck(
                id="ai.enabled",
                area="ai",
                title="AI",
                status="optional",
                message="AI is switched off (DOCUHIVE_AI_ENABLED=false).",
                help_doc="docs/setup/ai-providers.md",
            ),
        ]
    used = {
        parse_route(r, cfg).provider for t in cfg.tasks.values() for r in [t.route, *t.fallback]
    }
    reach = {n: reachable(n) for n in used if cfg.providers[n].enabled}
    ok = [n for n, (good, _) in reach.items() if good]
    checks.append(
        SetupCheck(
            id="ai.provider",
            area="ai",
            title="AI provider",
            required=True,
            status="ok" if ok else "todo",
            message=f"Reachable: {', '.join(sorted(ok))}."
            if ok
            else "No AI provider is reachable yet. Start Ollama or add an API key.",
            action_label=None if ok else "Set up AI",
            action_href="/settings/ai",
            help_doc="docs/setup/ai-providers.md",
        )
    )
    local = [
        t
        for t in ("classify", "extract", "embed")
        if any(parse_route(r, cfg).local for r in [cfg.tasks[t].route, *cfg.tasks[t].fallback])
        if t in cfg.tasks
    ]
    checks.append(
        SetupCheck(
            id="ai.privacy",
            area="ai",
            title="Local model for private documents",
            status="ok" if len(local) == 3 else "warn",
            message="Restricted documents can be processed locally."
            if len(local) == 3
            else "Some tasks have no local route; restricted documents will be skipped for them.",
            action_href="/settings/ai",
            help_doc="docs/learn/05-privacy-routing.md",
        )
    )
    auto = cfg.tasks.get("classify") and cfg.tasks["classify"].apply.auto
    checks.append(
        SetupCheck(
            id="ai.auto_apply",
            area="ai",
            title="Automatic filing",
            status="ok" if auto else "optional",
            message="Confident suggestions are applied automatically."
            if auto
            else "Suggestions wait in the review queue until the eval gate passes.",
            action_label="Open review",
            action_href="/review",
            help_doc="docs/evals/README.md",
        )
    )
    return checks


@router.get("/setup-status")
def setup_status(user: User) -> list[SetupCheck]:
    return setup_checks()
