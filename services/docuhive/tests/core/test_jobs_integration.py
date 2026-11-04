"""Real PostgreSQL proof for dedupe, leases, retries and scheduler leadership."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from docuhive.db import session
from docuhive.db.models import Job, Setting
from docuhive.jobs import (
    HANDLERS,
    PERIODICS,
    PermanentFailure,
    RetryLater,
    enqueue,
    handler,
    periodic,
)
from docuhive.jobs.runner import claim, reap, run
from docuhive.jobs.scheduler import acquire, release, tick
from sqlalchemy import select, text

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def registrations():
    handlers, periodics = HANDLERS.copy(), PERIODICS.copy()
    HANDLERS.clear()
    PERIODICS.clear()
    yield
    HANDLERS.clear()
    HANDLERS.update(handlers)
    PERIODICS.clear()
    PERIODICS.update(periodics)


def fetch(job_id):
    with session() as db:
        job = db.get(Job, job_id)
        db.expunge(job)
        return job


def make_due(job_id):
    with session() as db:
        db.get(Job, job_id).run_after = datetime.now(UTC) - timedelta(seconds=1)


def test_concurrent_dedupe_and_exactly_one_claim(postgres):
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: enqueue("sample", {}, dedupe_key="one"), range(20)))
    assert len(set(ids)) == 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        claimed = list(pool.map(lambda _: claim(["default"]), range(20)))
    assert len([job for job in claimed if job]) == 1


@pytest.mark.parametrize(
    "error,attempts,status",
    [
        (RetryLater("retry"), 1, "pending"),
        (RuntimeError("transient"), 2, "dead"),
        (PermanentFailure("stop"), 1, "dead"),
    ],
)
def test_retry_and_dead(postgres, error, attempts, status):
    @handler("sample", max_attempts=2)
    def work(payload, ctx):
        raise error

    job_id = enqueue("sample", {})
    for _attempt in range(attempts):
        make_due(job_id)
        run(claim(["default"]))
    job = fetch(job_id)
    assert job.status == status and job.attempts == attempts
    assert job.last_error
    assert (job.finished_at is not None) == (status == "dead")
    if status == "pending":
        assert 25 <= (job.run_after - datetime.now(UTC)).total_seconds() <= 31


def test_unknown_handler_defers_without_attempt(postgres):
    job_id = enqueue("document.stored", {}, queue="ai")
    run(claim(["ai"]))
    job = fetch(job_id)
    assert job.status == "pending" and job.attempts == 0 and job.note == "no handler"
    assert 3590 < (job.run_after - datetime.now(UTC)).total_seconds() <= 3600


def test_defer_heartbeat_success_and_stale_worker(postgres):
    until = datetime.now(UTC) + timedelta(minutes=2)

    @handler("sample", timeout_s=2)
    def defer(payload, ctx):
        ctx.heartbeat()
        ctx.defer(until, "vault unavailable")

    job_id = enqueue("sample", {})
    run(claim(["default"]))
    job = fetch(job_id)
    assert job.status == "pending" and job.attempts == 0 and job.run_after == until
    make_due(job_id)
    expired = claim(["default"])
    with session() as db:
        db.get(Job, job_id).locked_at = datetime.now(UTC) - timedelta(seconds=3)
    assert reap() == 1
    reclaimed = claim(["default"])
    HANDLERS["sample"] = type(HANDLERS["sample"])(lambda *_: None, "default", 5, 2)
    run(expired)
    assert fetch(job_id).locked_by == reclaimed.locked_by
    run(reclaimed)
    assert fetch(job_id).status == "done"
    assert enqueue("sample", {}, dedupe_key="completed") != job_id


def test_scheduler_leader_and_periodic_dedupe(postgres):
    @periodic("sample", every=timedelta(seconds=1))
    def sample(payload, ctx):
        pass

    with postgres.connect() as first, postgres.connect() as second:
        assert acquire(first)
        assert not acquire(second)
        tick()
        tick()
        with session() as db:
            assert len(list(db.scalars(select(Job)))) == 1
            assert db.get(Setting, "periodic:sample")
        release(first)
        assert acquire(second)
        release(second)


def test_migration_environments_have_separate_versions(postgres):
    from alembic.script import ScriptDirectory
    from docuhive.db.migrations import migration_config

    with session() as db:
        for track in ("core", "intel"):
            expected = ScriptDirectory.from_config(migration_config(track)).get_current_head()
            assert db.scalar(text(f"SELECT version_num FROM alembic_version_{track}")) == expected
        assert db.scalar(
            text(
                "SELECT to_tsvector('dh_german', 'Müller Rechnungen') @@ "
                "websearch_to_tsquery('dh_german', 'Muller Rechnung')"
            )
        )


def test_killed_worker_lease_recovers_without_duplicate_completion(postgres, tmp_path):
    import os
    import subprocess
    import sys
    import time

    marker = tmp_path / "claimed"

    @handler("test.block", queue="worker-proof", timeout_s=1)
    def recovered(payload, ctx):
        pass

    job_id = enqueue("test.block", {"marker": str(marker)}, queue="worker-proof")
    script = """
import time
from pathlib import Path
from docuhive.jobs import handler
from docuhive.worker import serve
@handler("test.block", queue="worker-proof", timeout_s=1)
def blocked(payload, ctx):
    Path(payload["marker"]).touch()
    time.sleep(60)
serve(["worker-proof"], 1)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        env=dict(os.environ),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20
        while not marker.exists() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(0.05)
        assert marker.exists(), "Worker did not claim the synthetic job"
        process.kill()
        process.wait(timeout=5)
        time.sleep(1.1)
        assert reap() >= 1
        job = claim(["worker-proof"])
        assert job.id == job_id and job.attempts == 2
        run(job)
        assert fetch(job_id).status == "done"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
