"""Backup orchestration, failure recovery and retention without external services."""

import importlib.util
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("backup_script", ROOT / "deploy/scripts/backup.py")
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


@pytest.fixture
def environment(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "_system/db").mkdir(parents=True)
    (vault / "_system/VAULT_ID").write_text("synthetic-vault")
    staging = tmp_path / "staging"
    staging.mkdir()
    password = tmp_path / "password"
    password.write_text("synthetic-password")
    password.chmod(0o600)
    for key, value in {
        "DOCUHIVE_VAULT_HOST_DIR": vault,
        "DOCUHIVE_STAGING_HOST_DIR": staging,
        "DOCUHIVE_VAULT_ID": "synthetic-vault",
        "DOCUHIVE_PROD_ENV": tmp_path / "synthetic.env",
        "RESTIC_PASSWORD_FILE": password,
        "RESTIC_REPOSITORIES": "'/backup/target one' /backup/two",
    }.items():
        monkeypatch.setenv(key, str(value))
    return vault, staging, password


def runner(calls, fail=None):
    def command(args, **kwargs):
        calls.append(args)
        if args[:2] == ["restic", "version"]:
            return SimpleNamespace(stdout=b"restic 0.18.1 compiled with go")
        if "ps" in args:
            return SimpleNamespace(stdout=b"api\nworker\nworker-ocr\npostgres\n")
        if "pg_dump" in args:
            kwargs["stdout"].write(b"synthetic database dump")
        if fail and fail in args:
            raise subprocess.CalledProcessError(1, args, stderr=b"credentials never published")
        return SimpleNamespace(stdout=b"")

    return command


def test_backup_quiesces_validates_dumps_checks_targets_and_restarts(environment, monkeypatch):
    vault, staging, _ = environment
    for number in range(20):
        (vault / f"_system/db/docuhive-202601{number:02}.dump").write_bytes(b"old")
    calls = []
    monkeypatch.setattr(backup, "command", runner(calls))
    result = backup.backup(datetime(2026, 11, 1, tzinfo=UTC))  # Sunday + first of month
    assert result["ok"] and len(result["targets"]) == 2
    assert sum("stop" in call for call in calls) == 1
    assert sum("start" in call for call in calls) == 1
    assert sum("forget" in call for call in calls) == 2
    assert sum("check" in call for call in calls) == 2
    assert sum("pg_restore" in call for call in calls) == 1
    assert len(list((vault / "_system/db").glob("*.dump"))) == 14
    restic_calls = [call for call in calls if "backup" in call]
    assert all(str(staging) in call and str(vault / "library") in call for call in restic_calls)
    assert json.loads((vault / "_system/backup-status.json").read_text())["ok"]


@pytest.mark.parametrize("failure", ["stop", "pg_dump", "backup", "start"])
def test_backup_failures_keep_last_success_and_restart_writers(environment, monkeypatch, failure):
    vault, _, _ = environment
    (vault / "_system/backup-status.json").write_text(
        json.dumps({"last_success": "2026-01-01T00:00:00+00:00"})
    )
    calls = []
    monkeypatch.setattr(backup, "command", runner(calls, failure))
    result = backup.backup(datetime(2026, 11, 4, tzinfo=UTC))
    assert not result["ok"]
    if failure != "start":
        assert result["last_success"] == "2026-01-01T00:00:00+00:00"
    assert any("start" in call for call in calls)
    assert "credentials" not in json.dumps(result)
    assert not list((vault / "_system/db").glob("*.partial"))


def test_backup_refuses_unmounted_vault_and_public_password_file(environment, monkeypatch):
    vault, _, password = environment
    calls = []
    monkeypatch.setattr(backup, "command", runner(calls))
    password.chmod(0o644)
    with pytest.raises(ValueError, match="mode 600"):
        backup.backup()
    password.chmod(0o600)
    (vault / "_system/VAULT_ID").write_text("wrong-vault")
    with pytest.raises(ValueError, match="registered vault"):
        backup.backup()
    # An unmounted share has no marker at all: the same refusal, not a crash.
    (vault / "_system/VAULT_ID").unlink()
    with pytest.raises(ValueError, match="registered vault"):
        backup.backup()
    assert not calls


@pytest.mark.parametrize("failure", ["", "stop", "backup", "migrate"])
def test_upgrade_failure_boundary(tmp_path, monkeypatch, failure):
    import os
    import shutil

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(ROOT / "deploy/scripts/upgrade.sh", scripts / "upgrade.sh")
    log = tmp_path / "commands.jsonl"
    monkeypatch.setenv("UPGRADE_LOG", str(log))
    monkeypatch.setenv("UPGRADE_FAILURE", failure)
    monkeypatch.setenv("DOCUHIVE_PROD_ENV", "old.env")
    monkeypatch.setenv("PATH", f"{scripts}:{os.environ['PATH']}")
    stub = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["UPGRADE_LOG"], "a") as out:
    out.write(json.dumps(sys.argv) + "\\n")
fail = os.environ["UPGRADE_FAILURE"]
failed = ((fail == "migrate" and "run" in sys.argv) or (fail == "stop" and "stop" in sys.argv) or
          (fail == "backup" and sys.argv[0].endswith("backup.sh")))
