"""Poll scanner shares; retain source files until the vault original is verified."""

import json
import os
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from docuhive import ingest, jobs, vault
from docuhive.config.settings import get_settings
from docuhive.contracts import IngestRequest, SourceInfo, SourceKind
from docuhive.db import session
from docuhive.db.models import Document, Setting, User
from docuhive.vault.availability import available
from docuhive.vault.health import folder_of, sha256

KEY = "consume:seen"


def ignored(path: Path) -> bool:
    name = path.name.casefold()
    return (
        name.startswith((".", "~$"))
        or name.endswith((".part", ".tmp", ".crdownload"))
        or name == "thumbs.db"
    )


def signature(path: Path) -> list[int]:
    stat = path.stat(follow_symlinks=False)
    return [stat.st_size, stat.st_mtime_ns, stat.st_ino]


def verified_copy(source: Path, target: Path) -> str:
    before = signature(source)
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as src, target.open("wb") as out:
        shutil.copyfileobj(src, out, 1024 * 1024)
        out.flush()
        os.fsync(out.fileno())
    digest = sha256(target)
    if signature(source) != before or sha256(source) != digest:
        raise OSError("Scanner input changed during pickup")
    return digest


@jobs.periodic("consume.poll", every=timedelta(seconds=30), queue="ocr")
def poll(payload: dict, ctx: jobs.JobContext) -> None:
    if not available():
        return
    settings = get_settings()
    root = settings.consume_dir or vault.root() / "consume"
    if not root.is_dir() or root.is_symlink():
        return
    with session() as db:
        users = {
            u.username: u.id for u in db.scalars(select(User).where(~User.pw_hash.startswith("!")))
        }
        # A persisted observation survives worker restarts; the row lock serialises manual polls.
        row = db.scalar(select(Setting).where(Setting.key == KEY).with_for_update())
        if row is None:
            db.add(Setting(key=KEY, value={}))
            return
        previous = row.value
        seen: dict = {}
        candidates = [(p, settings.consume_default_owner) for p in root.iterdir() if p.is_file()]
        for name in users:
            folder = root / name
            if (
                name != "_rejected"
                and folder.is_dir()
                and not folder.is_symlink()
                and not ignored(folder)
            ):
                candidates.extend((p, name) for p in folder.iterdir() if p.is_file())
        for path, owner in candidates:
            if ignored(path) or path.is_symlink() or owner not in users:
                continue
            key = str(path.relative_to(root))
            try:
                current = signature(path)
                old = previous.get(key, {})
                seen[key] = {"signature": current}
                if old.get("signature") != current:
                    continue
                if "document_id" in old:
                    seen[key] = old
                    doc = db.get(Document, old["document_id"])
                    if doc and doc.status == "stored" and doc.vault_path and available():
                        folder = folder_of(vault.root(), doc.vault_path).resolve()
                        original = vault.original(folder)
                        if folder.is_relative_to(vault.root().resolve()) and original:
                            if (
                                sha256(original) == old["sha256"] == doc.sha256 == sha256(path)
                                and signature(path) == current
                            ):
                                path.unlink()
                                del seen[key]
                    continue
                incoming = ingest.incoming_dir()
                fd, name = tempfile.mkstemp(dir=incoming, suffix=path.suffix[:16])
                os.close(fd)
                copy = Path(name)
                try:
                    if current[0] > settings.max_upload_mb * 1024 * 1024:
                        raise ingest.TooLarge()
                    digest = verified_copy(path, copy)
                    result = ingest.submit(
                        [copy],
                        IngestRequest(
                            owner_id=users[owner],
                            source=SourceInfo(kind=SourceKind.consume, original_filename=path.name),
                        ),
                    )
                    seen[key] = {
                        "signature": current,
                        "document_id": result.document_id,
                        "sha256": digest,
                    }
                except ingest.IngestRejected as error:
                    if signature(path) != current:
                        continue
                    rejected = root / "_rejected"
                    if rejected.is_symlink():
                        raise OSError("Rejected folder must not be a symbolic link") from None
                    rejected.mkdir(exist_ok=True)
                    # Unique names preserve earlier rejections and their explanations.
                    filename = path.name.encode("utf-8")[:180].decode("utf-8", errors="ignore")
                    destination = rejected / f"{copy.stem}-{filename}"
                    os.replace(path, destination)
                    destination.with_name(destination.name + ".reason.txt").write_text(
                        json.dumps(
                            {
                                "reason": type(error).__name__,
                                "action": "Check file type and size, then move it back to retry.",
                            }
                        )
                    )
                    del seen[key]
                finally:
                    copy.unlink(missing_ok=True)
            except (OSError, NotImplementedError):
                ctx.log.warning("Scanner pickup deferred; the input file has been kept")
            ctx.heartbeat()
        row.value = seen
