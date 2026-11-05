"""CL test fakes: SQLite stand-ins for OA's contracts (db, jobs, documents, ingest, auth, search)
plus helpers for routing and FakeModel. No Docker, no network, no API keys.

    core = FakeCore(); core.install(monkeypatch)
    doc = core.docs.add(content="Stromrechnung ...", owner_id=1)
    core.jobs.run()            # run queued jobs through the real handler registry
"""

import hashlib
import json
import shutil
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from docuhive.ai.fake import REGISTRY, FakeModel
from docuhive.contracts import (
    ApplyResult,
    CurrentUser,
    DocStatus,
    DocumentView,
    FactValue,
    IngestRequest,
    IngestResult,
    MetadataPatch,
    Provenance,
    SearchFilters,
    SearchHit,
    SourceInfo,
)
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    and_,
    create_engine,
    delete,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from ulid import ULID

__all__ = ["FakeCore", "FakeModel", "REGISTRY", "TEST_ROUTING", "use_routing"]

meta = MetaData()
users = Table(
    "users",
    meta,
    Column("id", Integer, primary_key=True),
    Column("username", Text),
    Column("role", Text),
)
correspondents = Table(
    "correspondents",
    meta,
    Column("id", Integer, primary_key=True),
    Column("name", Text),
    Column("norm_name", Text, unique=True),
    Column("merged_into", BigInteger),
)
tags = Table(
    "tags",
    meta,
    Column("id", Integer, primary_key=True),
    Column("name", Text),
    Column("slug", Text, unique=True),
    Column("merged_into", BigInteger),
)
documents = Table(
    "documents",
    meta,
    Column("id", String, primary_key=True),
    Column("owner_id", Integer),
    Column("shared", Boolean, default=True),
    Column("status", Text),
    Column("sha256", Text),
    Column("mime", Text),
    Column("pages", Integer),
    Column("title", Text),
    Column("document_date", Date),
    Column("language", Text),
    Column("category", Text),
    Column("document_type", Text),
    Column("correspondent_id", Integer),
    Column("content", Text),
    Column("manual_fields", JSON, default=list),
    Column("added_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
    Column("deleted_at", DateTime(timezone=True)),
)
document_tags = Table(
    "document_tags",
    meta,
    Column("document_id", String, primary_key=True),
    Column("tag_id", Integer, primary_key=True),
)
doc_facts = Table(
    "doc_facts",
    meta,
    Column("document_id", String, primary_key=True),
    Column("field", Text, primary_key=True),
    Column("type", Text),
    Column("value_text", Text),
    Column("value_num", Numeric),
    Column("value_date", Date),
    Column("currency", Text),
    Column("confidence", Numeric),
)
doc_sources = Table(
    "doc_sources",
    meta,
    Column("document_id", String, primary_key=True),
    Column("kind", Text),
    Column("original_filename", Text),
    Column("account_id", Integer),
    Column("message_id", Text),
    Column("email_from", Text),
    Column("subject", Text),
    Column("received_at", DateTime(timezone=True)),
)
jobs_table = Table(
    "jobs",
    meta,
    Column("id", Integer, primary_key=True),
    Column("kind", Text),
    Column("status", Text),
    Column("last_error", Text),
    Column("finished_at", DateTime(timezone=True)),
)
api_tokens = Table(
    "api_tokens",
    meta,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer),
    Column("token_hash", Text),
    Column("scopes", JSON),
    Column("revoked_at", DateTime(timezone=True)),
)
custom_fields = Table(
    "custom_fields",
    meta,
    Column("id", Integer, primary_key=True),
    Column("name", Text),
    Column("label", Text),
    Column("type", Text),
    Column("description", Text, default=""),
    Column("document_types", JSON, default=list),
    Column("remind_days_before", JSON, default=list),
)
duplicate_pairs = Table(
    "duplicate_pairs",
    meta,
    Column("id", Integer, primary_key=True),
    Column("document_id", String),
    Column("other_id", String),
    Column("score", Numeric),
    Column("reasons", JSON, default=list),
    Column("status", Text, default="open"),
)
settings = Table("settings", meta, Column("key", String, primary_key=True), Column("value", JSON))
TABLES = {t.name: t for t in meta.sorted_tables}


def norm(name: str) -> str:
    return " ".join(name.casefold().split())


def visible_docs(user: CurrentUser):  # type: ignore[no-untyped-def]
    return and_(
        or_(documents.c.owner_id == user.id, documents.c.shared.is_(True)),
        documents.c.deleted_at.is_(None),
    )


