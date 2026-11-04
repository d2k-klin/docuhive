"""Document core against the network-free storage fake: upload, processing, vault, edits, trash.

OCR and conversion are replaced by a stub `build`; test_document_core_integration.py runs the
real pipeline on PostgreSQL with Tesseract and Gotenberg.
"""

import io
import json
import logging
import shutil

import pytest
from docuhive import db, vault
from docuhive.db.models import AuditLog, Document, Job
from docuhive.ingest import process as pipeline
from docuhive.ingest.errors import Quarantine
from docuhive.jobs import JobContext, _Deferred
from docuhive.vault import health
from PIL import Image
from sqlalchemy import select

from .test_archive_tools import client, tools  # noqa: F401
from .test_auth_integration import CSRF

PDF = b"%PDF-1.4\nsynthetic QA-DOC:core-001\n%%EOF\n"


def fake_build(work, files):
    archive = work / "archive.pdf"
    shutil.copyfile(files[0], archive)
    (work / "thumb.webp").write_bytes(b"synthetic thumbnail")
    combined = None
    if len(files) > 1:
        combined = work / "combined.pdf"
        combined.write_bytes(PDF)
    return pipeline.Built(
        archive=archive,
        thumb=work / "thumb.webp",
        combined=combined,
        content="Synthetic invoice 84.20 EUR",
        pages=len(files),
    )


@pytest.fixture
def core(tools, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pipeline, "build", fake_build)
    vault._checked.clear()
    vault.init()
    return tools


def run(doc_id: str, attempt: int = 1) -> None:
    pipeline.process({"document_id": doc_id}, JobContext(1, attempt, logging.getLogger("t")))


def kinds() -> list[str]:
    with db.session() as session:
        return list(session.scalars(select(Job.kind).order_by(Job.id)))


def status(doc_id: str) -> str:
    with db.session() as session:
        return session.scalar(select(Document.status).where(Document.id == doc_id))


def upload(client, data=PDF, name="Rechnung.pdf", **params):  # noqa: F811
    return client.post("/api/upload", files=[("files", (name, data))], params=params, headers=CSRF)


