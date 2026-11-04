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
                job.status = "dead" if job.attempts >= job.max_attempts else "pending"
                job.run_after, job.locked_at, job.locked_by = now, None, None
                job.last_error = "Worker lease expired"
                if job.status == "dead":
                    job.finished_at = now
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
