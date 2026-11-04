"""The single entry point for every document source: validate, dedupe, stage, queue.

`submit` takes ownership of the files. Processing (conversion, OCR, the vault write) runs
later in the `ingest.process` job, so a slow or unavailable NAS never blocks a source.
"""

import hashlib
import json
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ulid import ULID

from docuhive import db, jobs
from docuhive.config.settings import get_settings
from docuhive.contracts import IngestRequest, IngestResult
from docuhive.db.models import DocSource, Document
from docuhive.vault import sha256

from .detect import detect
from .errors import Quarantine

HINTS = "hints.json"


class IngestRejected(Exception):
    pass


class UnsupportedType(IngestRejected):
    pass


class TooLarge(IngestRejected):
    pass


def staging_dir() -> Path:
    return get_settings().staging_dir


def incoming_dir() -> Path:
    path = staging_dir() / "incoming"
    path.mkdir(parents=True, exist_ok=True)
    return path


def submit(files: list[Path], req: IngestRequest) -> IngestResult:
    if not files or (len(files) > 1 and not req.combine):
        raise UnsupportedType("Multiple files require combine=True")
    if sum(path.stat().st_size for path in files) > get_settings().max_upload_mb * 1024**2:
        raise TooLarge("Upload exceeds the configured limit")
    try:
        detected = [detect(path) for path in files]
    except Quarantine as error:
        raise UnsupportedType(str(error)) from error
    if len(files) > 1 and any(item.kind != "image" for item in detected):
        raise UnsupportedType("Only images can be combined")
    digests = [sha256(path) for path in files]
    # Several pages are identified by the hash of their hashes, in order (vault health agrees).
    digest = hashlib.sha256("".join(digests).encode()).hexdigest() if len(files) > 1 else digests[0]

    def duplicate() -> IngestResult | None:
        with db.session() as session:
            existing = session.scalar(
                select(Document.id).where(
                    Document.owner_id == req.owner_id, Document.sha256 == digest
                )
            )
        if existing is None:
            return None
        for path in files:
            path.unlink(missing_ok=True)
        return IngestResult(document_id=existing, status="duplicate")

    if found := duplicate():
        return found
    doc_id = str(ULID())
    folder = staging_dir() / doc_id
    try:
        with db.session() as session:
            session.add(
                Document(
                    id=doc_id,
                    owner_id=req.owner_id,
                    shared=req.shared,
                    status="staged",
                    sha256=digest,
                    mime=detected[0].mime if len(files) == 1 else "application/pdf",
                    title=Path(req.source.original_filename).stem[:120] or None,
                    manual_fields=[],
                    fts_config="dh_simple",  # the AI sets the language later
                )
            )
            session.flush()  # the unique (owner, sha256) constraint settles a race here
            session.add(DocSource(document_id=doc_id, **req.source.model_dump(exclude_none=True)))
            session.flush()
            folder.mkdir(parents=True)
            if req.hints:
                (folder / HINTS).write_text(json.dumps(req.hints))
            for index, (path, item) in enumerate(zip(files, detected, strict=True)):
                shutil.move(path, folder / f"input-{index}.{item.ext}")
    except IntegrityError:
        if found := duplicate():
            return found
        raise
    jobs.enqueue(
        "ingest.process",
        {"document_id": doc_id, "combine": req.combine, "hints": req.hints},
        queue="ocr",
        dedupe_key=f"ingest.process:{doc_id}",
    )
    return IngestResult(document_id=doc_id, status="staged")
