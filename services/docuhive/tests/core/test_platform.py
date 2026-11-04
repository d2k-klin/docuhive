"""Key-free checks for health, CLI, transactions and extension fallback."""

import pytest
from docuhive import __version__, db
from docuhive.api.app import create_app
from docuhive.cli import parser
from docuhive.jobs.runner import backoff
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


def test_health_and_error_envelope(monkeypatch):
    monkeypatch.setattr("docuhive.api.app.start_intelligence", lambda: None)
    with TestClient(create_app()) as client:
        response = client.get("/api/system/health")
        assert response.json() == {"status": "ok", "version": __version__}
        denied = client.get("/api/system/jobs")
        assert denied.status_code == 401
        assert denied.json()["error"]["code"] == "http_401"
        invalid = client.post("/api/auth/login", json={}, headers={"X-DocuHive-CSRF": "1"})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "validation_error"


def test_cli_arguments():
    assert parser().parse_args(["worker", "--queues", "ocr", "--concurrency", "1"]).queues == "ocr"
    assert parser().parse_args(["db", "current"]).action == "current"
    assert parser().parse_args(["api"]).host == "127.0.0.1"


def test_session_commit_and_rollback(monkeypatch):
    engine = create_engine("sqlite://")
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    with db.session() as session:
        session.execute(text("CREATE TABLE sample (value integer)"))
        session.execute(text("INSERT INTO sample VALUES (1)"))
    with pytest.raises(RuntimeError), db.session() as session:
        session.execute(text("INSERT INTO sample VALUES (2)"))
        raise RuntimeError("rollback")
    with db.session() as session:
        assert session.scalar(text("SELECT sum(value) FROM sample")) == 1


def test_backoff_caps_without_excessive_integer_growth():
    assert [backoff(attempt).total_seconds() for attempt in (1, 2, 3, 8, 10000)] == [
        30,
        60,
        120,
        3600,
        3600,
    ]


def test_optional_intelligence_imports_leave_core_runnable(monkeypatch):
    from docuhive import startup

    def missing(name):
        raise ModuleNotFoundError(name="docuhive.ai")

    monkeypatch.setattr(startup, "import_module", missing)
    startup.start_intelligence()

    def broken(name):
        raise ModuleNotFoundError(name="a_required_dependency")

    monkeypatch.setattr(startup, "import_module", broken)
    startup.start_intelligence()