def test_upload_stores_in_vault_and_edits_follow(core):
    response = upload(core, category="utilities/electricity", tags=["property"])
    assert response.status_code == 202, response.text
    doc_id = response.json()["document_id"]
    assert response.json()["status"] == "staged"
    assert upload(core).json() == {"document_id": doc_id, "status": "duplicate"}
    assert not list((vault.root().parent / "staging" / "incoming").iterdir())
    pending = core.get("/api/documents/pending").json()
    assert [(p["id"], p["status"], p["title"]) for p in pending] == [(doc_id, "staged", "Rechnung")]

    run(doc_id)
    assert status(doc_id) == "stored"
    assert "document.stored" in kinds()
    assert not (vault.root().parent / "staging" / doc_id).exists()
    folder = next(vault.root().glob(f"*/{doc_id}"))
    assert (folder / "original.pdf").read_bytes() == PDF
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["schema"] == 1 and meta["id"] == doc_id and meta["owner"] == "owner"
    assert meta["category"] == "utilities/electricity" and meta["tags"] == ["property"]
    assert set(meta["manual_fields"]) == {"category", "tags"}
    assert health.scan(full=True).ok

    detail = core.get(f"/api/documents/{doc_id}").json()
    assert detail["status"] == "stored" and detail["files"] == ["original", "archive", "thumb"]
    archive = core.get(f"/api/documents/{doc_id}/file?kind=archive")
    assert archive.status_code == 200 and archive.content == PDF
    assert "inline" in archive.headers["content-disposition"]
    original = core.get(f"/api/documents/{doc_id}/file?kind=original&download=true")
    assert 'attachment; filename="Rechnung.pdf"' in original.headers["content-disposition"]
    assert core.get(f"/api/documents/{doc_id}/thumbnail").content == b"synthetic thumbnail"

    edited = core.patch(
        f"/api/documents/{doc_id}",
        json={
            "title": "Electricity  invoice",
            "correspondent": "  Stadtwerke   Muster ",
            "facts": {"amount": {"type": "money", "value": "84.20", "currency": "EUR"}},
            "tags_remove": ["property"],
            "shared": False,
        },
        headers=CSRF,
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["document"]["title"] == "Electricity invoice"
    assert body["document"]["correspondent"] == "Stadtwerke Muster"
    assert body["document"]["tags"] == [] and body["document"]["shared"] is False
    assert {"title", "correspondent", "facts.amount", "tags", "shared"} <= set(
        body["result"]["applied"]
    )
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["correspondent"] == "Stadtwerke Muster" and meta["shared"] is False
    assert meta["facts"]["amount"]["value"] == "84.20"
    assert "document.metadata_changed" in kinds()
    actions = [h["action"] for h in core.get(f"/api/documents/{doc_id}/history").json()]
    assert actions[0] == "metadata" and "ingest.stored" in actions

    unknown = core.patch(f"/api/documents/{doc_id}", json={"category": "nope"}, headers=CSRF)
    assert unknown.json()["error"]["code"] == "document_unknown_category"
    listed = core.get("/api/documents?category=utilities").json()
    assert [item["id"] for item in listed["items"]] == [doc_id]

    bulk = core.post(
        "/api/documents/bulk",
        json={"ids": [doc_id, "01JCMISSINGMISSINGMISSING0"], "patch": {"tags_add": ["car"]}},
        headers=CSRF,
    ).json()
    assert bulk == {"updated": 1, "skipped": ["01JCMISSINGMISSINGMISSING0"]}

    assert core.post(f"/api/documents/{doc_id}/trash", headers=CSRF).status_code == 204
    assert core.get("/api/documents").json()["items"] == []
    assert [row["id"] for row in core.get("/api/documents/trash").json()] == [doc_id]
    assert json.loads((folder / "meta.json").read_text())["deleted_at"]
    assert core.post(f"/api/documents/{doc_id}/restore", headers=CSRF).status_code == 204
    assert core.get("/api/documents").json()["total"] == 1
    assert kinds().count("document.trashed") == 1 and "document.restored" in kinds()


def test_unknown_upload_category_is_refused(core):
    refused = upload(core, category="nope")
    assert refused.json()["error"]["code"] == "document_unknown_category"


def test_rejected_uploads_leave_nothing_behind(core, monkeypatch):
    unsupported = upload(core, data=b"\x00\x01\x02\x03", name="blob.bin")
    assert unsupported.status_code == 415
    assert unsupported.json()["error"]["code"] == "unsupported_type"
    monkeypatch.setenv("DOCUHIVE_MAX_UPLOAD_MB", "1")
    from docuhive import config

    config.reload()
    large = upload(core, data=PDF + b"0" * (1024**2))
    assert large.status_code == 413
    assert not list((vault.root().parent / "staging" / "incoming").iterdir())
    with db.session() as session:
        assert session.scalar(select(Document.id)) is None


def test_vault_outage_defers_and_keeps_the_upload(core):
    doc_id = upload(core).json()["document_id"]
    (vault.root() / "_system" / "VAULT_ID").rename(vault.root() / "_system" / "VAULT_ID.off")
    vault._checked.clear()
    with pytest.raises(_Deferred, match="vault unavailable"):
        run(doc_id)
    assert status(doc_id) == "staged"
    assert (vault.root().parent / "staging" / doc_id / "input-0.pdf").read_bytes() == PDF
    (vault.root() / "_system" / "VAULT_ID.off").rename(vault.root() / "_system" / "VAULT_ID")
    run(doc_id)
    assert status(doc_id) == "stored"


def test_quarantine_keeps_input_and_retry_stores(core, monkeypatch):
    doc_id = upload(core).json()["document_id"]

    def encrypted(work, files):
        raise Quarantine("encrypted")

    monkeypatch.setattr(pipeline, "build", encrypted)
    run(doc_id)
    assert status(doc_id) == "quarantined"
    assert "document.quarantined" in kinds()
    assert core.get("/api/documents/pending").json()[0]["quarantine_reason"] == "encrypted"
    assert (vault.root().parent / "staging" / doc_id / "input-0.pdf").exists()

    monkeypatch.setattr(pipeline, "build", fake_build)
    assert core.post(f"/api/documents/{doc_id}/retry", headers=CSRF).status_code == 202
    assert status(doc_id) == "staged"
    assert core.post(f"/api/documents/{doc_id}/retry", headers=CSRF).status_code == 404
    run(doc_id)
    assert status(doc_id) == "stored"


def test_unexpected_errors_retry_then_quarantine(core, monkeypatch):
    from docuhive.jobs import RetryLater

    doc_id = upload(core).json()["document_id"]

    def broken(work, files):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(pipeline, "build", broken)
    with pytest.raises(RetryLater):
        run(doc_id, attempt=1)
    run(doc_id, attempt=pipeline.MAX_ATTEMPTS)
    assert status(doc_id) == "quarantined"


def test_crash_after_commit_finishes_without_storing_twice(core):
    doc_id = upload(core).json()["document_id"]
    staging = vault.root().parent / "staging" / doc_id
    run(doc_id)
    staging.mkdir()
    (staging / "hints.json").write_text(json.dumps({"doc_hint": "invoice"}))
    with db.session() as session:
        session.query(Job).filter(Job.kind == "document.stored").delete()
    run(doc_id)
    assert not staging.exists()
    with db.session() as session:
        payload = session.scalar(select(Job.payload).where(Job.kind == "document.stored"))
        stored = session.scalars(
            select(AuditLog.action).where(AuditLog.action == "ingest.stored")
        ).all()
    assert payload["hints"] == {"doc_hint": "invoice"} and len(stored) == 1


def test_photos_combine_into_one_document(core):
    pages = []
    for colour in ("white", "black"):
        image = io.BytesIO()
        Image.new("RGB", (8, 8), colour).save(image, format="PNG")
        pages.append(("files", (f"page-{colour}.png", image.getvalue())))
    response = core.post("/api/upload", files=pages, params={"combine": "true"}, headers=CSRF)
    assert response.status_code == 202, response.text
    doc_id = response.json()["document_id"]
    run(doc_id)
    folder = next(vault.root().glob(f"*/{doc_id}"))
    assert sorted(p.name for p in folder.glob("original*")) == [
        "original-0.png",
        "original-1.png",
        "original.pdf",
    ]
    assert health.scan(full=True).ok


def test_vault_init_refuses_a_foreign_folder_and_write_is_verified(core, tmp_path, monkeypatch):
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "holiday.jpg").write_bytes(b"synthetic")
    monkeypatch.setenv("DOCUHIVE_VAULT_DIR", str(foreign))
    from docuhive import config

    config.reload()
    with pytest.raises(ValueError, match="not empty"):
        vault.init()
    assert vault.check().reason == "not_initialised"
    target = tmp_path / "out" / "file.bin"
    assert vault.write_atomic(target, b"abc") == vault.sha256(target)
    assert [p.name for p in target.parent.iterdir()] == ["file.bin"]


