"""The agent harness: the only way DocuHive calls a model.

    privacy gate -> routes (primary, fallbacks) -> budget -> Strands call with timeout
    -> domain validation (one retry with the error text) -> ai_runs row for every attempt

Feature code never builds a `strands.Agent` itself.
"""

import asyncio
import logging
import threading
import time
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from docuhive import config, taxonomy
from docuhive.ai import budgets, privacy, router, routing, runs
from docuhive.ai.budgets import BudgetExceeded
from docuhive.ai.privacy import NoAllowedRoute
from docuhive.ai.router import Route
from docuhive.ai.settings import get_ai_settings
from docuhive.contracts import DocumentView

log = logging.getLogger(__name__)

__all__ = [
    "AIDisabled",
    "AllRoutesFailed",
    "BudgetExceeded",
    "InvalidOutput",
    "NoAllowedRoute",
    "StructuredResult",
    "render",
    "run_agent",
    "run_structured",
]

SYSTEM = (
    "You are one step in DocuHive, a personal document archive. Use only the information you "
    "are given. Answer by calling the output tool with values that match its schema."
)
BACKOFF_S = 0.5  # provider error backoff base; tests set it to 0
_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="harness")


class AIDisabled(Exception):
    """DOCUHIVE_AI_ENABLED=false."""


class InvalidOutput(Exception):
    """The model's answer failed validation twice on the same route."""


class AllRoutesFailed(Exception):
    """Every allowed route errored or timed out."""


@dataclass
class StructuredResult[T: BaseModel]:
    value: T
    ai_run_id: int
    route: Route
    prompt_version: str
    restricted: bool


def render(prompt_name: str, variables: dict) -> tuple[str, str]:
    """(text, "name@version"). Templates use str.format_map: {var}, and {{ }} for literal braces."""
    template, version = config.prompt(prompt_name)
    return template.format_map(variables), version


def _usage(result: Any) -> tuple[int | None, int | None]:
    u = getattr(getattr(result, "metrics", None), "accumulated_usage", None) or {}
    return u.get("inputTokens"), u.get("outputTokens")


def _invoke[T: BaseModel](route: Route, prompt: str, output: type[T], timeout_s: float) -> Any:
    from strands import Agent

    agent = Agent(model=router.model_for(route), system_prompt=SYSTEM, callback_handler=None)
    cancel = threading.Event()
    future = _POOL.submit(agent, prompt, structured_output_model=output, cancel_signal=cancel)
    try:
        return future.result(timeout=timeout_s)
    except FutureTimeout:
        cancel.set()
        raise TimeoutError(f"no answer within {timeout_s:.0f}s") from None


def _allowed_routes(task: str, restricted: bool, version: str, doc_id: str | None) -> list[Route]:
    if not get_ai_settings().enabled:
        raise AIDisabled("AI disabled")
    routes = router.resolve(task, restricted=restricted)
    if not routes:
        reason = (
            "restricted document, no local model configured" if restricted else "no enabled route"
        )
        runs.log(
            task,
            None,
            restricted=restricted,
            prompt_version=version,
            status="skipped",
            document_id=doc_id,
            error=reason,
        )
        if restricted and routing.load().privacy.on_restricted_without_local == "error":
            raise NoAllowedRoute(task, f"{reason} (on_restricted_without_local=error)")
        raise NoAllowedRoute(task, reason)
    return routes


def run_structured[T: BaseModel](
    task: str,
    prompt_name: str,
    variables: dict,
    output: type[T],
    *,
    document: DocumentView | None = None,
    validate: Callable[[T], T] | None = None,
    restricted: bool | None = None,
) -> StructuredResult[T]:
    """Run one structured-output task. `validate` applies domain rules and raises ValueError;
    the harness then retries once on the same route with the error appended to the prompt.
    `restricted` overrides the privacy decision for inputs that are not documents (email
    snippets, eval cases); the default asks the privacy gate about `document`."""
    text, version = render(prompt_name, variables)
    if restricted is None:
        restricted = privacy.must_stay_local(task, document, taxonomy.load())
    doc_id = document.id if document else None
    routes = _allowed_routes(task, restricted, version, doc_id)
    cfg = routing.load()
    timeout_s = cfg.limits.timeout_s.get(task, 120)
    over_budget: BudgetExceeded | None = None
    attempted = False

    def logged(route: Route, status: str, t0: float, result: Any = None, **kw: Any) -> int:
        tin, tout = _usage(result)
        return runs.log(
            task,
            route,
            restricted=restricted,
            prompt_version=version,
            status=status,
            document_id=doc_id,
            tokens_in=tin,
            tokens_out=tout,
            cost_usd=budgets.cost(route, tin, tout),
            latency_ms=int((time.monotonic() - t0) * 1000),
            **kw,
        )

    for route in routes:
        try:
            budgets.check(route)
        except BudgetExceeded as e:
            over_budget = e
            continue
        attempted = True
        prompt, failures, invalid_retried = text, 0, False
        while failures <= cfg.limits.retries:
            t0 = time.monotonic()
            try:
                result = _invoke(route, prompt, output, timeout_s)
                value = result.structured_output
                if value is None:
                    raise ValueError("no structured output returned")
            except TimeoutError as e:
                logged(route, "timeout", t0, error=str(e))
                failures += 1
            except Exception as e:  # noqa: BLE001 - provider errors are retried, then fall back
                status = "invalid" if type(e).__name__ == "StructuredOutputException" else "error"
                logged(route, status, t0, error=f"{type(e).__name__}: {e}")
                failures += 1
            else:
                try:
                    value = validate(value) if validate else value
                except ValueError as e:
                    logged(
                        route,
                        "invalid",
                        t0,
                        result,
                        output=value.model_dump(mode="json"),
                        error=str(e),
                    )
                    if invalid_retried:
                        raise InvalidOutput(f"{task}: {e}") from None
                    invalid_retried = True
                    prompt = (
                        f"{text}\n\nYour previous answer was invalid: {e}\n"
                        "Return only valid JSON matching the schema."
                    )
                    continue
                run_id = logged(route, "ok", t0, result, output=value.model_dump(mode="json"))
                return StructuredResult(value, run_id, route, version, restricted)
            if failures <= cfg.limits.retries:
                time.sleep(BACKOFF_S * 2 ** (failures - 1))
        log.warning("%s: route %s failed, trying the next one", task, route)
    if over_budget and not attempted:
        raise over_budget
    raise AllRoutesFailed(task)


