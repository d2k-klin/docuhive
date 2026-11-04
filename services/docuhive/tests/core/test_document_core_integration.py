"""The real pipeline on PostgreSQL: Gotenberg conversion, Tesseract OCR, vault, search vector.

Synthetic files only. Needs `make test-integration` (PostgreSQL and Gotenberg) and Tesseract
with the German and English language data on the host.
"""

import json
import logging
import os
import shutil

import pikepdf
import pytest
from docuhive import config, db, documents, ingest, vault
from docuhive.auth import create_user
from docuhive.contracts import IngestRequest, MetadataPatch, SourceInfo, SourceKind
from docuhive.db.models import Document
from docuhive.ingest import process as pipeline
from docuhive.jobs import JobContext
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select, text

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract is not installed"),
]


@pytest.fixture
def owner(postgres, monkeypatch):
    monkeypatch.setenv(
        "DOCUHIVE_GOTENBERG_URL",
        os.environ.get("DOCUHIVE_TEST_GOTENBERG_URL", "http://127.0.0.1:53001"),
    )
    # Synthetic text is English; the host may lack German data (production images ship both).
    monkeypatch.setenv("DOCUHIVE_OCR_LANGUAGES", "eng")
    config.reload()
    vault._probed.clear()
    vault.init()
    return create_user("qa-core", "synthetic qa password 2026")


def ingest_file(owner: int, name: str, data: bytes) -> str:
    path = ingest.incoming_dir() / name
    path.write_bytes(data)
    result = ingest.submit(
        [path],
        IngestRequest(
            owner_id=owner, source=SourceInfo(kind=SourceKind.upload, original_filename=name)
        ),
    )
    pipeline.process({"document_id": result.document_id}, JobContext(1, 1, logging.getLogger("t")))
    return result.document_id


def row(doc_id: str) -> tuple[str, str | None, int | None]:
    with db.session() as session:
        doc = session.get(Document, doc_id)
        assert doc is not None
        return doc.status, doc.quarantine_reason, doc.pages


@pytest.mark.req("ING-01", "STO-01", "STO-02")
def test_text_file_is_converted_stored_and_searchable(owner):
    doc_id = ingest_file(owner, "synthetic-note.txt", b"Synthetic electricity invoice 84.20 EUR")
    assert row(doc_id) == ("stored", None, 1)
    assert "84.20 EUR" in documents.get_content(doc_id)
    folder = next(vault.root().glob(f"*/{doc_id}"))
    with pikepdf.open(folder / "archive.pdf") as pdf:
        assert len(pdf.pages) == 1
    assert (folder / "original.txt").read_bytes() == b"Synthetic electricity invoice 84.20 EUR"
    assert json.loads((folder / "meta.json").read_text())["title"] == "synthetic-note"

    documents.apply_metadata(
        doc_id, MetadataPatch(correspondent="Stadtwerke Muster"), actor="system"
    )
    with db.session() as session:
        hits = session.scalars(
            text(
                "SELECT id FROM documents WHERE content_tsv @@ "
                "to_tsquery('dh_simple', 'stadtwerke & electricity')"
            )
        ).all()
    assert hits == [doc_id]


@pytest.mark.req("ING-03")
def test_photo_is_read_by_ocr(owner, tmp_path):
    image = Image.new("RGB", (1600, 400), "white")
    font = ImageFont.load_default(size=96)
    ImageDraw.Draw(image).text((60, 140), "INVOICE 2026", fill="black", font=font)
    path = tmp_path / "scan.png"
    image.save(path, dpi=(300, 300))
    doc_id = ingest_file(owner, "scan.png", path.read_bytes())
    assert row(doc_id)[0] == "stored"
    assert "INVOICE" in documents.get_content(doc_id).upper()


@pytest.mark.req("ING-04")
def test_encrypted_pdf_is_quarantined_with_its_input_kept(owner, tmp_path):
    path = tmp_path / "locked.pdf"
    with pikepdf.new() as pdf:
        pdf.add_blank_page()
        pdf.save(path, encryption=pikepdf.Encryption(owner="synthetic", user="synthetic"))
    doc_id = ingest_file(owner, "locked.pdf", path.read_bytes())
    assert row(doc_id)[:2] == ("quarantined", "encrypted")
    assert (ingest.staging_dir() / doc_id / "input-0.pdf").exists()
    with db.session() as session:
        assert session.scalar(select(Document.vault_path).where(Document.id == doc_id)) is None
