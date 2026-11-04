"""The single entry point for every document source: validate, dedupe, stage, queue.

`submit` takes ownership of the files. Processing (conversion, OCR, the vault write) runs
later in the `ingest.process` job, so a slow or unavailable NAS never blocks a source.
"""

import json
import re
import shutil
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ulid import ULID

from docuhive import db, jobs
from docuhive.config.settings import get_settings
from docuhive.contracts import IngestRequest, IngestResult
from docuhive.db.models import DocSource, Document
from docuhive.vault import combined_sha256, sha256

from .detect import detect
from .errors import Quarantine

REQUEST = "request.json"
INPUT = re.compile(r"^input-(\d+)\.[a-z0-9]+$")
ULID_NAME = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
ORPHAN_AFTER = timedelta(minutes=15)


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
    digest = combined_sha256(digests) if len(files) > 1 else digests[0]

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
    moved: list[tuple[Path, Path]] = []
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
            jobs.enqueue(
                "ingest.process",
                {"document_id": doc_id, "combine": req.combine, "hints": req.hints},
                queue="ocr",
                dedupe_key=f"ingest.process:{doc_id}",
                in_session=session,
            )
            folder.mkdir(parents=True)
            # Enough to submit again if the process dies before the commit (see `reconcile`).
            (folder / REQUEST).write_text(req.model_dump_json())
            for index, (path, item) in enumerate(zip(files, detected, strict=True)):
                target = folder / f"input-{index}.{item.ext}"
                shutil.move(path, target)
                moved.append((path, target))
    except BaseException as error:
        # Nothing committed: the caller still owns its files, exactly where they were.
        for source, target in reversed(moved):
            shutil.move(target, source)
        shutil.rmtree(folder, ignore_errors=True)
        if isinstance(error, IntegrityError) and (found := duplicate()):
            return found
        raise
    return IngestResult(document_id=doc_id, status="staged")


def saved_request(folder: Path) -> dict:
    try:
        data = json.loads((folder / REQUEST).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def inputs(folder: Path) -> list[Path]:
    """The staged files in page order; never conversion outputs or temp files."""
    numbered = []
    for path in folder.glob("input-*"):
        if match := INPUT.match(path.name):
            numbered.append((int(match.group(1)), path))
    return [path for _, path in sorted(numbered)]


@jobs.periodic("ingest.reconcile", every=timedelta(hours=1), queue="ocr")
def reconcile(payload: dict, ctx: Any) -> None:
    """A staged folder without a document is a submit that died before its commit: submit
    its files again (dedupe makes that safe), or park the folder in `_orphaned` for a person.
    """
    root = staging_dir()
    if not root.is_dir():
        return
    for folder in sorted(root.iterdir()):
        young = time.time() - folder.stat().st_mtime < ORPHAN_AFTER.total_seconds()
        if not folder.is_dir() or not ULID_NAME.match(folder.name) or young:
            continue
        with db.session() as session:
            if session.get(Document, folder.name) is not None:
                continue
        files = inputs(folder)
        try:
            request = IngestRequest.model_validate(saved_request(folder))
        except ValueError:
            request = None
        if request is None or not files:
            parked = root / "_orphaned"
            parked.mkdir(exist_ok=True)
            shutil.move(folder, parked / folder.name)
            ctx.log.warning("Parked an incomplete staging folder in _orphaned")
            continue
        recovered = []
        for path in files:
            target = incoming_dir() / f"recovered-{uuid.uuid4().hex}{path.suffix}"
            shutil.move(path, target)
            recovered.append(target)
        try:
            submit(recovered, request)
        except IngestRejected:
            for source, path in zip(files, recovered, strict=True):
                shutil.move(path, source)
            parked = root / "_orphaned"
            parked.mkdir(exist_ok=True)
            shutil.move(folder, parked / folder.name)
            continue
        shutil.rmtree(folder, ignore_errors=True)
