"""Durable PostgreSQL jobs and public registration contracts."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from docuhive.db import session
from docuhive.db.models import Job


class RetryLater(Exception):
    """Retry a transient failure using the job's backoff policy."""


class PermanentFailure(Exception):
    """Fail immediately without additional attempts."""


class _Deferred(Exception):
    def __init__(self, until: datetime, reason: str):
        self.until, self.reason = until, reason


@dataclass(frozen=True)
class Handler:
    fn: Callable
    queue: str
    max_attempts: int
    timeout_s: int


@dataclass(frozen=True)
class Periodic:
    every: timedelta
    queue: str


HANDLERS: dict[str, Handler] = {}
PERIODICS: dict[str, Periodic] = {}


def document_jobs(document_ids: list[str]) -> list[dict]:
    """Read progress without exposing job payloads or internal errors to the browser."""
    with session() as db:
        rows = db.execute(
            select(Job.id, Job.kind, Job.status, Job.payload, Job.run_after, Job.note)
            .where(
                Job.kind.in_(("document.stored", "ai.classify", "ai.extract", "index.embed")),
                Job.payload["document_id"].as_string().in_(document_ids),
            )
            .order_by(Job.id.desc())
        )
        return [
            {
                "id": r.id,
                "kind": r.kind,
                "status": r.status,
                "document_id": r.payload["document_id"],
                "run_after": r.run_after,
                "paused": bool(r.note and r.note.startswith("budget:")),
            }
            for r in rows
        ]


def handler(
    kind: str, *, queue: str = "default", max_attempts: int = 5, timeout_s: int = 600
) -> Callable:
    if max_attempts < 1 or timeout_s < 1:
        raise ValueError("Job attempts and timeout must be positive")

    def register(fn: Callable) -> Callable:
        HANDLERS[kind] = Handler(fn, queue, max_attempts, timeout_s)
        return fn

    return register


def periodic(kind: str, *, every: timedelta, queue: str = "default") -> Callable:
    if every.total_seconds() <= 0:
        raise ValueError("Periodic interval must be positive")

    def register(fn: Callable) -> Callable:
        if kind not in HANDLERS:
            handler(kind, queue=queue)(fn)
        PERIODICS[kind] = Periodic(every, queue)
        return fn

    return register


def enqueue(
    kind: str,
    payload: dict,
    *,
    queue: str = "default",
    run_after: datetime | None = None,
    dedupe_key: str | None = None,
    in_session: Session | None = None,
) -> int:
    """Queue a job. With `in_session`, the job commits (or rolls back) with the caller's own
    change, so a state change and the work it implies can never be separated by a crash."""
    registration = HANDLERS.get(kind)
    values = {
        "kind": kind,
        "payload": payload,
        "queue": queue,
        "dedupe_key": dedupe_key,
        "max_attempts": registration.max_attempts if registration else 5,
        "run_after": run_after or datetime.now(UTC),
    }
    statement = (
        insert(Job)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=[Job.dedupe_key], index_where=text("status IN ('pending','running')")
        )
        .returning(Job.id)
    )
    if in_session is not None:
        return _insert(in_session, statement, dedupe_key)
    with session() as db:
        return _insert(db, statement, dedupe_key)


def _insert(db: Session, statement: Any, dedupe_key: str | None) -> int:
    # READ COMMITTED takes a fresh snapshot for the select after a conflicting insert.
    while True:
        job_id = db.scalar(statement)
        if job_id is not None:
            return job_id
        existing = db.scalar(
            select(Job.id).where(
                Job.dedupe_key == dedupe_key, Job.status.in_(["pending", "running"])
            )
        )
        if existing is not None:
            return existing
            # The conflicting job may have finished between INSERT and SELECT.


@dataclass
class JobContext:
    job_id: int
    attempt: int
    log: logging.Logger
    _lease: str = ""

    def heartbeat(self) -> None:
        with session() as db:
            db.execute(
                update(Job)
                .where(Job.id == self.job_id, Job.status == "running", Job.locked_by == self._lease)
                .values(locked_at=datetime.now(UTC))
            )

    def defer(self, until: datetime, reason: str) -> NoReturn:
        if until.tzinfo is None:
            raise ValueError("Deferred jobs require a timezone-aware datetime")
        raise _Deferred(until, reason)
