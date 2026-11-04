"""Source adapters and operations against the existing network-free storage fixture."""

import errno
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from docuhive import config, db, ingest
from docuhive.contracts import IngestResult
from docuhive.db.models import Document, Setting
from docuhive.ingest import consume
from docuhive.vault import backup, library
from docuhive.vault.availability import available
from sqlalchemy import select

from .test_archive_tools import add, tools  # noqa: F401
from .test_auth_integration import CSRF, login
from .test_auth_memory import client  # noqa: F401


@pytest.fixture
def mounted(tools):
    (tools.vault / "_system" / "VAULT_ID").write_text("synthetic-vault")
    with db.session() as session:
        session.add(Setting(key="vault.id", value="synthetic-vault"))
    return tools


def test_token_upload_uses_the_contract_and_never_accepts_another_owner(mounted, tmp_path, monkeypatch):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    calls = []
    monkeypatch.setattr(ingest, "incoming_dir", lambda: incoming)
    def submit(files, req):
        calls.append((files[0].read_bytes(), req))
        return IngestResult(document_id="synthetic", status="staged")
    monkeypatch.setattr(ingest, "submit", submit)
    token = mounted.post("/api/tokens", json={"name": "phone", "scopes": ["upload"]}, headers=CSRF).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    response = mounted.post("/api/upload?source=mobile&combine=true", files={"files": ("../../scan.jpg", b"synthetic", "image/jpeg")}, headers=headers)
    assert response.status_code == 202 and response.json()["document_id"] == "synthetic"
    assert calls[0][0] == b"synthetic" and calls[0][1].source.kind == "api"
    assert calls[0][1].source.original_filename == "scan.jpg" and calls[0][1].owner_id == 1
    assert calls[0][1].combine and not list(incoming.iterdir())
    assert mounted.get("/api/auth/me", headers=headers).status_code == 403
    assert mounted.post("/api/upload?expected_owner_id=2", files={"files": ("a.pdf", b"x")}, headers=headers).status_code == 403
    assert len(calls) == 1
    assert mounted.post("/api/upload", files={"files": ("a.pdf", b"x")}).status_code == 403


def test_upload_rejection_limits_chunked_body_and_cleans_temporary_files(mounted, tmp_path, monkeypatch):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    monkeypatch.setattr(ingest, "incoming_dir", lambda: incoming)
    monkeypatch.setenv("DOCUHIVE_MAX_UPLOAD_MB", "1")
    config.reload()
    def reject(files, req):
        raise ingest.UnsupportedType()
    monkeypatch.setattr(ingest, "submit", reject)
    assert mounted.post("/api/upload", files={"files": ("a.txt", b"hi")}, headers=CSRF).status_code == 415
    assert not list(incoming.iterdir())
    too_big = mounted.post("/api/upload", files={"files": ("a.pdf", b"x" * (1024 * 1024 + 1))}, headers=CSRF)
    assert too_big.status_code == 413
    def chunks():
        yield b"--boundary\r\nContent-Disposition: form-data; name=\"files\"; filename=\"a.pdf\"\r\nContent-Type: application/pdf\r\n\r\n"
        for _ in range(4):
            yield b"x" * 1024 * 1024
        yield b"\r\n--boundary--\r\n"
    result = mounted.post("/api/upload", content=chunks(), headers={**CSRF, "Content-Type": "multipart/form-data; boundary=boundary"})
    assert result.status_code == 413
    assert not list(incoming.iterdir())


def test_scanner_stability_persistent_ledger_and_verified_release(mounted, tmp_path, monkeypatch):
    root = mounted.vault / "consume"
    (root / "owner").mkdir(parents=True)
    source = root / "owner" / "scan.pdf"
    source.write_bytes(b"first")
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    monkeypatch.setattr(ingest, "incoming_dir", lambda: incoming)
    calls = []
    def submit(files, req):
        calls.append((files[0].read_bytes(), req))
        add("scanned", vault=mounted.vault)
        (mounted.vault / "2026/scanned/original.pdf").write_bytes(files[0].read_bytes())
        with db.session() as session:
            session.get(Document, "scanned").status = "processing"
        files[0].unlink()
        return IngestResult(document_id="scanned", status="staged")
    monkeypatch.setattr(ingest, "submit", submit)
    ctx = SimpleNamespace(log=logging.getLogger("test"), heartbeat=lambda: None)
    consume.poll({}, ctx)  # initialise durable ledger
    consume.poll({}, ctx)  # first observation
    source.write_bytes(b"still writing")
    consume.poll({}, ctx)
    assert not calls
    consume.poll({}, ctx)
    assert len(calls) == 1 and calls[0][1].owner_id == 1
    assert calls[0][1].source.kind == "consume" and source.exists()
    consume.poll({}, ctx)
    assert source.exists() and len(calls) == 1
    with db.session() as session:
        session.get(Document, "scanned").status = "stored"
    (mounted.vault / "2026/scanned/original.pdf").write_bytes(b"wrong checksum")
    consume.poll({}, ctx)
    assert source.exists()
    (mounted.vault / "2026/scanned/original.pdf").write_bytes(b"still writing")
    consume.poll({}, ctx)
    assert not source.exists() and len(calls) == 1


