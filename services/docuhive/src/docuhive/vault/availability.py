"""Fail closed before operations on a NAS mount; never create the mount point."""

from sqlalchemy import select

from docuhive.config.settings import get_settings
from docuhive.db import session
from docuhive.db.models import Setting


def available() -> bool:
    try:
        found = (get_settings().vault_dir / "_system" / "VAULT_ID").read_text().strip()
    except OSError:
        return False
    with session() as db:
        expected = db.scalar(select(Setting.value).where(Setting.key == "vault.id"))
    return bool(found) and found == expected