def test_scanner_folder_is_picked_up_kept_until_stored_then_cleared(core):
    from docuhive.ingest import consume

    inbox = vault.root() / "consume" / "owner"
    inbox.mkdir(parents=True)
    (inbox / "scan.pdf").write_bytes(PDF)
    (inbox / "blob.bin").write_bytes(b"\x00\x01\x02\x03")
    ctx = JobContext(1, 1, logging.getLogger("t"))
    for _ in range(3):  # create the ledger, observe a stable file, then pick it up
        consume.poll({}, ctx)
    with db.session() as session:
        doc_id = session.scalar(select(Document.id))
    assert doc_id and (inbox / "scan.pdf").exists()
    rejected = list((vault.root() / "consume" / "_rejected").iterdir())
    assert any(p.name.endswith("blob.bin") for p in rejected)
    assert any(p.name.endswith(".reason.txt") for p in rejected)
    run(doc_id)
    consume.poll({}, ctx)
    assert not (inbox / "scan.pdf").exists()


def test_library_view_links_stored_documents(core):
    from docuhive.vault import library

    doc_id = upload(core, category="utilities/electricity").json()["document_id"]
    run(doc_id)
    assert library.sync() == {"ok": True, "links": 1}
    [linked] = (vault.root() / "library").rglob("*.pdf")
    archive = next(vault.root().glob(f"*/{doc_id}")) / "archive.pdf"
    assert linked.samefile(archive) and "utilities" in linked.parts
    core.post(f"/api/documents/{doc_id}/trash", headers=CSRF)
    assert library.sync() == {"ok": True, "links": 0}
    assert not list((vault.root() / "library").rglob("*.pdf"))
