"""Public health and protected platform operations."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from docuhive import __version__
from docuhive.auth import require_admin
from docuhive.contracts import CurrentUser
from docuhive.db import session
from docuhive.db.models import Job

router = APIRouter(prefix="/api/system", tags=["system"])
Admin = Annotated[CurrentUser, Depends(require_admin)]


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/jobs")
def jobs(
    user: Admin,
    status: Literal["pending", "running", "done", "dead"] | None = None,
    kind: str | None = None,
    queue: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: int | None = Query(default=None, ge=0),
) -> dict:
    query = select(Job).order_by(Job.id.desc()).limit(limit + 1)
    for column, value in ((Job.status, status), (Job.kind, kind), (Job.queue, queue)):
        if value is not None:
            query = query.where(column == value)
    if cursor is not None:
        query = query.where(Job.id < cursor)
    with session() as db:
        rows = list(db.scalars(query))
        # Payloads and raw errors can contain private document data and are not exposed here.
        items = [
            {
                "id": j.id,
                "kind": j.kind,
                "queue": j.queue,
                "status": j.status,
                "attempts": j.attempts,
                "max_attempts": j.max_attempts,
                "run_after": j.run_after,
                "note": j.note,
                "last_error": "Processing failed; see server logs." if j.last_error else None,
            }
            for j in rows[:limit]
        ]
        return {
            "items": items,
            "next_cursor": str(rows[limit - 1].id) if len(rows) > limit else None,
        }


@router.post("/jobs/{job_id}/retry", status_code=204)
def retry(job_id: int, user: Admin) -> None:
    from datetime import UTC, datetime

    with session() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if not job:
            raise HTTPException(404, "Job not found")
        if job.status != "dead":
            raise HTTPException(409, "Only failed jobs can be retried")
        if job.dedupe_key:
            active = db.scalar(
                select(Job.id).where(
                    Job.dedupe_key == job.dedupe_key, Job.status.in_(["pending", "running"])
                )
            )
            if active:
                raise HTTPException(409, "An active job already has this deduplication key")
        job.status, job.attempts, job.run_after = "pending", 0, datetime.now(UTC)
        job.locked_at, job.locked_by, job.finished_at, job.last_error = None, None, None, None


@router.get("/sse-test")
async def sse_test(user: Admin) -> StreamingResponse:
    async def ticks() -> AsyncIterator[str]:
        for tick in range(10):
            await asyncio.sleep(0.5)
            yield f"event: tick\ndata: {json.dumps({'tick': tick})}\n\n"

    return StreamingResponse(
        ticks(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