def test_scanner_ignore_rejection_and_outage_preserve_inputs(mounted, tmp_path, monkeypatch):
    root = mounted.vault / "consume"
    (root / "owner").mkdir(parents=True)
    for name in [".hidden", "~$temp.pdf", "a.part", "a.tmp", "a.crdownload", "Thumbs.db"]:
        (root / "owner" / name).write_bytes(b"ignored")
    (root / "unowned.pdf").write_bytes(b"unowned")
    (root / "owner" / "bad.exe").write_bytes(b"rejected")
    (root / "owner" / "link.pdf").symlink_to(root / "unowned.pdf")
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    monkeypatch.setattr(ingest, "incoming_dir", lambda: incoming)
    calls = []
    def reject(files, req):
        calls.append(req)
        raise ingest.UnsupportedType()
    monkeypatch.setattr(ingest, "submit", reject)
    ctx = SimpleNamespace(log=logging.getLogger("test"), heartbeat=lambda: None)
    for _ in range(3):
        consume.poll({}, ctx)
    assert len(calls) == 1 and (root / "unowned.pdf").exists()
    assert len(list((root / "_rejected").glob("*.exe"))) == 1
    assert list((root / "_rejected").glob("*.reason.txt"))
    marker = mounted.vault / "_system" / "VAULT_ID"
    marker.unlink()
    (root / "owner" / "new.pdf").write_bytes(b"kept")
    for _ in range(3):
        consume.poll({}, ctx)
    assert (root / "owner" / "new.pdf").exists() and len(calls) == 1


def test_library_hardlinks_collision_privacy_metadata_changes_and_no_copy(mounted, monkeypatch):
    for doc_id in ["a", "b"]:
        add(doc_id, title='A / title:*?', shared=True, vault=mounted.vault)
    add("private", title="Private", owner=2, vault=mounted.vault)
    original = mounted.vault / "2026/a/archive.pdf"
    assert library.sync() == {"ok": True, "links": 3}
    links = sorted((mounted.vault / "library").rglob("*.pdf"))
    assert any("(2)" in p.name for p in links)
    assert all(p.stat().st_ino == original.stat().st_ino for p in links if "(2)" not in p.name and "_private" not in str(p))
    assert (mounted.vault / "library/_private").stat().st_mode & 0o777 == 0o700
    assert library.sync()["links"] == 3
    foreign = mounted.vault / "library/keep.txt"
    foreign.write_text("user file")
    with db.session() as session:
        session.get(Document, "a").title = "New title"
        session.get(Document, "b").deleted_at = datetime.now(UTC)
    assert library.sync()["links"] == 2
    assert original.exists() and foreign.exists()
    assert library.component("../../") == "untitled"
    with db.session() as session:
        session.get(Document, "a").title = "Another title"
    def denied(*args):
        raise OSError(errno.EXDEV, "no hardlinks")
    monkeypatch.setattr(library.os, "link", denied)
    assert library.sync()["reason"] == "hardlinks_unavailable"
    assert library.sync()["reason"] == "hardlinks_unavailable"
    with db.session() as session:
        assert session.get(Setting, library.DISABLED).value is True
    assert original.exists()


def test_library_refuses_symlink_escape_and_vault_mismatch(mounted, tmp_path):
    add("escape", shared=True, vault=mounted.vault)
    (mounted.vault / "library").symlink_to(tmp_path)
    with pytest.raises(ValueError):
        library.sync()
    assert not list(tmp_path.glob("*.pdf"))
    (mounted.vault / "_system/VAULT_ID").write_text("another-vault")
    assert not available() and library.sync()["reason"] == "vault_unavailable"


def test_backup_status_is_sanitised_stale_and_guides_the_user(mounted):
    path = mounted.vault / "_system/backup-status.json"
    now = datetime.now(UTC)
    path.write_text(json.dumps({"at": now.isoformat(), "ok": True, "last_success": now.isoformat(), "targets": [{"ok": True, "url": "secret"}], "error": "secret"}))
    response = mounted.get("/api/system/backup")
    assert response.json()["targets_ok"] == 1 and response.json()["stale"] is False
    assert "secret" not in response.text
    checks = mounted.get("/api/system/setup-status").json()
    assert next(c for c in checks if c["id"] == "backup")["status"] == "ok"
    path.write_text(json.dumps({"last_success": (now - timedelta(days=3)).isoformat(), "ok": True}))
    assert backup.status().stale
    path.write_text("not json")
    assert backup.status().stale
    login(mounted, "other")
    assert mounted.get("/api/system/backup").status_code == 403