def visible_docs_incl_trash(user: CurrentUser):  # type: ignore[no-untyped-def]
    return or_(documents.c.owner_id == user.id, documents.c.shared.is_(True))


class NotFound(Exception):
    pass


class Deferred(Exception):
    def __init__(self, until: datetime, reason: str):
        super().__init__(reason)
        self.until, self.reason = until, reason


@dataclass
class Job:
    id: int
    kind: str
    payload: dict
    queue: str
    dedupe_key: str | None
    run_after: datetime | None
    status: str = "pending"  # pending | done | deferred | failed
    note: str | None = None


@dataclass
class Ctx:
    job_id: int
    attempt: int = 1
    log: Any = field(default_factory=lambda: __import__("logging").getLogger("fake.job"))

    def heartbeat(self) -> None:
        pass

    def defer(self, until: datetime, reason: str):  # type: ignore[no-untyped-def]
        raise Deferred(until, reason)


class FakeJobs:
    def __init__(self) -> None:
        self.all: list[Job] = []

    def document_jobs(self, document_ids: list[str]) -> list[dict]:
        return [
            {
                "id": j.id,
                "kind": j.kind,
                "status": j.status,
                "document_id": j.payload["document_id"],
                "run_after": j.run_after,
                "paused": j.status == "deferred",
            }
            for j in reversed(self.all)
            if j.payload.get("document_id") in document_ids
            and j.kind in ("document.stored", "ai.classify", "ai.extract", "index.embed")
        ]

    def enqueue(
        self,
        kind: str,
        payload: dict,
        *,
        queue: str = "default",
        run_after: datetime | None = None,
        dedupe_key: str | None = None,
    ) -> int:
        for j in self.all:
            if dedupe_key and j.dedupe_key == dedupe_key and j.status == "pending":
                return j.id
        job = Job(len(self.all) + 1, kind, payload, queue, dedupe_key, run_after)
        self.all.append(job)
        return job.id

    def pending(self, kind: str | None = None) -> list[Job]:
        return [j for j in self.all if j.status == "pending" and kind in (None, j.kind)]

    def kinds(self) -> list[str]:
        return [j.kind for j in self.pending()]

    def run(self, kinds: set[str] | None = None, max_jobs: int = 500) -> list[Job]:
        """Run pending jobs (and the jobs they enqueue) through the real handler registry.
        Kinds without a handler stay pending, like the real queue."""
        from docuhive import jobs

        ran: list[Job] = []
        for _ in range(max_jobs):
            job = next(
                (
                    j
                    for j in self.pending()
                    if (kinds is None or j.kind in kinds) and j.kind in jobs.HANDLERS
                ),
                None,
            )
            if job is None:
                break
            try:
                jobs.HANDLERS[job.kind].fn(job.payload, Ctx(job.id))
                job.status = "done"
            except Deferred as d:
                job.status, job.note = "deferred", d.reason
            except jobs.PermanentFailure as e:
                job.status, job.note = "failed", str(e)
            ran.append(job)
        return ran


