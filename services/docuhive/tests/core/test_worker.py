"""Shutdown, queue outages and scheduler connection ownership without external services."""

import signal
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from docuhive import worker


def test_consumer_finishes_current_job_before_stopping(monkeypatch):
    stopped = threading.Event()
    handled = []
    monkeypatch.setattr(worker, "claim", lambda queues: "claimed")

    def finish(job):
        handled.append(job)
        stopped.set()

    monkeypatch.setattr(worker, "run", finish)
    worker._consume(["ocr"], stopped)
    assert handled == ["claimed"]


def test_consumer_backs_off_after_database_outage(monkeypatch):
    stopped = threading.Event()
    waits = []

    def unavailable(queues):
        raise RuntimeError("database unavailable")

    def wait(seconds):
        waits.append(seconds)
        stopped.set()

    monkeypatch.setattr(worker, "claim", unavailable)
    monkeypatch.setattr(stopped, "wait", wait)
    worker._consume(["ocr"], stopped)
    assert waits == [5]


def test_scheduler_holds_connection_until_releasing_leadership(monkeypatch):
    stopped = threading.Event()
    activity = []

    class Connection:
        def execute(self, statement):
            activity.append("ping")

        def commit(self):
            pass

    @contextmanager
    def connect():
        activity.append("open")
        yield Connection()
        activity.append("close")

    monkeypatch.setattr(worker, "get_engine", lambda: SimpleNamespace(connect=connect))
    monkeypatch.setattr(worker.scheduler, "acquire", lambda connection: True)
    monkeypatch.setattr(worker.scheduler, "release", lambda connection: activity.append("release"))
    monkeypatch.setattr(worker.scheduler, "tick", stopped.set)
    monkeypatch.setattr(worker, "reap", lambda: activity.append("reap"))
    worker._schedule(["ocr"], stopped)
    assert activity == ["open", "ping", "reap", "release", "close"]


def test_worker_sigterm_stops_all_threads_and_imports_touchpoints(monkeypatch):
    signals, imports = {}, []
    monkeypatch.setattr(worker.signal, "signal", lambda sig, fn: signals.setdefault(sig, fn))
    monkeypatch.setattr(worker, "HANDLER_MODULES", ["synthetic.handlers"])
    monkeypatch.setattr(worker, "import_module", imports.append)
    monkeypatch.setattr(worker, "start_intelligence", lambda: None)
    monkeypatch.setattr(worker, "claim", lambda queues: None)

    def stop(queues, stopped):
        signals[signal.SIGTERM](None, None)

    monkeypatch.setattr(worker, "_schedule", stop)
    before = set(threading.enumerate())
    worker.serve(["ocr"], 2)
    assert imports == ["synthetic.handlers"]
    assert set(threading.enumerate()) <= before
    with pytest.raises(ValueError):
        worker.serve([], 0)
