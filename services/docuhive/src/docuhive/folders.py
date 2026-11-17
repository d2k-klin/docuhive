"""Linked folders: DocuHive reads and analyses the files where they are, never moving them.

An administrator links a folder inside the storage folder (a NAS share with years of documents,
say). Every few minutes each linked folder is walked: a new or changed file is copied to staging
and goes through the same pipeline as an upload, but the vault only gets DocuHive's searchable
copy, thumbnail and `meta.json`, plus `linked.json` naming the file. The original never moves.
A file that disappears is marked missing; its searchable copy stays.
"""

import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from docuhive import ingest, jobs, vault
from docuhive.config.settings import get_settings
from docuhive.contracts import IngestRequest, SourceInfo, SourceKind
from docuhive.db import session
from docuhive.db.models import LinkedFile, LinkedFolder, User
from docuhive.ingest.consume import ignored, verified_copy
from docuhive.vault import storage

SCAN_EVERY = timedelta(minutes=10)
SETTLE = timedelta(minutes=1)  # a file still being written waits for the next scan
SKIP_DIRS = ("@eaDir", "#recycle", "#snapshot", "$RECYCLE.BIN", "System Volume Information")
KEEP = ("linked", "duplicate", "skipped", "failed")


class Refused(ValueError):
    """Said to the person as it is."""


def add(owner_id: int, relative: str, label: str, shared: bool) -> int:
    """Link a folder inside the storage folder; its first scan starts right away."""
    try:
        target = storage._inside(relative)
    except storage.Refused as error:
        raise Refused(str(error)) from None
    if not target.is_dir():
        raise Refused("That folder does not exist.")
    archive = vault.root().resolve()
    if target == archive or target.is_relative_to(archive) or archive.is_relative_to(target):
        raise Refused("That is DocuHive's own vault, or holds it. Choose a folder of your files.")
    with session() as db:
        for other in db.scalars(select(LinkedFolder.path)):
            path = Path(other)
            if path == target or path.is_relative_to(target) or target.is_relative_to(path):
                raise Refused(f"It overlaps a folder already linked: {storage.label(path)}")
        folder = LinkedFolder(
            owner_id=owner_id,
            path=str(target),
            label=label.strip()[:80] or target.name,
            shared=shared,
            created_at=datetime.now(UTC),
        )
        db.add(folder)
        db.flush()
        folder_id = folder.id
    queue_scan(folder_id)
    return folder_id


def remove(folder_id: int) -> None:
    """Stop following a folder. Its documents stay in the archive, pointing at their files."""
    with session() as db:
        db.execute(delete(LinkedFolder).where(LinkedFolder.id == folder_id))


def queue_scan(folder_id: int) -> None:
    jobs.enqueue(
        "folders.scan",
        {"folder_id": folder_id},
        queue="ocr",
        dedupe_key=f"folders.scan:{folder_id}",
    )


@jobs.periodic("folders.scan_all", every=SCAN_EVERY, queue="ocr")
def scan_all(payload: dict, ctx: Any) -> None:
    with session() as db:
        ids = list(db.scalars(select(LinkedFolder.id)))
    for folder_id in ids:
        queue_scan(folder_id)


@jobs.handler("folders.scan", queue="ocr", timeout_s=3600)
def scan(payload: dict, ctx: Any) -> None:
    with session() as db:
        folder = db.get(LinkedFolder, payload["folder_id"])
        if folder is None:
            return
        root, folder_id = Path(folder.path), folder.id
        owner = db.get(User, folder.owner_id)
        label, shared, owner_id = folder.label, folder.shared, folder.owner_id
        known = {
            f.path: f
            for f in db.scalars(select(LinkedFile).where(LinkedFile.folder_id == folder_id))
        }
        for each in known.values():
            db.expunge(each)
    if owner is None or not root.is_dir():
        _finish(folder_id, "The folder cannot be reached. Is the share mounted?")
        return
    seen: set[str] = set()
    now = datetime.now(UTC)
    for directory, subdirs, names in os.walk(root, followlinks=False):
        subdirs[:] = [d for d in subdirs if not d.startswith(".") and d not in SKIP_DIRS]
        for name in names:
            path = Path(directory) / name
            if ignored(path) or path.is_symlink() or not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            seen.add(rel)
            stat = path.stat()
            row = known.get(rel)
            if row and (row.size, row.mtime_ns) == (stat.st_size, stat.st_mtime_ns):
                if row.state == "missing":  # back where it was
                    _save(
                        folder_id,
                        rel,
                        stat,
                        "linked" if row.document_id else "failed",
                        row.document_id,
                        row.error,
                    )
                continue
            if now - datetime.fromtimestamp(stat.st_mtime, UTC) < SETTLE:
                continue
            _ingest(folder_id, label, shared, owner_id, root, path, rel, stat, row)
            ctx.heartbeat()
    with session() as db:
        for row in db.scalars(
            select(LinkedFile).where(LinkedFile.folder_id == folder_id, LinkedFile.state.in_(KEEP))
        ):
            if row.path not in seen:
                row.state, row.seen_at = "missing", now
    _finish(folder_id, None)


def _ingest(
    folder_id: int,
    label: str,
    shared: bool,
    owner_id: int,
    root: Path,
    path: Path,
    rel: str,
    stat: os.stat_result,
    row: LinkedFile | None,
) -> None:
    if stat.st_size > get_settings().max_upload_mb * 1024 * 1024:
        _save(folder_id, rel, stat, "skipped", None, "Larger than the upload limit")
        return
    fd, name = tempfile.mkstemp(dir=ingest.incoming_dir(), suffix=path.suffix[:16])
    os.close(fd)
    copy = Path(name)
    try:
        verified_copy(path, copy)
        result = ingest.submit(
            [copy],
            IngestRequest(
                owner_id=owner_id,
                shared=shared,
                source=SourceInfo(
                    kind=SourceKind.folder,
                    original_filename=path.name,
                    folder=label,
                    path=rel,
                    file_modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
                ),
                hints={"linked_file": str(path)},
            ),
        )
    except ingest.IngestRejected as error:
        _save(folder_id, rel, stat, "skipped", None, str(error) or "Not a file DocuHive reads")
        return
    except OSError as error:  # changed while copying, or unreadable: the next scan tries again
        if row is None:
            _save(folder_id, rel, stat, "failed", None, f"Could not be read: {error.strerror}")
        return
    finally:
        copy.unlink(missing_ok=True)
    same = row is not None and row.document_id == result.document_id
    state = "linked" if result.status == "staged" or same else "duplicate"
    _save(folder_id, rel, stat, state, result.document_id, None)


def _save(
    folder_id: int,
    rel: str,
    stat: os.stat_result,
    state: str,
    document_id: str | None,
    error: str | None,
) -> None:
    from sqlalchemy.dialects.postgresql import insert

    values = {
        "folder_id": folder_id,
        "path": rel,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "state": state,
        "document_id": document_id,
        "error": error,
        "seen_at": datetime.now(UTC),
    }
    statement = insert(LinkedFile).values(**values)
    with session() as db:
        db.execute(
            statement.on_conflict_do_update(
                index_elements=[LinkedFile.folder_id, LinkedFile.path],
                set_={k: statement.excluded[k] for k in values if k not in ("folder_id", "path")},
            )
        )


def _finish(folder_id: int, error: str | None) -> None:
    with session() as db:
        folder = db.get(LinkedFolder, folder_id)
        if folder is not None:
            folder.last_scan_at, folder.last_error = datetime.now(UTC), error
