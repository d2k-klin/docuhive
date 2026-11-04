"""`ingest.process`: staged input → PDF → OCR → vault → `document.stored`.

Lossless and repeatable: the staged input is deleted only after the vault copy is written,
verified and committed; any failure keeps it and records a reason (quarantine). Every state
change commits together with the event it implies, so a crash never separates them.
"""

import shutil
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from docuhive import db, jobs, vault
from docuhive.config.settings import get_settings
from docuhive.db.models import AuditLog, DocSource, Document
from docuhive.documents import refresh_tsv
from docuhive.vault import meta

from . import inputs, saved_request, staging_dir
from .convert import combine, to_pdf
from .detect import detect
from .errors import Quarantine, Transient
from .ocr import ocr
from .safety import StepFailed, isolated
from .text import extract_text, page_count
from .thumbs import thumbnail

MAX_ATTEMPTS = 3
VAULT_RETRY = timedelta(minutes=2)
HEARTBEAT_S = 60


@dataclass
class Built:
    archive: Path
    thumb: Path
    combined: Path | None  # the pages as one PDF before OCR, for several photos
    content: str
    pages: int


@contextmanager
def keepalive(ctx: Any) -> Iterator[None]:
    """Renew the job's lease while a long step runs, so no other worker takes it over."""
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(HEARTBEAT_S):
            try:
                ctx.heartbeat()
            except Exception:  # a missed beat only shortens the lease
                pass

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=5)


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
    else:
        written = vault.combined_sha256(
            [
                vault.write_atomic(target / f"original-{index}{path.suffix}", path)
                for index, path in enumerate(files)
            ]
        )
        assert built.combined is not None
        vault.write_atomic(target / "original.pdf", built.combined)
    if written != sha:
        raise OSError("The staged original no longer matches its checksum")
    vault.write_atomic(target / "archive.pdf", built.archive)
    vault.write_atomic(target / "thumb.webp", built.thumb)
    return rel


def _source_kind(session: Session, doc_id: str) -> str | None:
    return session.scalar(select(DocSource.kind).where(DocSource.document_id == doc_id))


def _status(doc_id: str, status: str) -> None:
    with db.session() as session:
        session.get(Document, doc_id).status = status  # type: ignore[union-attr]


def quarantine(doc_id: str, reason: str) -> None:
    with db.session() as session:
        doc = session.get(Document, doc_id, with_for_update=True)
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
        payload = {
            "document_id": doc_id,
            "owner_id": doc.owner_id,
            "reason": reason,
            "source_kind": _source_kind(session, doc_id),
        }
        jobs.enqueue("document.quarantined", payload, queue="ai", in_session=session)


def retry(doc_id: str) -> bool:
    """Send a quarantined document through the pipeline again; its input was kept.

    Each retry is its own job: the attempt that quarantined the document may still be
    finishing, and must not absorb the new one.
    """
    with db.session() as session:
        doc = session.get(Document, doc_id, with_for_update=True)
        if doc is None or doc.status != "quarantined":
            return False
        doc.status, doc.quarantine_reason = "staged", None
        session.add(AuditLog(actor="system", document_id=doc_id, action="ingest.retry"))
        jobs.enqueue(
            "ingest.process",
            {"document_id": doc_id},
            queue="ocr",
            dedupe_key=f"ingest.process:{doc_id}:{uuid.uuid4().hex[:12]}",
            in_session=session,
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
        # A crash after the commit: the event was committed with it; only tidy up.
        meta.write_or_queue(doc_id)
        shutil.rmtree(work, ignore_errors=True)
        return
    health = vault.check()
    if not health.ok:
        ctx.defer(datetime.now(UTC) + VAULT_RETRY, f"vault unavailable: {health.reason}")
    files = inputs(work)
    if not files:
        quarantine(doc_id, "input_missing")
        return
    _status(doc_id, "processing")
    try:
        with keepalive(ctx):
            built = build(work, files)
            vault.require()
            rel = store(doc_id, sha, year, files, built)
    except Quarantine as error:
        quarantine(doc_id, str(error))
        return
    except (vault.VaultUnavailable, Transient) as error:
        # The NAS or the converter is away: wait without spending an attempt.
        _status(doc_id, "staged")
        ctx.defer(datetime.now(UTC) + VAULT_RETRY, f"waiting: {error}")
    except Exception as error:
        name = str(error) if isinstance(error, StepFailed) else type(error).__name__
        if ctx.attempt >= MAX_ATTEMPTS:
            quarantine(doc_id, f"processing_failed:{name}")
            return
        _status(doc_id, "staged")
        raise jobs.RetryLater(f"{name}: processing failed") from error
    with db.session() as session:
        doc = session.get(Document, doc_id, with_for_update=True)
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
        jobs.enqueue(
            "document.stored",
            {
                "document_id": doc_id,
                "owner_id": doc.owner_id,
                "source_kind": _source_kind(session, doc_id),
                "hints": saved_request(work).get("hints") or {},
            },
            queue="ai",
            dedupe_key=f"document.stored:{doc_id}",
            in_session=session,
        )
        meta.queue(session, doc_id)
    meta.write_or_queue(doc_id)
    shutil.rmtree(work, ignore_errors=True)