class FakeDocuments:
    """In-memory documents service with the real apply_metadata semantics (contracts §2.5)."""

    def __init__(self, core: "FakeCore"):
        self.core = core
        self.provenance: dict[str, dict[str, Provenance]] = {}
        self.calls: list[tuple[str, MetadataPatch, str]] = []

    def add(
        self,
        content: str = "",
        *,
        owner_id: int = 1,
        shared: bool = True,
        status: str = "stored",
        title: str | None = None,
        category: str | None = None,
        document_type: str | None = None,
        correspondent: str | None = None,
        document_date: date | None = None,
        tags: list[str] = (),
        facts: dict | None = None,
        manual_fields: list[str] = (),
        source_kind: str = "upload",
        filename: str = "scan.pdf",
        doc_id: str | None = None,
        deleted: bool = False,
        **source: Any,
    ) -> str:
        doc_id = doc_id or str(ULID())
        now = datetime.now(UTC)
        with self.core.session() as s:
            s.execute(
                insert(documents).values(
                    id=doc_id,
                    owner_id=owner_id,
                    shared=shared,
                    status=status,
                    sha256=hashlib.sha256(content.encode()).hexdigest(),
                    mime="application/pdf",
                    pages=1,
                    title=title or filename,
                    document_date=document_date,
                    category=category,
                    document_type=document_type,
                    content=content,
                    manual_fields=list(manual_fields),
                    added_at=now,
                    updated_at=now,
                    deleted_at=now if deleted else None,
                    correspondent_id=self._correspondent(s, correspondent)
                    if correspondent
                    else None,
                )
            )
            s.execute(
                insert(doc_sources).values(
                    document_id=doc_id, kind=source_kind, original_filename=filename, **source
                )
            )
            for t in tags:
                s.execute(insert(document_tags).values(document_id=doc_id, tag_id=self._tag(s, t)))
            for k, v in (facts or {}).items():
                self._fact(s, doc_id, k, v if isinstance(v, FactValue) else FactValue(**v))
        return doc_id

    def _correspondent(self, s: Session, name: str) -> int:
        cid = s.scalar(select(correspondents.c.id).where(correspondents.c.norm_name == norm(name)))
        if cid is None:
            cid = s.execute(
                insert(correspondents).values(name=name.strip(), norm_name=norm(name))
            ).inserted_primary_key[0]
        return cid

    def _tag(self, s: Session, name: str) -> int:
        tid = s.scalar(select(tags.c.id).where(tags.c.slug == name.lower()))
        if tid is None:
            tid = s.execute(insert(tags).values(name=name, slug=name.lower())).inserted_primary_key[
                0
            ]
        return tid

    def _fact(self, s: Session, doc_id: str, name: str, f: FactValue) -> None:
        s.execute(
            delete(doc_facts).where(doc_facts.c.document_id == doc_id, doc_facts.c.field == name)
        )
        s.execute(
            insert(doc_facts).values(
                document_id=doc_id,
                field=name,
                type=f.type,
                value_text=f.value,
                value_num=Decimal(f.value) if f.type in ("money", "number") else None,
                value_date=date.fromisoformat(f.value) if f.type == "date" else None,
                currency=f.currency,
                confidence=f.confidence,
            )
        )

    def get(self, doc_id: str) -> DocumentView:
        with self.core.session() as s:
            row = s.execute(select(documents).where(documents.c.id == doc_id)).mappings().first()
            if row is None:
                raise NotFound(doc_id)
            corr = (
                s.scalar(
                    select(correspondents.c.name).where(
                        correspondents.c.id == row["correspondent_id"]
                    )
                )
                if row["correspondent_id"]
                else None
            )
            tag_names = list(
                s.scalars(
                    select(tags.c.name)
                    .join(document_tags, document_tags.c.tag_id == tags.c.id)
                    .where(document_tags.c.document_id == doc_id)
                    .order_by(tags.c.name)
                )
            )
            facts = {
                r["field"]: FactValue(
                    type=r["type"],
                    value=r["value_text"],
                    currency=r["currency"],
                    confidence=float(r["confidence"]) if r["confidence"] is not None else None,
                )
                for r in s.execute(
                    select(doc_facts).where(doc_facts.c.document_id == doc_id)
                ).mappings()
            }
            src = (
                s.execute(select(doc_sources).where(doc_sources.c.document_id == doc_id))
                .mappings()
                .first()
            )
        return DocumentView(
            id=row["id"],
            owner_id=row["owner_id"],
            shared=row["shared"],
            status=row["status"],
            mime=row["mime"],
            pages=row["pages"],
            added_at=row["added_at"],
            title=row["title"],
            document_date=row["document_date"],
            language=row["language"],
            category=row["category"],
            document_type=row["document_type"],
            correspondent=corr,
            tags=tag_names,
            facts=facts,
            manual_fields=list(row["manual_fields"] or []),
            source=SourceInfo(**{k: v for k, v in dict(src).items() if k != "document_id"}),
            deleted_at=row["deleted_at"],
        )

    def get_for_user(self, doc_id: str, user: CurrentUser) -> DocumentView:
        v = self.get(doc_id)
        if v.deleted_at or not (v.owner_id == user.id or v.shared):
            raise NotFound(doc_id)
        return v

    def get_content(self, doc_id: str, max_chars: int | None = None) -> str:
        with self.core.session() as s:
            text = s.scalar(select(documents.c.content).where(documents.c.id == doc_id)) or ""
        return text[:max_chars] if max_chars else text

    def apply_metadata(
        self,
        doc_id: str,
        patch: MetadataPatch,
        *,
        actor: str,
        provenance: Provenance | None = None,
        force: bool = False,
    ) -> ApplyResult:
        self.calls.append((doc_id, patch, actor))
        view = self.get(doc_id)
        manual = set(view.manual_fields)
        is_ai, is_user = actor.startswith("ai:"), actor.startswith("user:")
        applied: list[str] = []
        skipped: list[str] = []

        def allowed(name: str) -> bool:
            if is_ai and not force and name in manual:
                skipped.append(name)
                return False
            applied.append(name)
            return True

        with self.core.session() as s:
            values: dict[str, Any] = {}
            for name in ("title", "document_date", "language", "category", "document_type"):
                v = getattr(patch, name)
                if v is not None and allowed(name):
                    values[name] = v
            if patch.correspondent is not None and allowed("correspondent"):
                values["correspondent_id"] = self._correspondent(s, patch.correspondent)
            if (patch.tags_add or patch.tags_remove) and allowed("tags"):
                for t in patch.tags_add:
                    s.execute(
                        delete(document_tags).where(
                            document_tags.c.document_id == doc_id,
                            document_tags.c.tag_id == self._tag(s, t),
                        )
                    )
                    s.execute(
                        insert(document_tags).values(document_id=doc_id, tag_id=self._tag(s, t))
                    )
                for t in patch.tags_remove:
                    s.execute(
                        delete(document_tags).where(
                            document_tags.c.document_id == doc_id,
                            document_tags.c.tag_id == self._tag(s, t),
                        )
                    )
            for k, f in (patch.facts or {}).items():
                if allowed(f"facts.{k}"):
                    if f is None:
                        s.execute(
                            delete(doc_facts).where(
                                doc_facts.c.document_id == doc_id, doc_facts.c.field == k
                            )
                        )
                    else:
                        self._fact(s, doc_id, k, f)
            unlocked = [f for f in patch.unlock_fields if is_user and f in manual]
            if is_user:
                manual |= set(applied)
            manual -= set(unlocked)
            values["manual_fields"] = sorted(manual)
            values["updated_at"] = datetime.now(UTC)
            s.execute(update(documents).where(documents.c.id == doc_id).values(**values))
        if provenance:
            self.provenance.setdefault(doc_id, {})[provenance.task] = provenance
        if applied or unlocked:
            self.core.jobs.enqueue(
                "document.metadata_changed",
                {"document_id": doc_id, "fields": applied, "unlocked": unlocked, "actor": actor},
                queue="ai",
            )
        return ApplyResult(applied=applied, skipped_manual=skipped)

    def iter_ids(
        self,
        *,
        status: DocStatus = DocStatus.stored,
        added_since: datetime | None = None,
        filters: SearchFilters | None = None,
    ) -> Iterator[str]:
        q = select(documents.c.id).where(
            documents.c.status == status, documents.c.deleted_at.is_(None)
        )
        if added_since:
            q = q.where(documents.c.added_at >= added_since)
        with self.core.session() as s:
            ids = list(s.scalars(q.order_by(documents.c.id)))
        yield from ids

    def trash(self, doc_id: str) -> None:
        with self.core.session() as s:
            s.execute(
                update(documents)
                .where(documents.c.id == doc_id)
                .values(deleted_at=datetime.now(UTC))
            )


