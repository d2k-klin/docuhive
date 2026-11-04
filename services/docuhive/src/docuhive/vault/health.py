"""Read-only vault health check: every stored document's files exist, parse and match the DB.

The vault is the source of truth, so this never repairs or moves anything; it only reports.
"""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select

from docuhive import db, jobs
from docuhive.config.settings import get_settings
from docuhive.db.models import Document, Setting
from docuhive.vault import sha256

KEY = "vault.health"
MAX_PROBLEMS = 200
YEAR = re.compile(r"^\d{4}$")

Problem = Literal[
    "vault_unavailable",
    "folder_missing",
    "original_missing",
    "archive_missing",
    "meta_missing",
    "meta_invalid",
    "checksum_mismatch",
    "orphan_folder",
]


class VaultProblem(BaseModel):
    kind: Problem
    document_id: str | None
    path: str  # relative to the vault, never an absolute host path


class VaultReport(BaseModel):
    checked_at: datetime
    full: bool
    documents: int
    hashed: int
    problem_count: int
    problems: list[VaultProblem]  # first MAX_PROBLEMS only

    @property
    def ok(self) -> bool:
        return self.problem_count == 0


def original_sha256(originals: list[Path], folder: Path) -> str:
    """A combined photo upload is identified by the hash of its pages' hashes, in order."""
    pages = sorted(folder.glob("original-*.*"), key=lambda p: int(p.stem.split("-")[1]))
    if pages:
        return hashlib.sha256("".join(sha256(p) for p in pages).encode()).hexdigest()
    return sha256(originals[0])


def folder_of(vault: Path, vault_path: str) -> Path:
    path = Path(vault_path)
    return path if path.is_absolute() else vault / path


def scan(full: bool = False) -> VaultReport:
    vault = get_settings().vault_dir
    problems: list[VaultProblem] = []
    hashed = 0

    def report(kind: Problem, doc_id: str | None, path: Path) -> None:
        problems.append(VaultProblem(kind=kind, document_id=doc_id, path=relative(vault, path)))

    with db.session() as session:
        rows = session.execute(
            select(Document.id, Document.vault_path, Document.sha256).where(
                Document.status == "stored", Document.vault_path.is_not(None)
            )
        ).all()
    if not (vault / "_system").is_dir():
        # An unmounted share looks like an empty folder; one problem says so instead of N.
        report("vault_unavailable", None, vault / "_system")
        return finish(full, len(rows), 0, problems)
    known: set[Path] = set()
    for doc_id, vault_path, expected in rows:
        folder = folder_of(vault, str(vault_path))
        known.add(folder.resolve())
        if not folder.is_dir():
            report("folder_missing", doc_id, folder)
            continue
        originals = sorted(folder.glob("original.*"))
        if not originals:
            report("original_missing", doc_id, folder / "original.*")
        elif full:
            hashed += 1
            if original_sha256(originals, folder) != expected:
                report("checksum_mismatch", doc_id, originals[0])
        if not (folder / "archive.pdf").is_file():
            report("archive_missing", doc_id, folder / "archive.pdf")
        meta = folder / "meta.json"
        if not meta.is_file():
            report("meta_missing", doc_id, meta)
            continue
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            data = None
        if not isinstance(data, dict) or data.get("id") != doc_id:
            report("meta_invalid", doc_id, meta)
    for year in vault.iterdir():
        if year.is_dir() and YEAR.match(year.name):
            for folder in year.iterdir():
                if folder.is_dir() and folder.resolve() not in known:
                    report("orphan_folder", None, folder)
    return finish(full, len(rows), hashed, problems)


def relative(vault: Path, path: Path) -> str:
    try:
        return str(path.relative_to(vault))
    except ValueError:
        return path.name


def finish(full: bool, documents: int, hashed: int, problems: list[VaultProblem]) -> VaultReport:
    result = VaultReport(
        checked_at=datetime.now(UTC),
        full=full,
        documents=documents,
        hashed=hashed,
        problem_count=len(problems),
        problems=problems[:MAX_PROBLEMS],
    )
    with db.session() as session:
        session.merge(Setting(key=KEY, value=result.model_dump(mode="json")))
    return result


def last() -> VaultReport | None:
    with db.session() as session:
        value = session.scalar(select(Setting.value).where(Setting.key == KEY))
    return VaultReport.model_validate(value) if value else None


@jobs.periodic("vault.check", every=timedelta(days=7))
def periodic_check(payload: dict, ctx: object) -> None:
    scan(full=payload.get("full", True))
