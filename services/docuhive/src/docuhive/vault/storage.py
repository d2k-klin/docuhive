"""Choosing the vault folder in the app, inside a storage root mounted at install.

Only safe moves are allowed: a new vault in an empty folder while the archive holds no
documents, or the archive's own vault found at a new place (a share mounted elsewhere).
Moving documents between storages is not done here.
"""

import os
import re
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import delete, func, select

from docuhive import db, vault
from docuhive.config.settings import get_settings
from docuhive.db.models import Document, Setting

State = Literal["empty", "this_vault", "other_vault", "not_empty", "not_writable"]
NAME = re.compile(r"^[^/\\.][^/\\]{0,99}$")


class Refused(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class Folder(BaseModel):
    name: str
    path: str  # relative to the storage root
    state: State


class Listing(BaseModel):
    root: str  # the storage root as the host sees it
    path: str
    current: str | None  # the chosen vault, relative to the root, when it is inside it
    folders: list[Folder]


def storage_root() -> Path:
    root = get_settings().storage_root
    if root is None or not root.is_dir():
        raise Refused(
            "no_storage_root",
            "No storage folder is available to choose from. Mount one at install "
            "(DOCUHIVE_STORAGE_ROOT_HOST_DIR, see the installation guide).",
        )
    return root.resolve()


def _inside(relative: str) -> Path:
    root = storage_root()
    target = (root / relative.strip("/")).resolve()
    if not target.is_relative_to(root):
        raise Refused("outside_storage_root", "Choose a folder inside the storage folder.")
    return target


def state(folder: Path) -> State:
    marker = folder / "_system" / "VAULT_ID"
    if marker.is_file():
        found = marker.read_text().strip()
        return "this_vault" if found == vault._bound_id() else "other_vault"
    if any(folder.iterdir()) and not vault._is_empty_skeleton(folder):
        return "not_empty"
    if not os.access(folder, os.W_OK | os.X_OK):
        return "not_writable"
    return "empty"


def label(folder: Path) -> str:
    settings, root = get_settings(), storage_root()
    shown = settings.storage_root_label or str(root)
    rest = folder.relative_to(root).as_posix()
    return shown if rest == "." else f"{shown.rstrip('/')}/{rest}"


def listing(relative: str = "") -> Listing:
    root, here = storage_root(), _inside(relative)
    if not here.is_dir():
        raise Refused("not_found", "That folder no longer exists.")
    folders = [
        Folder(name=p.name, path=p.relative_to(root).as_posix(), state=state(p))
        for p in sorted(here.iterdir(), key=lambda p: p.name.lower())
        # Links are hidden (macOS /Volumes links back to the system disk); _inside refuses them.
        if p.is_dir() and not p.is_symlink() and not p.name.startswith(".")
    ]
    current, rel = vault.root().resolve(), here.relative_to(root).as_posix()
    return Listing(
        root=label(root),
        path="" if rel == "." else rel,
        current=current.relative_to(root).as_posix() if current.is_relative_to(root) else None,
        folders=folders,
    )


def create(relative: str, name: str) -> Folder:
    if not NAME.match(name.strip()):
        raise Refused("invalid_name", "Use a folder name without slashes or a leading dot.")
    parent = _inside(relative)
    folder = parent / name.strip()
    try:
        folder.mkdir()
    except FileExistsError:
        raise Refused("exists", "A folder with that name already exists.") from None
    except OSError:
        raise Refused("not_writable", "DocuHive can't create a folder here.") from None
    rel = folder.relative_to(storage_root()).as_posix()
    return Folder(name=folder.name, path=rel, state="empty")


def _documents() -> int:
    with db.session() as session:
        return session.scalar(select(func.count()).select_from(Document)) or 0


def _writable(folder: Path) -> bool:
    probe = folder / f".docuhive-probe-{uuid.uuid4().hex}"
    try:
        probe.write_bytes(b"")
        probe.unlink()
    except OSError:
        return False
    return True


def choose(relative: str) -> str:
    """Make the folder the vault; returns the vault ID. Refuses anything unsafe."""
    folder = _inside(relative)
    if not folder.is_dir():
        raise Refused("not_found", "That folder no longer exists.")
    found = state(folder)
    if found == "other_vault":
        raise Refused(
            "other_vault",
            "This folder holds another archive's vault. Restoring an archive from its vault "
            "is `docuhive vault rebuild` on a new database (see the restore guide).",
        )
    if found == "not_empty":
        raise Refused("not_empty", "Choose an empty folder, or create a new one here.")
    if found == "not_writable" or not _writable(folder):
        raise Refused("not_writable", "DocuHive can't write to this folder.")
    if found == "empty" and _documents():
        raise Refused(
            "archive_not_empty",
            "Your archive already has documents. A new, empty storage would leave them "
            "behind; moving documents to another storage isn't supported yet.",
        )
    with db.session() as session:
        before = {k: session.get(Setting, k) for k in (vault.PATH_KEY, vault.ID_KEY)}
        before_values = {k: s.value if s else None for k, s in before.items()}
        session.merge(Setting(key=vault.PATH_KEY, value=str(folder)))
        if found == "empty":  # the archive is empty: bind it to the new vault init creates
            session.execute(delete(Setting).where(Setting.key == vault.ID_KEY))
    vault.forget_chosen()
    try:
        return vault.init()
    except Exception:
        with db.session() as session:  # put the previous storage back exactly as it was
            for key, value in before_values.items():
                session.execute(delete(Setting).where(Setting.key == key))
                if value is not None:
                    session.add(Setting(key=key, value=value))
        vault.forget_chosen()
        raise