class FakeIngest:
    class IngestRejected(Exception):
        pass

    class UnsupportedType(IngestRejected):
        pass

    class TooLarge(IngestRejected):
        pass

    def __init__(self, core: "FakeCore", root: Path):
        self.core, self.root = core, root
        (root / "incoming").mkdir(parents=True, exist_ok=True)
        self.submitted: list[tuple[str, IngestRequest, list[str]]] = []
        self._by_sha: dict[tuple[int, str], str] = {}

    def incoming_dir(self) -> Path:
        return self.root / "incoming"

    def submit(self, files: list[Path], req: IngestRequest) -> IngestResult:
        data = b"".join(p.read_bytes() for p in files)
        sha = hashlib.sha256(data).hexdigest()
        if (req.owner_id, sha) in self._by_sha:
            for p in files:
                p.unlink()
            return IngestResult(document_id=self._by_sha[(req.owner_id, sha)], status="duplicate")
        doc_id = str(ULID())
        dest = self.root / "vault" / doc_id
        dest.mkdir(parents=True)
        names = []
        for p in files:
            names.append(p.name)
            shutil.move(p, dest / p.name)
        self._by_sha[(req.owner_id, sha)] = doc_id
        self.submitted.append((doc_id, req, names))
        return IngestResult(document_id=doc_id, status="staged")


