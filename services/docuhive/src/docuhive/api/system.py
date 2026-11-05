"""Public health and protected platform operations."""

import asyncio
import json
import re
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from docuhive import __version__, vault
from docuhive.auth import current_user, require_admin
from docuhive.config.settings import get_settings
from docuhive.contracts import CurrentUser, SetupCheck
from docuhive.db import session
from docuhive.db.models import AuditLog, Document, Job
from docuhive.jobs import enqueue
from docuhive.vault import health as vault_health
from docuhive.vault import storage
from docuhive.vault.availability import available
from docuhive.vault.backup import BackupStatus
from docuhive.vault.backup import status as backup_status

router = APIRouter(prefix="/api/system", tags=["system"])
Admin = Annotated[CurrentUser, Depends(require_admin)]


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/jobs")
def jobs(
    user: Admin,
    status: Literal["pending", "running", "done", "dead"] | None = None,
    kind: str | None = None,
    queue: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: int | None = Query(default=None, ge=0),
) -> dict:
    query = select(Job).order_by(Job.id.desc()).limit(limit + 1)
    for column, value in ((Job.status, status), (Job.kind, kind), (Job.queue, queue)):
        if value is not None:
            query = query.where(column == value)
    if cursor is not None:
        query = query.where(Job.id < cursor)
    with session() as db:
        rows = list(db.scalars(query))
        # Payloads and raw errors can contain private document data and are not exposed here.
        items = [
            {
                "id": j.id,
                "kind": j.kind,
                "queue": j.queue,
                "status": j.status,
                "attempts": j.attempts,
                "max_attempts": j.max_attempts,
                "run_after": j.run_after,
                "note": j.note,
                "last_error": "Processing failed; see server logs." if j.last_error else None,
            }
            for j in rows[:limit]
        ]
        return {
            "items": items,
            "next_cursor": str(rows[limit - 1].id) if len(rows) > limit else None,
        }


@router.post("/jobs/{job_id}/retry", status_code=204)
def retry(job_id: int, user: Admin) -> None:
    from datetime import UTC, datetime

    with session() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if not job:
            raise HTTPException(404, "Job not found")
        if job.status != "dead":
            raise HTTPException(409, "Only failed jobs can be retried")
        if job.dedupe_key:
            active = db.scalar(
                select(Job.id).where(
                    Job.dedupe_key == job.dedupe_key, Job.status.in_(["pending", "running"])
                )
            )
            if active:
                raise HTTPException(409, "An active job already has this deduplication key")
        job.status, job.attempts, job.run_after = "pending", 0, datetime.now(UTC)
        job.locked_at, job.locked_by, job.finished_at, job.last_error = None, None, None, None


@router.get("/sse-test")
async def sse_test(user: Admin) -> StreamingResponse:
    async def ticks() -> AsyncIterator[str]:
        for tick in range(10):
            await asyncio.sleep(0.5)
            yield f"event: tick\ndata: {json.dumps({'tick': tick})}\n\n"

    return StreamingResponse(
        ticks(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/vault/health", response_model=vault_health.VaultReport | None)
def vault_report(user: Admin) -> vault_health.VaultReport | None:
    return vault_health.last()


@router.post("/vault/health", status_code=202)
def queue_vault_check(user: Admin, full: bool = False) -> dict:
    enqueue("vault.check", {"full": full}, dedupe_key="vault.check:manual")
    return {"queued": True}


class StorageInfo(BaseModel):
    location: str
    vault_id: str | None
    available: bool
    reason: str | None  # not_initialised | id_mismatch | not_writable
    kind: Literal["network", "local"] | None  # None: not certain (Docker Desktop, macOS)
    documents: int
    waiting: int  # accepted uploads still in local staging
    staging_location: str
    choosable: bool  # a storage root is mounted, so admins can choose the vault folder
    free_bytes: int | None
    total_bytes: int | None


NETWORK_FS = {"nfs", "nfs4", "cifs", "smb3", "smbfs", "afpfs"}
# Only what is certain: Docker Desktop shows every host folder as fuse.sshfs, NAS or not.
LOCAL_FS = {"ext4", "ext3", "xfs", "btrfs", "zfs", "f2fs", "apfs", "vfat", "exfat", "ntfs3"}


def storage_kind(path: Path, mountinfo: str | None = None) -> Literal["network", "local"] | None:
    """Network share or local disk, from the mount holding `path` (Linux only)."""
    try:
        table = Path("/proc/self/mountinfo").read_text() if mountinfo is None else mountinfo
        lines = table.splitlines()
    except OSError:
        return None
    target, best, fstype = str(path), "", ""
    for line in lines:
        fields = line.split()
        # mountinfo escapes spaces and the like as octal: /mnt/NAS\040Archive
        mount = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields[4])
        inside = target == mount or target.startswith(mount.rstrip("/") + "/")
        if inside and len(mount) >= len(best):
            best, fstype = mount, fields[fields.index("-") + 1]
    if not best:
        return None
    if fstype in NETWORK_FS:
        return "network"
    return "local" if fstype in LOCAL_FS else None


@router.get("/storage", response_model=StorageInfo)
def storage_info(user: Admin) -> StorageInfo:
    """Which storage DocuHive uses: the vault's location, identity, size and free space."""
    settings = get_settings()
    root = vault.root()
    try:
        vault_id: str | None = (root / "_system" / "VAULT_ID").read_text().strip()
    except OSError:
        vault_id = None
    free: int | None = None
    total: int | None = None
    try:
        usage = shutil.disk_usage(root)
        free, total = usage.free, usage.total
    except OSError:
        pass
    status = vault.check()
    with session() as db:
        count = db.scalar(
            select(func.count()).select_from(Document).where(Document.deleted_at.is_(None))
        )
        waiting = db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.status.in_(["staged", "processing"]))
        )
    location = settings.vault_label or str(root)
    if root != settings.vault_dir:  # chosen on this page, inside the storage root
        try:
            location = storage.label(root.resolve())
        except (storage.Refused, ValueError):
            location = str(root)
    return StorageInfo(
        location=location,
        vault_id=vault_id,
        available=status.ok,
        reason=status.reason,
        kind=storage_kind(root.resolve()),  # a relative path or symlink: match the real one
        documents=count or 0,
        waiting=waiting or 0,
        staging_location=settings.staging_label or str(settings.staging_dir),
        free_bytes=free,
        total_bytes=total,
        choosable=settings.storage_root is not None and settings.storage_root.is_dir(),
    )


