"""Read backup evidence without exposing repository addresses or raw errors."""

import json
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ValidationError

from docuhive.vault import root


class BackupStatus(BaseModel):
    at: datetime | None = None
    ok: bool = False
    last_success: datetime | None = None
    targets_ok: int = 0
    stale: bool = True


def status() -> BackupStatus:
    path = root() / "_system" / "backup-status.json"
    try:
        value = json.loads(path.read_text())
        result = BackupStatus.model_validate(value)
        if (
            result.at
            and result.at.tzinfo is None
            or result.last_success
            and result.last_success.tzinfo is None
        ):
            return BackupStatus()
        result.targets_ok = sum(target.get("ok") is True for target in value.get("targets", []))
        now = datetime.now(UTC)
        result.stale = (
            result.last_success is None
            or not now - timedelta(hours=48) <= result.last_success <= now
        )
        return result
    except (OSError, ValueError, TypeError, AttributeError, ValidationError):
        return BackupStatus()
