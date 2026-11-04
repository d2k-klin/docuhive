"""`ingest.process`: staged input → PDF → OCR → vault → `document.stored`.

Lossless and repeatable: the staged input is deleted only after the vault copy is written,
verified and committed; any failure keeps it and records a reason (quarantine).
"""

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from docuhive import db, jobs, vault
from docuhive.config.settings import get_settings
from docuhive.db.models import AuditLog, DocSource, Document
from docuhive.documents import refresh_tsv
from docuhive.vault import meta

from . import HINTS, staging_dir
from .convert import combine, to_pdf
from .detect import detect
from .errors import Quarantine
from .ocr import ocr
from .safety import StepFailed, isolated
from .text import extract_text, page_count
from .thumbs import thumbnail

MAX_ATTEMPTS = 3
VAULT_RETRY = timedelta(minutes=2)


@dataclass
class Built:
    archive: Path
    thumb: Path
    combined: Path | None  # the pages as one PDF before OCR, for several photos
    content: str
    pages: int


def inputs(work: Path) -> list[Path]:
    return sorted(work.glob("input-*"), key=lambda p: int(p.name.split("-")[1].split(".")[0]))


def build(work: Path, files: list[Path]) -> Built:
    """Each step runs in its own process with a time limit; a hang or crash is a reason."""
    detected = [isolated(detect, path, timeout_s=30) for path in files]
    pdfs = [
        isolated(to_pdf, path, item, timeout_s=150)
        for path, item in zip(files, detected, strict=True)
    ]
    combined = None
    if len(pdfs) > 1:
        combined = isolated(combine, pdfs, work / "combined.pdf", timeout_s=60)
    archive = work / "archive.pdf"
    isolated(ocr, combined or pdfs[0], archive, get_settings().ocr_languages, timeout_s=1800)
    thumb = work / "thumb.webp"
    isolated(thumbnail, archive, thumb, timeout_s=60)
    return Built(
        archive=archive,
        thumb=thumb,
        combined=combined,
        content=isolated(extract_text, archive, timeout_s=60),
        pages=isolated(page_count, archive, timeout_s=30),
    )


def store(doc_id: str, sha: str, year: int, files: list[Path], built: Built) -> str:
    """Copy everything into the vault with verified atomic writes; returns the folder."""
    rel = vault.folder(doc_id, year)
    target = vault.root() / rel
    if len(files) == 1:
        written = vault.write_atomic(target / f"original{files[0].suffix}", files[0])
        if written != sha:
            raise OSError("The staged original no longer matches its checksum")
    else:
        for index, path in enumerate(files):
            vault.write_atomic(target / f"original-{index}{path.suffix}", path)
        assert built.combined is not None
        vault.write_atomic(target / "original.pdf", built.combined)
    vault.write_atomic(target / "archive.pdf", built.archive)
    vault.write_atomic(target / "thumb.webp", built.thumb)
    return rel


def hints_of(work: Path) -> dict:
    """Hints are kept next to the staged input, so a retry from quarantine still has them."""
    try:
        return json.loads((work / HINTS).read_text())
    except (OSError, ValueError):
        return {}


def finish(doc_id: str, work: Path) -> None:
    """After the commit: description, event, then the staged input may go."""
    meta.write_or_queue(doc_id)
    with db.session() as session:
        doc = session.get(Document, doc_id)
        assert doc is not None
        kind = session.scalar(select(DocSource.kind).where(DocSource.document_id == doc_id))
        payload = {"document_id": doc_id, "owner_id": doc.owner_id, "source_kind": kind}
    jobs.enqueue(
        "document.stored",
        payload | {"hints": hints_of(work)},
        queue="ai",
        dedupe_key=f"document.stored:{doc_id}",
    )
    shutil.rmtree(work, ignore_errors=True)


def quarantine(doc_id: str, reason: str) -> None:
    with db.session() as session:
        doc = session.get(Document, doc_id)
        assert doc is not None
        doc.status, doc.quarantine_reason = "quarantined", reason[:500]
        doc.updated_at = datetime.now(UTC)
        session.add(
            AuditLog(
                actor="system",
                document_id=doc_id,
                action="ingest.quarantined",
                after={"reason": reason[:500]},
            )
        )
        kind = session.scalar(select(DocSource.kind).where(DocSource.document_id == doc_id))
        payload = {
            "document_id": doc_id,
            "owner_id": doc.owner_id,
            "reason": reason,
            "source_kind": kind,
        }
    jobs.enqueue("document.quarantined", payload, queue="ai")


def retry(doc_id: str) -> bool:
    """Send a quarantined document through the pipeline again; its input was kept."""
    with db.session() as session:
        doc = session.get(Document, doc_id)
        if doc is None or doc.status != "quarantined":
            return False
        doc.status, doc.quarantine_reason = "staged", None
        session.add(AuditLog(actor="system", document_id=doc_id, action="ingest.retry"))
    jobs.enqueue(
        "ingest.process",
        {"document_id": doc_id},
        queue="ocr",
        dedupe_key=f"ingest.process:{doc_id}",
    )
    return True


@jobs.handler("ingest.process", queue="ocr", timeout_s=1800, max_attempts=MAX_ATTEMPTS)
def process(payload: dict, ctx: Any) -> None:
    doc_id = payload["document_id"]
    work = staging_dir() / doc_id
    with db.session() as session:
        doc = session.get(Document, doc_id)
        if doc is None or doc.status == "quarantined":
            return
        status, sha, year = doc.status, doc.sha256, doc.added_at.year
    if status == "stored":
        # A crash after the commit: finish the remaining steps, nothing is stored twice.
        if work.exists():
            finish(doc_id, work)
        return
    health = vault.check()
    if not health.ok:
        ctx.defer(datetime.now(UTC) + VAULT_RETRY, f"vault unavailable: {health.reason}")
    files = inputs(work)
    if not files:
        quarantine(doc_id, "input_missing")
        return
    with db.session() as session:
        session.get(Document, doc_id).status = "processing"  # type: ignore[union-attr]
    try:
        built = build(work, files)
        vault.require()
        rel = store(doc_id, sha, year, files, built)
    except Quarantine as error:
        quarantine(doc_id, str(error))
        return
    except vault.VaultUnavailable as error:
        with db.session() as session:
            session.get(Document, doc_id).status = "staged"  # type: ignore[union-attr]
        ctx.defer(datetime.now(UTC) + VAULT_RETRY, f"vault unavailable: {error}")
    except Exception as error:
        name = str(error) if isinstance(error, StepFailed) else type(error).__name__
        if ctx.attempt >= MAX_ATTEMPTS:
            quarantine(doc_id, f"processing_failed:{name}")
            return
        with db.session() as session:
            session.get(Document, doc_id).status = "staged"  # type: ignore[union-attr]
        raise jobs.RetryLater(f"{name}: processing failed") from error
    with db.session() as session:
        doc = session.get(Document, doc_id)
        assert doc is not None
        doc.status, doc.vault_path, doc.content = "stored", rel, built.content
        doc.pages, doc.quarantine_reason = built.pages, None
        doc.updated_at = datetime.now(UTC)
        session.add(
            AuditLog(
                actor="system",
                document_id=doc_id,
                action="ingest.stored",
                after={"vault_path": rel, "pages": built.pages},
            )
        )
        session.flush()
        refresh_tsv(session, doc_id)
    finish(doc_id, work)
