"""Settings → Folders: folders DocuHive reads and analyses in place (administrators)."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from docuhive import folders
from docuhive.auth import require_admin
from docuhive.contracts import CurrentUser
from docuhive.db import session
from docuhive.db.models import Job, LinkedFile, LinkedFolder, User
from docuhive.vault import storage

router = APIRouter(prefix="/api/folders", tags=["folders"])
Admin = Annotated[CurrentUser, Depends(require_admin)]


class FolderIn(BaseModel):
    path: str = Field(min_length=1, description="Relative to the storage folder")
    label: str = Field(default="", max_length=80)
    shared: bool = False


class FolderOut(BaseModel):
    id: int
    label: str
    path: str  # as the host sees it
    owner: str
    shared: bool
    created_at: datetime
    last_scan_at: datetime | None
    last_error: str | None
    scanning: bool
    counts: dict[str, int]  # linked, duplicate, skipped, failed, missing


class FileOut(BaseModel):
    path: str
    state: str
    error: str | None
    document_id: str | None


def _shown(path: str) -> str:
    try:
        return storage.label(storage.storage_root() / path)
    except (storage.Refused, ValueError):
        return path


def _out(db, folder: LinkedFolder) -> FolderOut:  # type: ignore[no-untyped-def]
    counts = dict(
        db.execute(
            select(LinkedFile.state, func.count())
            .where(LinkedFile.folder_id == folder.id)
            .group_by(LinkedFile.state)
        ).all()
    )
    scanning = db.scalar(
        select(func.count()).where(
            Job.dedupe_key == f"folders.scan:{folder.id}", Job.status.in_(["pending", "running"])
        )
    )
    return FolderOut(
        id=folder.id,
        label=folder.label,
        path=_shown(folder.path),
        owner=db.get(User, folder.owner_id).username,
        shared=folder.shared,
        created_at=folder.created_at,
        last_scan_at=folder.last_scan_at,
        last_error=folder.last_error,
        scanning=bool(scanning),
        counts={k: int(v) for k, v in counts.items()},
    )


@router.get("", response_model=list[FolderOut])
def list_folders(user: Admin) -> list[FolderOut]:
    with session() as db:
        return [_out(db, f) for f in db.scalars(select(LinkedFolder).order_by(LinkedFolder.label))]


@router.post("", response_model=FolderOut, status_code=201)
def add_folder(body: FolderIn, user: Admin) -> FolderOut:
    try:
        folder_id = folders.add(user.id, body.path, body.label, body.shared)
    except folders.Refused as error:
        raise HTTPException(
            409, {"code": "refused", "message": str(error), "details": {}}
        ) from None
    with session() as db:
        made = db.get(LinkedFolder, folder_id)
        assert made is not None
        return _out(db, made)


def _folder(folder_id: int) -> None:
    with session() as db:
        if db.get(LinkedFolder, folder_id) is None:
            raise HTTPException(
                404, {"code": "not_found", "message": "No such folder", "details": {}}
            )


@router.post("/{folder_id}/scan", status_code=202)
def scan_now(folder_id: int, user: Admin) -> dict:
    _folder(folder_id)
    folders.queue_scan(folder_id)
    return {"queued": True}


@router.delete("/{folder_id}", status_code=204)
def stop_following(folder_id: int, user: Admin) -> None:
    """Its documents stay in the archive; their files stay where they are."""
    _folder(folder_id)
    folders.remove(folder_id)


@router.get("/{folder_id}/files", response_model=list[FileOut])
def files(
    folder_id: int,
    user: Admin,
    state: Literal["missing", "skipped", "failed", "linked", "duplicate"] = "failed",
    limit: int = 200,
) -> list[FileOut]:
    _folder(folder_id)
    with session() as db:
        rows = db.scalars(
            select(LinkedFile)
            .where(LinkedFile.folder_id == folder_id, LinkedFile.state == state)
            .order_by(LinkedFile.path)
            .limit(min(limit, 1000))
        )
        return [
            FileOut(path=r.path, state=r.state, error=r.error, document_id=r.document_id)
            for r in rows
        ]