ToolsArg = list | Callable[[Route], list]


async def run_agent(
    task: str,
    prompt_name: str,
    variables: dict,
    tools: ToolsArg,
    messages: list[dict],
    *,
    documents_restricted: bool = False,
    stream: bool = True,
    route: str | None = None,
) -> AsyncIterator[dict]:
    """Run a tool-using agent and yield events:
        {"type": "token", "text"} · {"type": "tool_call", "name", "args"}
        {"type": "tool_result", "name", "summary", "result"} · {"type": "done", "ai_run_id", ...}
    `messages` are Strands messages, the new user turn last. `tools` may be a function of the
    chosen route, so tools can mask restricted content when the route is not local.
    Raises NoAllowedRoute / BudgetExceeded / AIDisabled before the first event."""
    from strands import Agent

    system, version = render(prompt_name, variables)
    candidates = _allowed_routes(task, documents_restricted, version, None)
    if route:
        candidates = [r for r in candidates if str(r) == route] or candidates
    cfg = routing.load()
    t = cfg.tasks[task]
    over_budget: BudgetExceeded | None = None
    for i, r in enumerate(candidates):
        try:
            budgets.check(r)
        except BudgetExceeded as e:
            over_budget = e
            continue
        agent = Agent(
            model=router.model_for(r),
            system_prompt=system,
            messages=messages[:-1],  # type: ignore[arg-type]  # Strands Message TypedDicts
            tools=tools(r) if callable(tools) else tools,
            callback_handler=None,
        )
        names: dict[str, str] = {}
        state: dict[str, Any] = {
            "text": "",
            "tool_calls": [],
            "emitted": False,
            "result": None,
            "logged": False,
            "t0": time.monotonic(),
        }
        log_args = (task, r, documents_restricted, version, state)
        try:
            async with asyncio.timeout(cfg.limits.timeout_s.get(task, 300)):
                async for ev in agent.stream_async(
                    messages[-1]["content"], limits={"turns": t.max_tool_calls + 1}
                ):
                    for out in _map_event(ev, names, state):
                        state["emitted"] = True
                        yield out
            stop = getattr(state["result"], "stop_reason", None)
            run_id = _log_agent(*log_args, "ok")
            yield {
                "type": "done",
                "ai_run_id": run_id,
                "text": state["text"],
                "tool_calls": state["tool_calls"],
                "route": str(r),
                "local": r.local,
                "limited": stop == "limit_turns",
                "usage": dict(
                    zip(("tokens_in", "tokens_out"), _usage(state["result"]), strict=True)
                ),
            }
            return
        except Exception as e:  # noqa: BLE001
            status = "timeout" if isinstance(e, TimeoutError) else "error"
            _log_agent(*log_args, status, f"{type(e).__name__}: {e}")
            if state["emitted"] or i == len(candidates) - 1:
                raise
            log.warning("%s: route %s failed before streaming, falling back", task, r)
        finally:  # the client went away mid-stream (GeneratorExit / CancelledError)
            if not state["logged"]:
                _log_agent(*log_args, "error", "cancelled")
    if over_budget:
        raise over_budget
    raise AllRoutesFailed(task)


def _log_agent(
    task: str,
    r: Route,
    restricted: bool,
    version: str,
    state: dict,
    status: str,
    error: str | None = None,
) -> int:
    state["logged"] = True
    tin, tout = _usage(state["result"])
    return runs.log(
        task,
        r,
        restricted=restricted,
        prompt_version=version,
        status=status,
        tokens_in=tin,
        tokens_out=tout,
        cost_usd=budgets.cost(r, tin, tout),
        latency_ms=int((time.monotonic() - state["t0"]) * 1000),
        output={"text": state["text"], "tool_calls": state["tool_calls"]},
        error=error,
    )


def _map_event(ev: dict, names: dict[str, str], state: dict) -> list[dict]:
    if "data" in ev and isinstance(ev["data"], str):
        state["text"] += ev["data"]
        return [{"type": "token", "text": ev["data"]}]
    if "result" in ev:
        state["result"] = ev["result"]
        return []
    msg = ev.get("message")
    if not msg:
        return []
    out: list[dict] = []
    for block in msg.get("content", []):
        if "toolUse" in block:
            use = block["toolUse"]
            names[use["toolUseId"]] = use["name"]
            out.append({"type": "tool_call", "name": use["name"], "args": use.get("input", {})})
        elif "toolResult" in block:
            res = block["toolResult"]
            name = names.get(res.get("toolUseId", ""), "tool")
            payload = _tool_payload(res)
            summary = payload.get("summary") if isinstance(payload, dict) else None
            call = {"name": name, "summary": summary or str(payload)[:200]}
            state["tool_calls"].append(call)
            out.append({"type": "tool_result", **call, "result": payload})
    return out


def _tool_payload(res: dict) -> Any:
    import json

    for c in res.get("content", []):
        if "json" in c:
            return c["json"]
        if "text" in c:
            try:
                return json.loads(c["text"])
            except ValueError:
                return c["text"]
    return None
