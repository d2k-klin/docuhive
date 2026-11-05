"""The vault on the user's storage: layout, availability and verified atomic writes."""

import hashlib
import os
import re
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
# Canonical names only: a killed atomic write leaves `<name>.tmp-<uuid>` behind.
ORIGINAL = re.compile(r"^original\.[a-z0-9]+$")
PAGE = re.compile(r"^original-(\d+)\.[a-z0-9]+$")


class VaultUnavailable(Exception):
    pass


class VaultStatus(BaseModel):
    ok: bool
    reason: str | None = None  # not_initialised | id_mismatch | not_writable


PATH_KEY = "vault.path"
CHOSEN_TTL_S = 10
_chosen: tuple[float, Path | None] = (float("-inf"), None)


def root() -> Path:
    """The vault folder: the one chosen on Storage health, else DOCUHIVE_VAULT_DIR.

    Read from the database at most every 10 s per process. A worker still holding the old
    folder cannot write there: every write first checks the vault ID the database is bound to.
    """
    global _chosen
    at, chosen = _chosen
    if time.monotonic() - at >= CHOSEN_TTL_S:
        with db.session() as session:
            value = session.scalar(select(Setting.value).where(Setting.key == PATH_KEY))
        chosen = Path(value) if value else None
        _chosen = (time.monotonic(), chosen)
    return chosen or get_settings().vault_dir


def forget_chosen() -> None:
    global _chosen
    _chosen = (float("-inf"), None)


SKELETON = {"_system", "consume", "library"}


def _bound_id() -> str | None:
    with db.session() as session:
        return session.scalar(select(Setting.value).where(Setting.key == ID_KEY))


def _is_empty_skeleton(vault: Path) -> bool:
    """Nothing but empty `_system`, `consume` and `library` folders (a fresh mount point)."""
    return all(
        entry.name in SKELETON and entry.is_dir() and not any(entry.iterdir())
        for entry in vault.iterdir()
    )


def init() -> str:
    """Create a new vault, or bind a fresh database to an existing one.

    Refuses a folder holding anything else, and refuses to move a database that already
    belongs to another vault: an empty mount point for an absent NAS must never become a
    replacement vault.
    """
    vault = root()
    marker = vault / "_system" / "VAULT_ID"
    bound = _bound_id()
    if marker.is_file():
        vault_id = marker.read_text().strip()
        if bound and bound != vault_id:
            raise ValueError(
                "This folder is a different vault from the one this database belongs to; "
                "mount the right vault, or restore with `docuhive vault rebuild` on a new database"
            )
    else:
        if bound:
            raise ValueError(
                "This database belongs to a vault that is not mounted here; mount it and retry"
            )
        if vault.is_dir() and not _is_empty_skeleton(vault):
            raise ValueError("The vault folder is not empty and is not a DocuHive vault")
        (vault / "_system").mkdir(parents=True, exist_ok=True)
        vault_id = str(uuid.uuid4())
        write_atomic(vault / "_system" / "FORMAT", FORMAT.encode())
        write_atomic(marker, vault_id.encode())
    for name in ("consume", "library"):
        (vault / name).mkdir(exist_ok=True)
    from .meta import json_schema

    # Documents the format for anyone reading the vault without DocuHive.
    write_atomic(vault / "meta.schema.json", json_schema())
    if bound != vault_id:
        with db.session() as session:
            session.merge(Setting(key=ID_KEY, value=vault_id))
    _probed.clear()
    return vault_id


_probed: dict[Path, float] = {}


def check() -> VaultStatus:
    """The vault is mounted, is the one this database belongs to, and accepts writes.

    The identity is read on every call, so an unmounted share is noticed at once; only the
    write probe is cached (30 s).
    """
    vault = root()
    try:
        found = (vault / "_system" / "VAULT_ID").read_text().strip()
    except OSError:
        return VaultStatus(ok=False, reason="not_initialised")
    if _bound_id() != found:
        return VaultStatus(ok=False, reason="id_mismatch")
    if time.monotonic() - _probed.get(vault, -CHECK_TTL_S) >= CHECK_TTL_S:
        try:
            write_atomic(vault / "_system" / ".probe", str(time.time()).encode())
        except OSError:
            return VaultStatus(ok=False, reason="not_writable")
        _probed[vault] = time.monotonic()
    return VaultStatus(ok=True)


def require() -> None:
    status = check()
    if not status.ok:
        raise VaultUnavailable(status.reason)


def original(folder: Path) -> Path | None:
    found = sorted(p for p in folder.glob("original.*") if ORIGINAL.match(p.name))
    return found[0] if found else None


def pages(folder: Path) -> list[Path]:
    """The separate photos of a combined upload, in page order."""
    numbered = []
    for path in folder.glob("original-*"):
        if match := PAGE.match(path.name):
            numbered.append((int(match.group(1)), path))
    return [path for _, path in sorted(numbered)]


def combined_sha256(digests: list[str]) -> str:
    """Several pages are identified by the hash of their hashes, in order."""
    return hashlib.sha256("".join(digests).encode()).hexdigest()


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
