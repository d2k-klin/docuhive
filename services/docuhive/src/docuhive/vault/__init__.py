"""The vault on the user's storage: layout, availability and verified atomic writes."""

import hashlib
import os
import time
import uuid
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import select

from docuhive import db
from docuhive.config.settings import get_settings
from docuhive.db.models import Setting

FORMAT = "1"
ID_KEY = "vault.id"
CHECK_TTL_S = 30


class VaultUnavailable(Exception):
    pass


class VaultStatus(BaseModel):
    ok: bool
    reason: str | None = None  # not_initialised | id_mismatch | not_writable


def root() -> Path:
    return get_settings().vault_dir


def init() -> str:
    """Create `_system/` with a new vault id; refuse a non-empty folder that is not a vault."""
    vault = root()
    system = vault / "_system"
    if (system / "VAULT_ID").is_file():
        vault_id = (system / "VAULT_ID").read_text().strip()
    else:
        if vault.is_dir() and any(vault.iterdir()) and not system.is_dir():
            raise ValueError("The vault folder is not empty and is not a DocuHive vault")
        system.mkdir(parents=True, exist_ok=True)
        vault_id = str(uuid.uuid4())
        write_atomic(system / "VAULT_ID", vault_id.encode())
        write_atomic(system / "FORMAT", FORMAT.encode())
    for name in ("consume", "library"):
        (vault / name).mkdir(exist_ok=True)
    from .meta import json_schema

    # Documents the format for anyone reading the vault without DocuHive.
    write_atomic(vault / "meta.schema.json", json_schema())
    with db.session() as session:
        session.merge(Setting(key=ID_KEY, value=vault_id))
    _checked.clear()
    return vault_id


_checked: dict[Path, float] = {}


def check() -> VaultStatus:
    """The vault is mounted, is the one this database belongs to, and accepts writes.

    Only a healthy result is cached (30 s), so an outage is noticed on the next call.
    """
    vault = root()
    if time.monotonic() - _checked.get(vault, -CHECK_TTL_S) < CHECK_TTL_S:
        return VaultStatus(ok=True)
    marker = vault / "_system" / "VAULT_ID"
    try:
        found = marker.read_text().strip()
    except OSError:
        return VaultStatus(ok=False, reason="not_initialised")
    with db.session() as session:
        expected = session.scalar(select(Setting.value).where(Setting.key == ID_KEY))
    if expected != found:
        return VaultStatus(ok=False, reason="id_mismatch")
    try:
        write_atomic(vault / "_system" / ".probe", str(time.time()).encode())
    except OSError:
        return VaultStatus(ok=False, reason="not_writable")
    _checked[vault] = time.monotonic()
    return VaultStatus(ok=True)


def require() -> None:
    status = check()
    if not status.ok:
        raise VaultUnavailable(status.reason)


def folder(doc_id: str, year: int) -> str:
    """Relative folder of a document; the year is `added_at`'s, so it never moves."""
    return f"{year:04d}/{doc_id}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_atomic(path: Path, data: bytes | Path) -> str:
    """Write next to `path`, fsync, rename over it, then re-read to verify. Returns the sha256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
    digest = hashlib.sha256()
    try:
        with tmp.open("wb") as out:
            if isinstance(data, Path):
                with data.open("rb") as source:
                    for block in iter(lambda: source.read(1 << 20), b""):
                        digest.update(block)
                        out.write(block)
            else:
                digest.update(data)
                out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    try:
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        pass  # SMB and some NAS mounts refuse a directory fsync
    expected = digest.hexdigest()
    if sha256(path) != expected:
        raise OSError(f"Verification failed after writing {path.name}")
    return expected
