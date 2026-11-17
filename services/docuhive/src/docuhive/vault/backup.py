"""Backup options and evidence, shared with the host's backup job through the vault.

The backup runs on the host (it pauses the containers and holds the restic password). The app
writes what to back up and when to `_system/backup.json`, and a "back up now" request to
`_system/backup-request.json`; the job writes `_system/backup-status.json` back. Where backups go
and the password stay on the host: the app never sees them.
"""

import json
import re
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

from docuhive.vault import root, write_atomic

OPTIONS = "backup.json"
ERROR = re.compile(r"backup_[a-z]+_failed")
INCLUDED = re.compile(r"vault|database|staging|plugins|linked:\d{1,4}")
REQUEST = "backup-request.json"


class Keep(BaseModel):
    daily: int = Field(default=7, ge=1, le=365)
    weekly: int = Field(default=8, ge=0, le=520)
    monthly: int = Field(default=24, ge=0, le=240)
    dumps: int = Field(default=14, ge=1, le=365)  # database dumps inside the vault


class Include(BaseModel):
    staging: bool = True  # files still waiting to be read
    plugins: bool = True  # installed plugins and your own files in their custom/ folders
    linked_folders: bool = False  # files in linked folders (can be large)


class BackupOptions(BaseModel):
    time: str = "03:00"  # host time
    days: list[int] = Field(default=[0, 1, 2, 3, 4, 5, 6])  # Monday = 0
    keep: Keep = Keep()
    check_percent: int = Field(default=5, ge=0, le=100)  # verified on the 1st of the month
    include: Include = Include()
    # Written by the app from the linked folders, as the host sees them; read by the job.
    linked_paths: list[str] = []
    updated_at: datetime | None = None
    updated_by: str | None = None

    @field_validator("time")
    @classmethod
    def clock(cls, value: str) -> str:
        time.fromisoformat(value)  # raises for anything but HH:MM
        return value

    @field_validator("days")
    @classmethod
    def weekdays(cls, value: list[int]) -> list[int]:
        if not value or any(d not in range(7) for d in value):
            raise ValueError("choose at least one day, Monday = 0 … Sunday = 6")
        return sorted(set(value))


class BackupRequest(BaseModel):
    requested_at: datetime
    by: str


def _system() -> Path:
    return root() / "_system"


def options() -> BackupOptions:
    try:
        return BackupOptions.model_validate_json((_system() / OPTIONS).read_text())
    except (OSError, ValueError, ValidationError):
        return BackupOptions()


def save(chosen: BackupOptions, by: str) -> BackupOptions:
    saved = chosen.model_copy(
        update={
            "linked_paths": linked_paths() if chosen.include.linked_folders else [],
            "updated_at": datetime.now(UTC),
            "updated_by": by,
        }
    )
    write_atomic(_system() / OPTIONS, saved.model_dump_json(indent=2).encode())
    return saved


def refresh_linked() -> None:
    """Linked folders changed: keep the job's list of them current."""
    current = options()
    if current.include.linked_folders and (_system() / OPTIONS).is_file():
        save(current, current.updated_by or "system")


def linked_paths() -> list[str]:
    """Linked folders as the host sees them: the storage folder's host path + the rest."""
    from sqlalchemy import select

    from docuhive.config.settings import get_settings
    from docuhive.db import session
    from docuhive.db.models import LinkedFolder

    settings = get_settings()
    inside, host = settings.storage_root, settings.storage_root_label
    with session() as db:
        paths = [Path(p) for p in db.scalars(select(LinkedFolder.path))]
    out = []
    for path in paths:
        if inside and host and path.is_relative_to(inside):
            out.append(str(Path(host) / path.relative_to(inside)))
        else:
            out.append(str(path))  # no container in between: the same path
    return sorted(out)


def request(by: str) -> BackupRequest:
    made = BackupRequest(requested_at=datetime.now(UTC), by=by)
    write_atomic(_system() / REQUEST, made.model_dump_json().encode())
    return made


def pending() -> BackupRequest | None:
    try:
        return BackupRequest.model_validate_json((_system() / REQUEST).read_text())
    except (OSError, ValueError, ValidationError):
        return None


def next_run(chosen: BackupOptions, now: datetime | None = None) -> datetime:
    """The next scheduled start, in host time (the server's own timezone)."""
    now = (now or datetime.now(UTC)).astimezone()
    at = time.fromisoformat(chosen.time)
    for offset in range(8):
        day = (now + timedelta(days=offset)).date()
        start = datetime.combine(day, at, tzinfo=now.tzinfo)
        if day.weekday() in chosen.days and start > now:
            return start
    raise AssertionError("unreachable: at least one day is chosen")


class TargetResult(BaseModel):
    target: int  # 1, 2 … in the order of RESTIC_REPOSITORIES; addresses stay on the host
    ok: bool = False


class BackupStatus(BaseModel):
    at: datetime | None = None
    ok: bool = False
    last_success: datetime | None = None
    targets_ok: int = 0
    stale: bool = True
    targets: list[TargetResult] = []
    included: list[str] = []  # what the last run covered: vault, staging, plugins, linked:N
    running_since: datetime | None = None
    error: str | None = None  # a code such as backup_dump_failed, never a raw message


def allowed_age(chosen: BackupOptions) -> timedelta:
    """How old the last success may be before warning: the longest gap between scheduled
    days, plus a day for a slow or retried run (48 hours when it runs every day)."""
    days = sorted(chosen.days)
    gaps = [(b - a) % 7 or 7 for a, b in zip(days, days[1:] + days[:1], strict=True)]
    return timedelta(days=max(gaps) + 1)


def status() -> BackupStatus:
    path = root() / "_system" / "backup-status.json"
    try:
        value = json.loads(path.read_text())
        raw_targets = value.pop("targets", []) if isinstance(value, dict) else []
        # Only what is safe to show: a known error code, and per target whether it worked.
        code = value.get("error") if isinstance(value, dict) else None
        value["error"] = code if isinstance(code, str) and ERROR.fullmatch(code) else None
        value["included"] = [
            i for i in value.get("included") or [] if isinstance(i, str) and INCLUDED.fullmatch(i)
        ]
        result = BackupStatus.model_validate(value)
        result.targets = [
            TargetResult(target=index, ok=t.get("ok") is True)
            for index, t in enumerate(raw_targets, start=1)
            if isinstance(t, dict)
        ]
        if (
            result.at
            and result.at.tzinfo is None
            or result.last_success
            and result.last_success.tzinfo is None
        ):
            return BackupStatus()
        result.targets_ok = sum(t.ok for t in result.targets)
        now = datetime.now(UTC)
        result.stale = (
            result.last_success is None
            or not now - allowed_age(options()) <= result.last_success <= now
        )
        if result.running_since and now - result.running_since > timedelta(hours=12):
            result.running_since = None  # a job that died: not running any more
        return result
    except (OSError, ValueError, TypeError, AttributeError, ValidationError):
        return BackupStatus()