sys.exit(1 if failed else 0)
"""
    for name in ["docker", "backup.sh"]:
        (scripts / name).write_text(stub)
        (scripts / name).chmod(0o755)
    result = subprocess.run([str(scripts / "upgrade.sh"), "new.env"], capture_output=True)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert any("build" in call for call in calls)
    assert result.returncode == (1 if failure else 0)
    if failure in {"backup", "stop"}:
        assert any("start" in call and "old.env" in call for call in calls)
        assert not any("run" in call for call in calls)
    elif failure == "migrate":
        assert not any("start" in call for call in calls)
        assert any("stop" in call and "new.env" in call for call in calls)
    else:
        assert any("up" in call and "new.env" in call for call in calls)


def test_snapshot_verifier_refuses_empty_or_changed_document_bytes(tmp_path):
    import runpy

    verify = runpy.run_path(str(ROOT / "deploy/drills/verify_snapshot.py"))["verify"]
    source, restored = tmp_path / "source", tmp_path / "restored"
    source.mkdir()
    restored.mkdir()
    with pytest.raises(ValueError, match="no documents"):
        verify(source, restored)
    for root in [source, restored]:
        (root / "2026/synthetic").mkdir(parents=True)
        (root / "2026/synthetic/meta.json").write_text('{"id":"synthetic"}')
        (root / "2026/synthetic/original.pdf").write_bytes(b"synthetic")
    verify(source, restored)
    (restored / "2026/synthetic/original.pdf").write_bytes(b"changed")
    with pytest.raises(ValueError, match="differ"):
        verify(source, restored)


def test_options_from_the_app_are_checked_one_by_one(tmp_path):
    (tmp_path / "_system").mkdir()
    assert backup.options(tmp_path) == backup.DEFAULTS  # no file: the old behaviour
    (tmp_path / "_system/backup.json").write_text(
        json.dumps(
            {
                "time": "25:99",  # wrong: keeps 03:00
                "days": [6],
                "keep": {"daily": 30, "weekly": -1, "monthly": True, "dumps": 3},
                "check_percent": 10,
                "include": {"staging": False, "plugins": "yes", "linked_folders": True},
                "linked_paths": ["/srv/storage/papers", 7],
            }
        )
    )
    chosen = backup.options(tmp_path)
    assert chosen["time"] == "03:00" and chosen["days"] == [6]
    assert chosen["keep"] == {"daily": 30, "weekly": 8, "monthly": 24, "dumps": 3}
    assert chosen["check_percent"] == 10
    assert chosen["include"] == {"staging": False, "plugins": True, "linked_folders": True}
    assert chosen["linked_paths"] == ["/srv/storage/papers"]


def test_due_follows_the_schedule_catches_up_and_obeys_a_request():
    sundays = backup.DEFAULTS | {"time": "03:00", "days": [6]}
    sunday = datetime(2026, 11, 15, 3, 10).astimezone()  # host time
    assert backup.due(sunday, sundays, {}, requested=False)  # never ran
    ran = {"at": sunday.isoformat()}
    assert not backup.due(sunday + timedelta(minutes=15), sundays, ran, requested=False)
    assert not backup.due(sunday + timedelta(days=3), sundays, ran, requested=False)
    # The host was off on Sunday: Monday morning it catches up.
    last_week = {"at": (sunday - timedelta(days=7)).isoformat()}
    assert backup.due(sunday + timedelta(days=1), sundays, last_week, requested=False)
    assert backup.due(sunday + timedelta(days=3), sundays, ran, requested=True)
    before = sunday.replace(hour=2, minute=50)
    assert not backup.due(before, sundays, last_week, requested=False)


def test_options_shape_the_run_and_extras_stay_inside_their_folders(
    environment, monkeypatch, tmp_path
):
    vault, staging, _ = environment
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    storage = tmp_path / "storage"
    (storage / "papers").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("DOCUHIVE_PLUGINS_HOST_DIR", str(plugins))
    monkeypatch.setenv("DOCUHIVE_STORAGE_ROOT_HOST_DIR", str(storage))
    (vault / "_system/backup.json").write_text(
        json.dumps(
            {
                "keep": {"daily": 3, "weekly": 2, "monthly": 1, "dumps": 2},
                "check_percent": 0,
                "include": {"staging": False, "plugins": True, "linked_folders": True},
                "linked_paths": [str(storage / "papers"), str(elsewhere), str(vault)],
            }
        )
    )
    (vault / "_system/backup-request.json").write_text("{}")
    for number in range(5):
        (vault / f"_system/db/docuhive-2026010{number}.dump").write_bytes(b"old")
    calls = []
    monkeypatch.setattr(backup, "command", runner(calls))
    result = backup.backup(datetime(2026, 11, 1, tzinfo=UTC))
    assert result["ok"] and result["included"] == ["vault", "database", "plugins", "linked:1"]
    [restic] = [c for c in calls if "backup" in c and "restic" in c][:1]
    assert str(plugins) in restic and str(storage / "papers") in restic
    assert str(staging) not in restic and str(elsewhere) not in restic
    forget = next(c for c in calls if "forget" in c)
    assert forget[forget.index("--keep-daily") + 1 :][:5] == [
        "3",
        "--keep-weekly",
        "2",
        "--keep-monthly",
        "1",
    ]
    assert not any("check" in c for c in calls)  # checking switched off
    assert len(list((vault / "_system/db").glob("*.dump"))) == 2
    assert not (vault / "_system/backup-request.json").exists()
    status = json.loads((vault / "_system/backup-status.json").read_text())
    assert "running_since" not in status and status["last_prune"]
    # A week has not passed: no second prune.
    calls.clear()
    backup.backup(datetime(2026, 11, 3, tzinfo=UTC))
    assert not any("forget" in c for c in calls)
