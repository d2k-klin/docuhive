"""Linked folders on PostgreSQL: files are analysed where they are, never moved or changed."""

import functools
import logging
import os
import time

import pytest
from docuhive import config, db, folders, vault
from docuhive.api.app import create_app
from docuhive.auth import create_user
from docuhive.auth.rate_limit import LoginLimiter
from docuhive.db.models import DocSource, Document, LinkedFile
from docuhive.ingest import process as pipeline
from docuhive.jobs import JobContext
from docuhive.vault import health
from fastapi.testclient import TestClient
from sqlalchemy import select

from .test_auth_integration import CSRF, PASSWORD
from .test_document_core import blank_pdf, fake_build

pytestmark = pytest.mark.integration
CTX = JobContext(1, 1, logging.getLogger("t"))


@functools.cache
def pdf(text: str) -> bytes:
    import io

    import pikepdf

    out = io.BytesIO()
    doc = pikepdf.open(io.BytesIO(blank_pdf()))
    doc.docinfo["/Title"] = text  # different bytes per file
    doc.save(out)
    return out.getvalue()


def old(path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    past = time.time() - 3600  # settled: not being written any more
    os.utime(path, (past, past))


@pytest.fixture
def client(postgres, monkeypatch, tmp_path):
    monkeypatch.setattr("docuhive.api.app.start_intelligence", lambda: None)
    monkeypatch.setattr("docuhive.api.auth.limiter", LoginLimiter())
    monkeypatch.setattr(pipeline, "build", fake_build)
    monkeypatch.setenv("DOCUHIVE_STORAGE_ROOT", str(tmp_path / "nas"))
    (tmp_path / "nas").mkdir()
    config.reload()
    vault._probed.clear()
    vault.init()
    create_user("owner", PASSWORD, admin=True)
    create_user("member", PASSWORD)
    with TestClient(create_app(), base_url="https://testserver") as client:
        yield client


def login(client, name):
    client.post("/api/auth/login", json={"username": name, "password": PASSWORD}, headers=CSRF)


def documents() -> dict[str, str]:
    """path in the folder -> document id."""
    with db.session() as s:
        return {
            r.path: r.document_id
            for r in s.scalars(select(LinkedFile).where(LinkedFile.state == "linked"))
        }


def test_a_linked_folder_is_analysed_in_place(client, tmp_path):
    papers = tmp_path / "nas" / "papers"
    old(papers / "Strom 2025.pdf", pdf("strom"))
    old(papers / "Steuer" / "Bescheid.pdf", pdf("bescheid"))
    old(papers / "notes.bin", b"\x00\x01\x02 not a document")
    old(papers / ".hidden.pdf", pdf("hidden"))
    old(papers / "@eaDir" / "thumb.pdf", pdf("nas thumbnail"))
    login(client, "member")
    assert client.get("/api/folders").status_code == 403
    login(client, "owner")
    refused = client.post("/api/folders", json={"path": "../.."}, headers=CSRF)
    assert refused.status_code == 409
    made = client.post(
        "/api/folders", json={"path": "papers", "label": "Papers", "shared": True}, headers=CSRF
    )
    assert made.status_code == 201, made.text
    folder = made.json()
    assert folder["label"] == "Papers" and folder["scanning"] is True
    nested = client.post("/api/folders", json={"path": "papers/Steuer"}, headers=CSRF)
    assert nested.status_code == 409 and "overlaps" in nested.json()["error"]["message"]

    folders.scan({"folder_id": folder["id"]}, CTX)
    linked = documents()
    assert set(linked) == {"Strom 2025.pdf", "Steuer/Bescheid.pdf"}
    [skipped] = client.get(f"/api/folders/{folder['id']}/files?state=skipped").json()
    assert skipped["path"] == "notes.bin"
    for doc_id in linked.values():
        pipeline.process({"document_id": doc_id}, CTX)

    doc_id = linked["Steuer/Bescheid.pdf"]
    with db.session() as s:
        doc = s.get(Document, doc_id)
        source = s.get(DocSource, doc_id)
        assert doc.status == "stored" and doc.shared
        assert (source.kind, source.folder, source.path) == (
            "folder",
            "Papers",
            "Steuer/Bescheid.pdf",
        )
        assert source.file_modified_at is not None
        stored = vault.root() / doc.vault_path
    # The vault keeps DocuHive's copy and a pointer; the file itself never moved.
    assert sorted(p.name for p in stored.iterdir()) == [
        "archive.pdf",
        "linked.json",
        "meta.json",
        "thumb.webp",
    ]
    assert vault.original(stored) == papers / "Steuer" / "Bescheid.pdf"
    assert (papers / "Steuer" / "Bescheid.pdf").read_bytes() == pdf("bescheid")
    original = client.get(f"/api/documents/{doc_id}/file?kind=original")
    assert original.status_code == 200 and original.content == pdf("bescheid")
    assert health.scan(full=True).ok

    # The same file again, uploaded by hand earlier or later, is recognised.
    old(papers / "Kopie.pdf", pdf("strom"))
    folders.scan({"folder_id": folder["id"]}, CTX)
    with db.session() as s:
        copy = s.scalar(select(LinkedFile).where(LinkedFile.path == "Kopie.pdf"))
        assert (copy.state, copy.document_id) == ("duplicate", linked["Strom 2025.pdf"])

    # A file that disappears is marked missing; its searchable copy stays.
    (papers / "Steuer" / "Bescheid.pdf").unlink()
    folders.scan({"folder_id": folder["id"]}, CTX)
    assert client.get("/api/folders").json()[0]["counts"]["missing"] == 1
    assert any(p.kind == "original_missing" for p in health.scan(full=False).problems)
    assert (stored / "archive.pdf").is_file()

    # Stop following: the documents stay.
    assert client.delete(f"/api/folders/{folder['id']}", headers=CSRF).status_code == 204
    assert client.get("/api/folders").json() == []
    with db.session() as s:
        assert s.get(Document, doc_id) is not None


def test_an_upload_records_who_and_from_which_device(client):
    login(client, "owner")
    iphone = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
    )
    sent = client.post(
        "/api/upload",
        params={"source": "mobile"},
        files=[("files", ("Quittung.pdf", pdf("quittung")))],
        headers=CSRF | {"User-Agent": iphone},
    )
    assert sent.status_code == 202, sent.text
    with db.session() as s:
        source = s.get(DocSource, sent.json()["document_id"])
        got = (source.kind, source.uploaded_by, source.device)
    assert got == (
        "mobile",
        "owner",
        "iPhone · Safari",
    )


def test_the_phone_page_gives_a_qr_code_and_says_when_it_cannot_work(client, monkeypatch):
    login(client, "member")
    local = client.get("/api/system/phone").json()
    assert local["url"].endswith("/capture") and "only works on this computer" in local["problem"]
    assert local["svg"].startswith("<?xml") or local["svg"].startswith("<svg")
    monkeypatch.setenv("DOCUHIVE_PUBLIC_URL", "https://docuhive.home.arpa")
    config.reload()
    home = client.get("/api/system/phone").json()
    assert (home["url"], home["problem"]) == ("https://docuhive.home.arpa/capture", None)