def _refused(error: storage.Refused) -> HTTPException:
    status = 404 if error.code == "not_found" else 409
    return HTTPException(status, detail={"code": error.code, "message": str(error), "details": {}})


@router.get("/storage/folders", response_model=storage.Listing)
def storage_folders(user: Admin, path: str = "") -> storage.Listing:
    """Folders inside the storage root, each with what choosing it would do."""
    try:
        return storage.listing(path)
    except storage.Refused as error:
        raise _refused(error) from None


class NewFolder(BaseModel):
    path: str = ""
    name: str


@router.post("/storage/folders", response_model=storage.Folder, status_code=201)
def storage_new_folder(user: Admin, body: NewFolder) -> storage.Folder:
    try:
        return storage.create(body.path, body.name)
    except storage.Refused as error:
        raise _refused(error) from None


class ChooseStorage(BaseModel):
    path: str


@router.post("/storage/choose", response_model=StorageInfo)
def storage_choose(user: Admin, body: ChooseStorage) -> StorageInfo:
    """Make a folder inside the storage root the vault (only the safe cases, see vault.storage)."""
    try:
        storage.choose(body.path)
    except storage.Refused as error:
        raise _refused(error) from None
    with session() as db:
        db.add(
            AuditLog(
                actor=f"user:{user.id}", action="vault.storage_chosen", after={"path": body.path}
            )
        )
    return storage_info(user)


@router.get("/backup", response_model=BackupStatus)
def backup_report(user: Admin) -> BackupStatus:
    return backup_status()


@router.get("/setup-status", response_model=list[SetupCheck])
def setup_status(user: Annotated[CurrentUser, Depends(current_user)]) -> list[SetupCheck]:
    settings = get_settings()
    vault_ok = available()
    backup = backup_status()
    consume = settings.consume_dir or vault.root() / "consume"
    https = settings.public_url.startswith("https://")
    return [
        SetupCheck(
            id="vault",
            area="storage",
            title="Connect your storage",
            required=True,
            status="ok" if vault_ok else "error",
            message="Your archive storage is connected."
            if vault_ok
            else "Storage is unavailable. New uploads stay in staging until it returns.",
            action_label="Check storage",
            action_href="/settings/storage",
            help_doc="docs/setup/nas-wd-ex2-ultra.md",
        ),
        SetupCheck(
            id="backup",
            area="backup",
            title="Back up your archive",
            status="ok" if backup.ok and not backup.stale else "warn",
            message="Your latest backup completed."
            if backup.ok and not backup.stale
            else (
                "No recent successful backup was confirmed. "
                "Check the backup timer and run a backup."
            ),
            action_label="Check backups",
            action_href="/settings/storage",
            help_doc="docs/setup/operations.md",
        ),
        SetupCheck(
            id="capture.https",
            area="capture",
            title="Set up phone capture",
            status="ok" if https else "warn",
            message="Your configured phone address uses HTTPS."
            if https
            else "Use an HTTPS address to install capture on your phone and save captures offline.",
            action_label="Open capture",
            action_href="/capture",
            help_doc="docs/setup/remote-access.md",
        ),
        SetupCheck(
            id="capture.consume",
            area="capture",
            title="Connect a scanner folder",
            status="ok" if vault_ok and consume.is_dir() else "optional",
            message="The scanner folder is available."
            if vault_ok and consume.is_dir()
            else "You can add a scanner folder when you need one.",
            action_label="Capture guide",
            action_href="/capture",
            help_doc="docs/setup/mobile.md",
        ),
    ]
