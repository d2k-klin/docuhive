"""Exercise handler outcomes without a database; SQL concurrency is checked separately."""

import logging
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from docuhive import jobs
from docuhive.db.models import Job
from docuhive.jobs import Handler, JobContext, PermanentFailure, RetryLater, runner


@pytest.fixture
def memory(monkeypatch):
    writes = []

    class Store:
        def execute(self, statement):
            writes.append(statement.compile().params)

    @contextmanager
    def session():
        yield Store()

    monkeypatch.setattr(runner, "session", session)
    monkeypatch.setattr(jobs, "session", session)
    registry = {}
    monkeypatch.setattr(runner, "HANDLERS", registry)
    monkeypatch.setattr(jobs, "HANDLERS", registry)
    return writes


def job(attempts=1, max_attempts=3):
    return Job(
        id=42,
        kind="test.policy",
        payload={"synthetic": True},
        queue="default",
        status="running",
        attempts=attempts,
        max_attempts=max_attempts,
        locked_by="original-lease",
        locked_at=datetime.now(UTC),
    )


def test_success_and_no_handler(memory):
    runner.run(job())
    assert memory[-1]["status"] == "pending" and memory[-1]["attempts"] == 0
    assert memory[-1]["note"] == "no handler"
    jobs.HANDLERS["test.policy"] = Handler(lambda *_: None, "default", 3, 600)
    runner.run(job())
    assert memory[-1]["status"] == "done" and memory[-1]["last_error"] is None
    assert memory[-1]["locked_by_1"] == "original-lease"


@pytest.mark.parametrize(
    "error,attempt,expected",
    [
        (RetryLater("temporarily unavailable"), 1, "pending"),
        (RuntimeError("failed"), 3, "dead"),
        (PermanentFailure("invalid input"), 1, "dead"),
    ],
)
def test_failure_policy(memory, error, attempt, expected):
    def fail(payload, ctx):
        raise error

    jobs.HANDLERS["test.policy"] = Handler(fail, "default", 3, 600)
    runner.run(job(attempts=attempt))
    state = memory[-1]
    assert state["status"] == expected
    assert (state["finished_at"] is not None) == (expected == "dead")
    assert state["last_error"].startswith(type(error).__name__)


def test_defer_and_heartbeat_keep_the_lease_and_attempt_budget(memory):
    until = datetime.now(UTC) + timedelta(minutes=2)

    def defer(payload, ctx):
        ctx.heartbeat()
        ctx.defer(until, "vault unavailable")

    jobs.HANDLERS["test.policy"] = Handler(defer, "default", 3, 600)
    runner.run(job(attempts=2))
    assert memory[0]["locked_by_1"] == "original-lease"
    assert memory[-1]["status"] == "pending"
    assert memory[-1]["attempts"] == 1 and memory[-1]["run_after"] == until
    with pytest.raises(ValueError):
        JobContext(42, 1, logging.getLogger("test")).defer(datetime.now(), "naive time")


def test_invalid_registration_options_are_rejected():
    with pytest.raises(ValueError):
        jobs.handler("invalid", max_attempts=0)
    with pytest.raises(ValueError):
        jobs.periodic("invalid", every=timedelta(0))


@pytest.mark.parametrize("answers,expected", [([91], 91), ([None, 92], 92), ([None, None, 93], 93)])
def test_enqueue_conflict_and_completed_job_race(monkeypatch, answers, expected):
    from sqlalchemy.dialects import postgresql

    responses = iter(answers)
    queries = []

    class Store:
        def scalar(self, statement):
            queries.append(str(statement.compile(dialect=postgresql.dialect())))
            return next(responses)

    @contextmanager
    def session():
        yield Store()

    monkeypatch.setattr(jobs, "session", session)
    assert jobs.enqueue("test.enqueue", {}, dedupe_key="same") == expected
    assert "ON CONFLICT" in queries[0] and "DO NOTHING" in queries[0]
    assert len(queries) == len(answers)
