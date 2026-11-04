"""Regenerate a human-readable hardlink view without moving vault originals."""

import errno
import os
import re
import unicodedata
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from docuhive import jobs
from docuhive.config.settings import get_settings
from docuhive.db import session
from docuhive.db.models import Document, Setting, User
from docuhive.vault.availability import available
from docuhive.vault.health import folder_of

MANIFEST = "library:manifest"
DISABLED = "library:disabled"


def component(value: str, fallback: str = "untitled") -> str:
    value = unicodedata.normalize("NFC", value)
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', "", value).strip(" .")[:120].rstrip(" .")
    return value if value and value not in {".", ".."} else fallback


def inside(root: Path, relative: str) -> Path:
    path = root / relative
    if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root.parent):
        raise ValueError("Library paths must not contain symbolic links")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Library paths must stay in the library")
    return path


def sync(*, retry: bool = False) -> dict:
    if not available():
        return {"ok": False, "reason": "vault_unavailable"}
    vault = get_settings().vault_dir
    library = vault / "library"
    with session() as db:
        disabled = db.get(Setting, DISABLED)
        if disabled and disabled.value and not retry:
            return {"ok": False, "reason": "hardlinks_unavailable"}
        if retry and disabled:
            disabled.value = False
        manifest = db.scalar(select(Setting).where(Setting.key == MANIFEST).with_for_update())
        if manifest is None:
            manifest = Setting(key=MANIFEST, value={})
            db.add(manifest)
        desired: dict[str, Path] = {}
        used: set[str] = set()
        rows = db.execute(
            select(Document, User.username)
            .join(User, User.id == Document.owner_id)
            .where(
                Document.status == "stored",
                Document.deleted_at.is_(None),
                Document.vault_path.is_not(None),
            )
            .order_by(Document.id)
        )
        for doc, username in rows:
            original = folder_of(vault, doc.vault_path) / "archive.pdf"
            if (
                not original.resolve().is_relative_to(vault.resolve())
                or original.is_symlink()
                or not original.is_file()
            ):
                continue
            day = doc.document_date or doc.added_at.date()
            category = [
                component(p, "_uncategorized")
                for p in (doc.category or "_uncategorized").split("/")
            ]
            # Reserved roots cannot be reached through document metadata.
            if category[0].startswith("_") and category[0] != "_uncategorized":
                category[0] = "category-" + category[0]
            prefix = [] if doc.shared else ["_private", component(username)]
            directory = Path(*prefix, *category, str(day.year))
            stem = f"{day.isoformat()} {component(doc.title or doc.id)}"
            relative = str(directory / f"{stem}.pdf")
            number = 1
            while relative.casefold() in used:
                number += 1
                relative = str(directory / f"{stem} ({number}).pdf")
            used.add(relative.casefold())
            desired[relative] = original
        kept = {}
        for relative, inode in manifest.value.items():
            path = inside(library, relative)
            if path.exists():
                stat = path.stat()
                if [stat.st_dev, stat.st_ino] != inode:
                    continue  # A user's replacement is never ours to delete.
                if relative in desired and os.path.samefile(path, desired[relative]):
                    kept[relative] = inode
                else:
                    path.unlink()
        for relative, original in desired.items():
            if relative in kept:
                continue
            target = inside(library, relative)
            if target.exists():
                continue  # Never overwrite unrelated files, including after a lost manifest.
            if relative.startswith("_private/"):
                private = library / "_private"
                private.mkdir(parents=True, exist_ok=True, mode=0o700)
                private.chmod(0o700)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(original, target)
            except OSError as error:
                if error.errno not in {errno.EXDEV, errno.EPERM, errno.ENOTSUP, errno.ENOSYS}:
                    raise
                db.merge(Setting(key=DISABLED, value=True))
                manifest.value = kept
                return {"ok": False, "reason": "hardlinks_unavailable"}
            stat = target.stat()
            kept[relative] = [stat.st_dev, stat.st_ino]
        manifest.value = kept
        if library.exists():
            for folder in sorted(library.rglob("*"), reverse=True):
                if folder.is_dir() and not folder.is_symlink():
                    try:
                        folder.rmdir()
                    except OSError:
                        pass  # Only empty directories are removed.
        return {"ok": True, "links": len(kept)}


@jobs.periodic("library.sync", every=timedelta(hours=1))
def periodic_sync(payload: dict, ctx: jobs.JobContext) -> None:
    result = sync()
    if not result["ok"]:
        ctx.log.warning("Library view unavailable: %s", result["reason"])
