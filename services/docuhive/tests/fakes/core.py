"""Platform contract fakes, maintained by Developer OA."""

import hashlib
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

from docuhive.contracts import (
    CurrentUser,
    DocStatus,
    DocumentView,
    IngestRequest,
    IngestResult,
    MetadataPatch,
    Provenance,
    SearchFilters,
)
from docuhive.documents import NotFound
from docuhive.documents.metadata import apply_view
from docuhive.jobs import JobContext
from ulid import ULID


class FakeJobContext(JobContext):
    def heartbeat(self) -> None:
        pass


class FakeJobs:
    def __init__(self, *, run_immediately: bool = False):
        self.jobs: list[dict] = []
        self.handlers: dict = {}
        self.run_immediately = run_immediately

    def enqueue(
        self,
        kind: str,
        payload: dict,
        *,
        queue: str = "default",
        run_after: datetime | None = None,
        dedupe_key: str | None = None,
    ) -> int:
        if dedupe_key:
            for job in self.jobs:
                if job["dedupe_key"] == dedupe_key and job["status"] in {"pending", "running"}:
                    return job["id"]
        job = {
            "id": len(self.jobs) + 1,
            "kind": kind,
            "payload": payload,
            "queue": queue,
            "run_after": run_after,
            "dedupe_key": dedupe_key,
            "status": "pending",
        }
        self.jobs.append(job)
        if (
            self.run_immediately
            and kind in self.handlers
            and (run_after is None or run_after <= datetime.now(UTC))
        ):
            job["status"] = "running"
            self.handlers[kind](
                payload, FakeJobContext(job["id"], 1, logging.getLogger("fake-jobs"))
            )
            job["status"] = "done"
        return job["id"]

    def handler(self, kind: str, **options):
        def register(fn):
            self.handlers[kind] = fn
            return fn

        return register

    def periodic(self, kind: str, **options):
        return self.handler(kind, **options)


class FakeDocuments:
    def __init__(self, jobs: FakeJobs | None = None):
        self.docs: dict[str, DocumentView] = {}
        self.contents: dict[str, str] = {}
        self.jobs = jobs or FakeJobs()
        self.provenance: dict[str, dict[str, Provenance]] = {}

    def get(self, doc_id: str) -> DocumentView:
        if doc_id not in self.docs:
            raise NotFound(doc_id)
        return self.docs[doc_id].model_copy(deep=True)

    def get_for_user(self, doc_id: str, user: CurrentUser) -> DocumentView:
        doc = self.get(doc_id)
        if doc.deleted_at or not (doc.owner_id == user.id or doc.shared):
            raise NotFound(doc_id)
        return doc

    def get_content(self, doc_id: str, max_chars: int | None = None) -> str:
        self.get(doc_id)
        if max_chars is not None and max_chars < 0:
            raise ValueError("max_chars must not be negative")
        return self.contents.get(doc_id, "")[:max_chars]

    def apply_metadata(
        self,
        doc_id: str,
        patch: MetadataPatch,
        *,
        actor: str,
        provenance: Provenance | None = None,
        force: bool = False,
    ):
        doc = self.get(doc_id)
        before_manual = set(doc.manual_fields)
        result = apply_view(doc, patch, actor=actor, force=force)
        unlocked = sorted(before_manual - set(doc.manual_fields))
        self.docs[doc_id] = doc
        if result.applied or unlocked:
            if provenance:
                self.provenance.setdefault(doc_id, {})[provenance.task] = provenance
            payload = {"document_id": doc_id, "fields": result.applied, "actor": actor}
            if unlocked:
                payload["unlocked"] = unlocked
            self.jobs.enqueue("document.metadata_changed", payload, queue="ai")
        return result

    def iter_ids(
        self,
        *,
        status: DocStatus = DocStatus.stored,
        added_since: datetime | None = None,
        filters: SearchFilters | None = None,
    ):
        for doc in sorted(self.docs.values(), key=lambda doc: doc.id):
            if doc.status != status or (added_since and doc.added_at < added_since):
                continue
            if filters:
                if doc.deleted_at and not filters.include_trashed:
                    continue
                if filters.document_ids and doc.id not in filters.document_ids:
                    continue
                if any(
                    selected and value not in selected
                    for selected, value in (
                        (filters.categories, doc.category),
                        (filters.document_types, doc.document_type),
                        (filters.correspondents, doc.correspondent),
                        (filters.source_kinds, doc.source.kind),
                    )
                ):
                    continue
                if not set(filters.tags) <= set(doc.tags):
                    continue
                if filters.date_from and (
                    not doc.document_date or doc.document_date < filters.date_from
                ):
                    continue
                if filters.date_to and (
                    not doc.document_date or doc.document_date > filters.date_to
                ):
                    continue
            yield doc.id


class FakeIngest:
    def __init__(self, root: Path, jobs: FakeJobs | None = None):
        self.root, self.jobs = root, jobs or FakeJobs()
        self.hashes: dict[tuple[int, str], str] = {}

    def incoming_dir(self) -> Path:
        path = self.root / "incoming"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def submit(self, files: list[Path], req: IngestRequest) -> IngestResult:
        from docuhive.config.settings import get_settings
        from docuhive.ingest import TooLarge, UnsupportedType
        from docuhive.ingest.detect import detect
        from docuhive.ingest.errors import Quarantine

        if not files or (len(files) > 1 and not req.combine):
            raise UnsupportedType("Multiple files require combine=True")
        if sum(path.stat().st_size for path in files) > get_settings().max_upload_mb * 1024**2:
            raise TooLarge("Upload exceeds the configured limit")
        try:
            detected = [detect(path) for path in files]
        except Quarantine as error:
            raise UnsupportedType(str(error)) from error
        if len(files) > 1 and any(item.kind != "image" for item in detected):
            raise UnsupportedType("Only images can be combined")
        digests = [hashlib.sha256(path.read_bytes()).hexdigest() for path in files]
        digest = (
            hashlib.sha256("".join(digests).encode()).hexdigest() if req.combine else digests[0]
        )
        key = (req.owner_id, digest)
        if key in self.hashes:
            for path in files:
                path.unlink()
            return IngestResult(document_id=self.hashes[key], status="duplicate")
        doc_id = str(ULID())
        folder = self.root / doc_id
        folder.mkdir(parents=True)
        for index, (path, item) in enumerate(zip(files, detected, strict=True)):
            shutil.move(path, folder / f"input-{index}.{item.ext}")
        self.hashes[key] = doc_id
        self.jobs.enqueue(
            "ingest.process",
            {"document_id": doc_id, "combine": req.combine, "hints": req.hints},
            queue="ocr",
        )
        return IngestResult(document_id=doc_id, status="staged")


def install_fake_core(monkeypatch, root: Path):
    from types import SimpleNamespace

    from docuhive import documents, ingest, jobs

    fake_jobs = FakeJobs()
    fake_docs, fake_ingest = FakeDocuments(fake_jobs), FakeIngest(root, fake_jobs)
    for name in ("enqueue", "handler", "periodic"):
        monkeypatch.setattr(jobs, name, getattr(fake_jobs, name))
    for name in ("get", "get_for_user", "get_content", "apply_metadata", "iter_ids"):
        monkeypatch.setattr(documents, name, getattr(fake_docs, name))
    for name in ("incoming_dir", "submit"):
        monkeypatch.setattr(ingest, name, getattr(fake_ingest, name))
    return SimpleNamespace(jobs=fake_jobs, documents=fake_docs, ingest=fake_ingest)
