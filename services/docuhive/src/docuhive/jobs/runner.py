"""Lease-based claiming, execution and recovery."""

import logging
import os
import socket
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select, update

from docuhive.db import session
from docuhive.db.models import Job
from docuhive.jobs import (
    HANDLERS,
    JobContext,
    PermanentFailure,
    _Deferred,
    handler,
    periodic,
)

log = logging.getLogger(__name__)


def backoff(attempt: int) -> timedelta:
    return timedelta(seconds=min(30 * 2 ** min(max(attempt - 1, 0), 7), 3600))


def claim(queues: list[str]) -> Job | None:
    with session() as db:
        job = db.scalar(
            select(Job)
            .where(
                Job.status == "pending", Job.queue.in_(queues), Job.run_after <= datetime.now(UTC)
            )
            .order_by(Job.run_after, Job.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        job.status, job.locked_at = "running", datetime.now(UTC)
        job.locked_by = f"{socket.gethostname()}:{os.getpid()}:{uuid4()}"
        job.attempts += 1
        registration = HANDLERS.get(job.kind)
        if registration:
            job.max_attempts = registration.max_attempts
        db.flush()
        db.expunge(job)
        return job


def run(job: Job) -> None:
    now = datetime.now(UTC)
    values: dict = {"locked_at": None, "locked_by": None, "note": None}
    registration = HANDLERS.get(job.kind)
    if registration is None:
        values.update(
            status="pending",
            run_after=now + timedelta(hours=1),
            attempts=job.attempts - 1,
            note="no handler",
        )
    else:
        ctx = JobContext(job.id, job.attempts, log, job.locked_by or "")
        try:
            registration.fn(job.payload, ctx)
        except _Deferred as deferred:
            values.update(
                status="pending",
                run_after=deferred.until,
                attempts=job.attempts - 1,
                note=deferred.reason,
            )
        except Exception as error:
            dead = isinstance(error, PermanentFailure) or job.attempts >= job.max_attempts
            values.update(
                status="dead" if dead else "pending",
                last_error=f"{type(error).__name__}: {error}"[:2000],
                run_after=datetime.now(UTC) + backoff(job.attempts),
                finished_at=datetime.now(UTC) if dead else None,
            )
            log.warning("Job %s (%s) %s", job.id, job.kind, "failed" if dead else "will retry")
        else:
            values.update(status="done", finished_at=datetime.now(UTC), last_error=None)
    with session() as db:
        # An expired worker cannot overwrite a new worker's lease or result.
        db.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "running", Job.locked_by == job.locked_by)
            .values(**values)
        )


def reap() -> int:
    now = datetime.now(UTC)
    count = 0
    with session() as db:
        jobs = db.scalars(
            select(Job).where(Job.status == "running").with_for_update(skip_locked=True)
        )
        for job in jobs:
            registration = HANDLERS.get(job.kind)
            timeout = registration.timeout_s if registration else 600
            if job.locked_at and job.locked_at < now - timedelta(seconds=timeout):
                _release(job, now, "Worker lease expired")
                count += 1
    return count


def _release(job: Job, now: datetime, reason: str) -> None:
    job.status = "dead" if job.attempts >= job.max_attempts else "pending"
    job.run_after, job.locked_at, job.locked_by = now, None, None
    job.last_error = reason
    if job.status == "dead":
        job.finished_at = now


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def release_orphans() -> int:
    """At worker start, free jobs held by a dead process on this host, without waiting out
    their lease (30 minutes for OCR). A restarted container keeps its hostname and often
    its PID, so a lease with our own PID is a predecessor's; a live sibling's is left alone.
    """
    host, me, now, count = socket.gethostname(), os.getpid(), datetime.now(UTC), 0
    with session() as db:
        jobs = db.scalars(
            select(Job)
            .where(Job.status == "running", Job.locked_by.startswith(f"{host}:", autoescape=True))
            .with_for_update(skip_locked=True)
        )
        for job in jobs:
            pid = int((job.locked_by or "").split(":")[-2])
            if pid == me or not _alive(pid):
                _release(job, now, "Worker stopped while running this job")
                count += 1
    return count


@periodic("jobs.cleanup", every=timedelta(days=1))
@handler("jobs.cleanup")
def cleanup(payload: dict, ctx: JobContext) -> None:
    with session() as db:
        db.execute(
            delete(Job).where(
                Job.status == "done", Job.finished_at < datetime.now(UTC) - timedelta(days=30)
            )
        )
