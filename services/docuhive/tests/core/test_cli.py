"""CLI dispatch must preserve queue selection, fail-fast security and password handling."""

import json
import logging
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
    synthetic_secret = "synthetic-test-secret-with-at-least-32-bytes"  # gitleaks:allow
    monkeypatch.setenv("DOCUHIVE_SECRET_KEY", synthetic_secret)
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


@pytest.mark.parametrize(
    ("line", "secret"),
    [
        ("login password=hunter2 user=a", "hunter2"),
        ('{"token": "dh_abc123", "user": "a"}', "dh_abc123"),
        ("Authorization: Bearer eyJ.secret.value", "eyJ.secret.value"),
        ("cookie: dh_session=abcdef; theme=dark", "abcdef"),
        ("GET /api/capture?api_key=k123&page=2", "k123"),
        ('{"password": "alpha bravo charlie"}', "bravo charlie"),
        ('{"secret": "with \\"escaped\\" quote"}', "escaped"),
        ("Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
    ],
)
def test_log_lines_never_carry_secret_values(line, secret):
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "%s", (line,), None)
    assert cli.Redact().filter(record)
    assert "[redacted]" in record.getMessage()
    assert secret not in record.getMessage()


def test_redaction_leaves_ordinary_lines_alone():
    record = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "session expired for %s", ("a",), None
    )
    cli.Redact().filter(record)
    assert record.getMessage() == "session expired for a"


def test_access_log_keeps_its_arguments_after_redaction():
    from uvicorn.logging import AccessFormatter

    args = ("127.0.0.1:5000", "GET", "/api/reminders.ics?token=dh_abc", "1.1", 200)
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d', args, None
    )
    cli.Redact().filter(record)
    line = AccessFormatter(use_colors=False).format(record)
    assert "dh_abc" not in line and "token=[redacted]" in line and "200" in line


def test_api_logging_config_filters_root_and_uvicorn_handlers(monkeypatch):
    seen = {}
    monkeypatch.setattr("uvicorn.run", lambda *a, **kw: seen.update(kw))
    monkeypatch.setattr(sys, "argv", ["docuhive", "api", "--reload"])
    cli.main()
    config = seen["log_config"]
    assert config["root"]["handlers"] == ["root"]
    assert all(h["filters"] == ["redact"] for h in config["handlers"].values())
