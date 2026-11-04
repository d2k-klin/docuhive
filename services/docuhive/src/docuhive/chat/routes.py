"""/api/chat (sessions, streamed answers over SSE) and /api/analyses (saved analyses)."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from docuhive import config, db, jobs
from docuhive.agents.ask import ask
from docuhive.agents.base import AIDisabled
from docuhive.ai import router as ai_router
from docuhive.ai import routing
from docuhive.ai.budgets import BudgetExceeded
from docuhive.ai.http import User, fail
from docuhive.ai.privacy import NoAllowedRoute
from docuhive.chat.models import Analysis, ChatMessage, ChatSession
from docuhive.contracts import CurrentUser, SearchFilters

router = APIRouter(prefix="/api/chat", tags=["chat"])
analyses_router = APIRouter(prefix="/api/analyses", tags=["analyses"])
HEARTBEAT_S = 15.0


class SessionIn(BaseModel):
    title: str | None = None
    filters: SearchFilters = SearchFilters()
    local_only: bool = False
    route: str | None = None


class SessionPatch(BaseModel):
    title: str | None = None
    filters: SearchFilters | None = None
    local_only: bool | None = None
    route: str | None = None


def _session_out(s: ChatSession) -> dict:
    return {
        "id": s.id,
        "title": s.title,
        "filters": s.filters,
        "local_only": s.local_only,
        "route": s.route,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


def _msg_out(m: ChatMessage) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "citations": m.citations or [],
        "tool_calls": m.tool_calls or [],
        "flags": m.flags or {},
        "ai_run_id": m.ai_run_id,
        "created_at": m.created_at,
    }


def _own(s: Any, sid: int, user: CurrentUser) -> ChatSession:
    sess = s.get(ChatSession, sid)
    if sess is None or sess.user_id != user.id:
        fail(404, "not_found", "Chat not found")
    return sess


@router.get("/routes")
def routes(user: User) -> dict:
    """The routes this user may pick for chat (local flags for the selector)."""
    cfg = routing.load()
    allowed = {str(r) for r in ai_router.resolve("chat", restricted=False)}
    t = cfg.tasks["chat"]
    items = [
        {"route": str(r), "local": r.local, "default": i == 0}
        for i, r in enumerate(ai_router.parse_route(x, cfg) for x in [t.route, *t.fallback])
        if str(r) in allowed
    ]
    local = [str(r) for r in ai_router.resolve("chat", restricted=True)]
    return {
        "items": items,
        "local_only_forced": cfg.privacy.local_only,
        "local_available": bool(local),
    }


@router.post("/sessions")
def create_session(body: SessionIn, user: User) -> dict:
    with db.session() as s:
        sess = ChatSession(
            user_id=user.id,
            title=body.title,
            filters=body.filters.model_dump(mode="json", exclude_defaults=True),
            local_only=body.local_only,
            route=body.route,
        )
        s.add(sess)
        s.flush()
        return _session_out(sess)


@router.get("/sessions")
def list_sessions(user: User) -> dict:
    with db.session() as s:
        rows = s.scalars(
            select(ChatSession)
            .where(ChatSession.user_id == user.id)
            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
            .limit(100)
        )
        return {"items": [_session_out(x) for x in rows], "next_cursor": None}


@router.get("/sessions/{sid}")
def get_session(sid: int, user: User) -> dict:
    with db.session() as s:
        return _session_out(_own(s, sid, user))


@router.patch("/sessions/{sid}")
def patch_session(sid: int, body: SessionPatch, user: User) -> dict:
    with db.session() as s:
        sess = _own(s, sid, user)
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(
                sess,
                k,
                v
                if k != "filters"
                else SearchFilters(**v).model_dump(mode="json", exclude_defaults=True),
            )
        sess.updated_at = datetime.now(UTC)
        return _session_out(sess)


@router.delete("/sessions/{sid}")
def delete_session(sid: int, user: User) -> dict:
    with db.session() as s:
        _own(s, sid, user)
        s.execute(delete(ChatMessage).where(ChatMessage.session_id == sid))
        s.execute(delete(ChatSession).where(ChatSession.id == sid))
    return {"ok": True}


@router.get("/sessions/{sid}/messages")
def messages(sid: int, user: User) -> dict:
    with db.session() as s:
        _own(s, sid, user)
        rows = s.scalars(
            select(ChatMessage).where(ChatMessage.session_id == sid).order_by(ChatMessage.id)
        )
        return {"items": [_msg_out(m) for m in rows], "next_cursor": None}


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


def _error(e: BaseException) -> dict:
    if isinstance(e, BudgetExceeded):
        return {"code": "budget_exceeded", "message": f"{e}. Switch to a local model to continue."}
    if isinstance(e, NoAllowedRoute):
        return {"code": "no_allowed_route", "message": e.reason}
    if isinstance(e, AIDisabled):
        return {"code": "ai_disabled", "message": "AI is switched off on this server."}
    return {"code": "provider_error", "message": f"The model failed: {type(e).__name__}"}


async def answer_stream(sid: int, user: CurrentUser, content: str) -> AsyncIterator[str]:
    with db.session() as s:
        sess = _own(s, sid, user)
        history = [
            {"role": m.role, "content": m.content}
            for m in s.scalars(
                select(ChatMessage).where(ChatMessage.session_id == sid).order_by(ChatMessage.id)
            )
        ]
        scope, local_only, route = SearchFilters(**sess.filters), sess.local_only, sess.route
        if not sess.title:
            sess.title = content[:60]
        sess.updated_at = datetime.now(UTC)
        s.add(ChatMessage(session_id=sid, role="user", content=content))
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def produce() -> None:
        try:
            async for ev in ask(
                user,
                history,
                content,
                scope=scope,
                local_only=local_only or routing.load().privacy.local_only,
                route=route,
            ):
                await queue.put(ev)
        except Exception as e:  # noqa: BLE001 - reported to the client as an error event
            await queue.put({"type": "error", **_error(e)})
        finally:
            await queue.put(None)

    task = asyncio.create_task(produce())
    text, tool_calls, finished = "", [], False
    try:
        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), HEARTBEAT_S)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if ev is None:
                break
            kind = ev.pop("type")
            if kind == "token":
                text += ev["text"]
            elif kind == "tool_result":
                result = ev.pop("result", None)
                call = {"name": ev["name"], "summary": ev["summary"]}
                if ev["name"] == "query_facts" and isinstance(result, dict):
                    call["result"] = {k: result.get(k) for k in ("rows", "aggregates", "field")}
                    ev["result"] = call["result"]
                tool_calls.append(call)
            elif kind == "done":
                finished = True
                with db.session() as s:
                    msg = ChatMessage(
                        session_id=sid,
                        role="assistant",
                        content=ev["text"],
                        citations=[c["document_id"] for c in ev["citations"]],
                        tool_calls=tool_calls,
                        ai_run_id=ev["ai_run_id"],
                        flags={
                            "uncited": ev["uncited"],
                            "limited": ev.get("limited", False),
                            "route": ev.get("route"),
                            "local": ev.get("local"),
                        },
                    )
                    s.add(msg)
                    s.flush()
                    mid = msg.id
                ev = {
                    "message_id": mid,
                    "ai_run_id": ev["ai_run_id"],
                    "uncited": ev["uncited"],
                    "usage": ev.get("usage"),
                    "route": ev.get("route"),
                    "local": ev.get("local"),
                }
            elif kind == "error":
                finished = True
            yield sse(kind, ev)
    finally:
        if not finished:  # client disconnected: cancel generation, keep what we have
            task.cancel()
            with db.session() as s:
                s.add(
                    ChatMessage(
                        session_id=sid,
                        role="assistant",
                        content=text,
                        tool_calls=tool_calls,
                        flags={"truncated": True},
                    )
                )


@router.post("/sessions/{sid}/messages")
async def post_message(sid: int, body: MessageIn, user: User) -> StreamingResponse:
    with db.session() as s:
        _own(s, sid, user)
    return StreamingResponse(
        answer_stream(sid, user, body.content),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---- saved analyses (QA-04) ------------------------------------------------------------------


class AnalysisIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=4000)
    filters: SearchFilters = SearchFilters()
    route: str | None = None


def _analysis_out(a: Analysis) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "prompt": a.prompt,
        "filters": a.filters,
        "route": a.route,
        "last_run_at": a.last_run_at,
        "last_result": a.last_result,
        "created_at": a.created_at,
    }


def _own_analysis(s: Any, aid: int, user: CurrentUser) -> Analysis:
    a = s.get(Analysis, aid)
    if a is None or a.user_id != user.id:
        fail(404, "not_found", "Analysis not found")
    return a


@analyses_router.get("/templates")
def templates(user: User) -> dict:
    """Built-in templates (config/defaults/analyses.yaml; the overlay can add more)."""
    return {"items": config.load_yaml("analyses.yaml").get("templates", [])}


@analyses_router.get("")
def list_analyses(user: User) -> dict:
    with db.session() as s:
        rows = s.scalars(select(Analysis).where(Analysis.user_id == user.id).order_by(Analysis.id))
        return {"items": [_analysis_out(a) for a in rows], "next_cursor": None}


@analyses_router.post("")
def create_analysis(body: AnalysisIn, user: User) -> dict:
    with db.session() as s:
        a = Analysis(
            user_id=user.id,
            name=body.name,
            prompt=body.prompt,
            route=body.route,
            filters=body.filters.model_dump(mode="json", exclude_defaults=True),
        )
        s.add(a)
        s.flush()
        return _analysis_out(a)


@analyses_router.get("/{aid}")
def get_analysis(aid: int, user: User) -> dict:
    with db.session() as s:
        return _analysis_out(_own_analysis(s, aid, user))


@analyses_router.patch("/{aid}")
def patch_analysis(aid: int, body: AnalysisIn, user: User) -> dict:
    with db.session() as s:
        a = _own_analysis(s, aid, user)
        a.name, a.prompt, a.route = body.name, body.prompt, body.route
        a.filters = body.filters.model_dump(mode="json", exclude_defaults=True)
        return _analysis_out(a)


@analyses_router.delete("/{aid}")
def delete_analysis(aid: int, user: User) -> dict:
    with db.session() as s:
        _own_analysis(s, aid, user)
        s.execute(delete(Analysis).where(Analysis.id == aid))
    return {"ok": True}


@analyses_router.post("/{aid}/run")
def run_analysis(aid: int, user: User) -> dict:
    """Runs as a job (task=analyse); the UI polls GET /api/analyses/{id}."""
    with db.session() as s:
        _own_analysis(s, aid, user)
    job = jobs.enqueue(
        "analyses.run",
        {"analysis_id": aid, "user": user.model_dump()},
        queue="ai",
        dedupe_key=f"analysis:{aid}",
    )
    return {"job_id": job, "status": "queued"}
