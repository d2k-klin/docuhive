"""CLI dispatch must preserve queue selection, fail-fast security and password handling."""

import json
import sys

import pytest
from docuhive import cli, config


def test_openapi_cli_is_machine_readable(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["docuhive", "openapi"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["info"]["title"] == "DocuHive"


def test_worker_and_api_dispatch(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "docuhive.worker.serve", lambda queues, concurrency: calls.append((queues, concurrency))
    )
    monkeypatch.setattr(
        sys, "argv", ["docuhive", "worker", "--queues", "ocr, default", "--concurrency", "1"]
    )
    cli.main()
    assert calls == [(["ocr", "default"], 1)]
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.setattr(sys, "argv", ["docuhive", "api", "--port", "8123"])
    cli.main()
    assert calls[-1]["port"] == 8123 and calls[-1]["host"] == "127.0.0.1"


def test_db_upgrade_dispatch_and_production_downgrade_guard(monkeypatch):
    calls = []
    monkeypatch.setattr("docuhive.db.migrations.migrate", lambda *args: calls.append(args))
    monkeypatch.setattr(sys, "argv", ["docuhive", "db", "upgrade"])
    cli.main()
    assert calls == [("upgrade", None)]
    monkeypatch.setenv("DOCUHIVE_ENV", "prod")
    monkeypatch.setenv("DOCUHIVE_SECRET_KEY", "synthetic-test-secret-with-at-least-32-bytes")
    config.reload()
    monkeypatch.setattr(sys, "argv", ["docuhive", "db", "downgrade"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2 and len(calls) == 1


def test_user_password_mismatch_never_creates_user(monkeypatch):
    called = []
    prompts = iter(["a synthetic password", "a different password"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(prompts))
    monkeypatch.setattr("docuhive.auth.create_user", lambda *args, **kwargs: called.append(args))
    monkeypatch.setattr(sys, "argv", ["docuhive", "user", "create", "synthetic"])
    with pytest.raises(SystemExit):
        cli.main()
    assert called == []