class FakeCore:
    def __init__(self, root: Path | None = None):
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        meta.create_all(self.engine)
        from docuhive.db import IntelBase

        _import_intel_models()
        IntelBase.metadata.create_all(self.engine)
        self.jobs = FakeJobs()
        self.docs = FakeDocuments(self)
        self.ingest = FakeIngest(self, root or Path("tmp/fake-vault"))
        self.semantic: Any = None
        with self.session() as s:
            s.execute(
                insert(users).values(
                    [
                        {"id": 1, "username": "dev", "role": "admin"},
                        {"id": 2, "username": "member", "role": "member"},
                    ]
                )
            )

    @contextmanager
    def session(self) -> Iterator[Session]:
        with Session(self.engine) as s, s.begin():
            yield s

    def hybrid(
        self,
        user: CurrentUser,
        query: str,
        filters: SearchFilters,
        limit: int = 20,
        mode: str = "hybrid",
    ) -> list[SearchHit]:
        if self.semantic is None:
            return []
        hits = self.semantic(user, query, filters, limit)
        return [
            SearchHit(
                document_id=h.document_id,
                title=None,
                snippet=h.text[:200],
                score=h.score,
                fts_rank=None,
                semantic_rank=i + 1,
            )
            for i, h in enumerate(hits)
        ]

    def install(self, mp: Any) -> "FakeCore":
        """Point OA's contract modules at the fakes (monkeypatch, undone after the test)."""
        from docuhive import db, jobs
        from docuhive.ai import coretables

        mp.setattr(db, "session", self.session)
        mp.setattr(jobs, "enqueue", self.jobs.enqueue)
        mp.setattr(jobs, "document_jobs", self.jobs.document_jobs)
        mp.setattr(coretables, "table", lambda name: TABLES[name])
        mods = {
            name: _module(f"docuhive.{name}") for name in ("documents", "ingest", "auth", "search")
        }
        for fn in ("get", "get_for_user", "get_content", "apply_metadata", "iter_ids"):
            mp.setattr(mods["documents"], fn, getattr(self.docs, fn))
        mp.setattr(mods["documents"], "NotFound", NotFound)
        mp.setattr(mods["ingest"], "incoming_dir", self.ingest.incoming_dir)
        mp.setattr(mods["ingest"], "submit", self.ingest.submit)
        for exc in ("IngestRejected", "UnsupportedType", "TooLarge"):
            mp.setattr(mods["ingest"], exc, getattr(FakeIngest, exc), raising=False)
        mp.setattr(mods["auth"], "visible_docs", visible_docs)
        mp.setattr(mods["auth"], "visible_docs_incl_trash", visible_docs_incl_trash)
        mp.setattr(mods["search"], "hybrid", self.hybrid)
        mp.setattr(mods["search"], "register_semantic", lambda fn: setattr(self, "semantic", fn))
        return self

    def count(self, table: str, **where: Any) -> int:
        from docuhive.db import IntelBase

        t = IntelBase.metadata.tables.get(table)
        t = TABLES[table] if t is None else t
        q = select(func.count()).select_from(t)
        for k, v in where.items():
            q = q.where(t.c[k] == v)
        with self.session() as s:
            return s.scalar(q) or 0

    def rows(self, table: str, **where: Any) -> list[dict]:
        from docuhive.db import IntelBase

        t = IntelBase.metadata.tables.get(table)
        t = TABLES[table] if t is None else t
        q = select(t)
        for k, v in where.items():
            q = q.where(t.c[k] == v)
        with self.session() as s:
            return [dict(r) for r in s.execute(q.order_by(*t.primary_key.columns)).mappings()]


def _module(name: str) -> types.ModuleType:
    try:
        return __import__(name, fromlist=["_"])
    except ModuleNotFoundError:  # OA has not created the stub yet
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        setattr(sys.modules["docuhive"], name.rsplit(".", 1)[1], mod)
        return mod


def _import_intel_models() -> None:
    import importlib

    for m in (
        "ai.models",
        "review.models",
        "mail.models",
        "index.models",
        "chat.models",
        "notify.models",
        "reminders.models",
    ):
        try:
            importlib.import_module(f"docuhive.{m}")
        except ModuleNotFoundError as e:
            if e.name != f"docuhive.{m}":
                raise


TEST_ROUTING: dict = {
    "version": 1,
    "providers": {
        "local": {"kind": "fake", "local": True},
        "cloud": {"kind": "fake", "local": False},
    },
    "tasks": {t: {"route": "local/m"} for t in ("triage", "classify", "extract", "chat", "analyse")}
    | {"embed": {"route": "local/embed", "dims": 1024}},
    "privacy": {"restricted_tags": ["private"]},
    "budgets": {"cloud": 1.0},
    "pricing": {"cloud/m": {"in": 1000.0, "out": 1000.0}},
    "limits": {"timeout_s": {}, "retries": 1},
}


def use_routing(mp: Any, **overrides: Any) -> Any:
    """Install TEST_ROUTING (deep-merged with overrides) as the effective routing.yaml."""
    from docuhive.ai import routing

    raw = json.loads(json.dumps(TEST_ROUTING))
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(raw.get(key), dict):
            raw[key] = {**raw[key], **value}
        else:
            raw[key] = value
    cfg = routing.parse(raw)
    mp.setattr(routing, "load", lambda: cfg)
    return cfg
