"""Testing a plugin against a disposable archive: real database, no network, no AI key.

    from docuhive.sdk.testing import Archive

    def test_tags(archive_db):                 # any fixture that provides an empty test database
        with Archive("plugins-example/schule") as archive:
            alice = archive.user("alice")
            letter = archive.add(alice, document_type="school_letter")
            archive.emit("document.classified", document_id=letter, document_type="school_letter")
            archive.run_jobs()
            assert archive.document(letter).tags == ["school"]

The AI is off unless the test scripts its answers: `Archive(plugin, ai={"*": {...}})` answers
every question with that structured output (keys are substrings of the prompt, as in FakeModel).
No real model is ever asked.

Needs DOCUHIVE_TEST_DATABASE_URL pointing at a database whose name ends in `_test`; its
tables are emptied. `docker compose -f deploy/compose.test.yml up -d` starts one.
"""

import os
import shutil
import tempfile
from datetime import UTC, datetime
from datetime import date as Date
from pathlib import Path
from typing import Any

from ulid import ULID

from docuhive.contracts import CurrentUser, DocumentView, FactValue


class Archive:
    def __init__(
        self,
        plugin: str | Path,
        *,
        also: list[str | Path] = (),  # type: ignore[assignment]
        ai: dict[str, Any] | None = None,
    ) -> None:
        self.paths = [Path(p).resolve() for p in (*also, plugin)]
        self.ai = ai
        self._users: dict[str, CurrentUser] = {}
        self._count = 0

    # Set-up ------------------------------------------------------------------------------
    def __enter__(self) -> "Archive":
        from sqlalchemy import text
        from sqlalchemy.engine import make_url

        from docuhive import config, db
        from docuhive.db import CoreBase, get_engine, models  # noqa: F401
        from docuhive.db.migrations import migrate
        from docuhive.plugins import data, discovery, runtime, state

        url = os.environ.get("DOCUHIVE_TEST_DATABASE_URL", "")
        if not (make_url(url).database or "").endswith("_test") if url else True:
            raise RuntimeError(
                "Set DOCUHIVE_TEST_DATABASE_URL to a disposable database whose name ends in _test"
            )
        roots = {p.parent for p in self.paths}
        if len(roots) != 1:
            raise RuntimeError("Put the plugins under test in one folder")
        os.environ["DOCUHIVE_DATABASE_URL"] = url
        os.environ["DOCUHIVE_PLUGINS_DIR"] = str(roots.pop())
        # A fresh vault and staging folder: tests never touch a real archive's files.
        self._tmp = tempfile.mkdtemp(prefix="docuhive-plugin-test-")
        os.environ["DOCUHIVE_VAULT_DIR"] = f"{self._tmp}/vault"
        os.environ["DOCUHIVE_STAGING_DIR"] = f"{self._tmp}/staging"
        config.reload()
        self._ai_off()
        get_engine.cache_clear()
        runtime.reset()
        migrate("upgrade")
        names = ", ".join(f'"{t}"' for t in CoreBase.metadata.tables)
        with db.session() as s:
            s.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        from docuhive import vault

        vault.forget_chosen()
        vault.init()
        for path in self.paths:
            data.drop(path.name)
            found = discovery.find(path.name)
            if found is None or not found.loadable or found.manifest is None:
                raise RuntimeError(f"{path.name}: {found.problems if found else 'not found'}")
            state.enable(path.name, found.manifest.capability_names(), actor="test")
        runtime.start("worker")
        missing = [p.name for p in self.paths if p.name not in runtime.LOADED]
        if missing:
            errors = {k: v.last_error for k, v in state.states().items() if k in missing}
            raise RuntimeError(f"Could not start: {errors}")
        return self

    def _ai_off(self) -> None:
        """Never reach a real model: AI off, or every task routed to a scripted FakeModel."""
        from docuhive.ai import fake, router, routing
        from docuhive.ai.settings import get_ai_settings

        self._env = {k: os.environ.get(k) for k in ("DOCUHIVE_AI_ENABLED", "DOCUHIVE_ENV")}
        os.environ["DOCUHIVE_AI_ENABLED"] = "true" if self.ai is not None else "false"
        os.environ["DOCUHIVE_ENV"] = "test"  # the only place the scripted model answers
        router._MODELS.clear()
        get_ai_settings.cache_clear()
        self._routing_load = routing.load
        tasks = ("triage", "classify", "extract", "chat", "analyse")
        cfg = routing.parse(
            {
                "version": 1,
                "providers": {"test": {"kind": "fake", "local": True}},
                "tasks": {t: {"route": "test/model"} for t in tasks}
                | {"embed": {"route": "test/embed", "dims": 1024}},
                "limits": {"timeout_s": {}, "retries": 0},
            }
        )
        routing.load = lambda: cfg  # type: ignore[method-assign,assignment]
        fake.REGISTRY.clear()
        if self.ai is not None:
            fake.REGISTRY["test/model"] = fake.FakeModel(outputs=self.ai)

    def __exit__(self, *exc: Any) -> None:
        from docuhive.ai import fake, router, routing
        from docuhive.ai.settings import get_ai_settings
        from docuhive.plugins import data, runtime

        routing.load = self._routing_load  # type: ignore[method-assign,assignment]
        fake.REGISTRY.clear()
        router._MODELS.clear()
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_ai_settings.cache_clear()

        runtime.reset()
        for path in self.paths:
            data.drop(path.name)
        shutil.rmtree(self._tmp, ignore_errors=True)

    # Data --------------------------------------------------------------------------------
    def user(self, name: str, *, admin: bool = False) -> CurrentUser:
        from docuhive.auth import create_user

        if name not in self._users:
            user_id = create_user(name, "a synthetic test password", admin=admin)
            self._users[name] = CurrentUser(
                id=user_id, username=name, role="admin" if admin else "member"
            )
        return self._users[name]

    def add(
        self,
        owner: CurrentUser,
        *,
        title: str | None = None,
        document_type: str | None = None,
        category: str | None = None,
        date: Date | None = None,
        facts: dict[str, Any] | None = None,
        content: str = "",
        shared: bool = False,
        original: tuple[str, bytes] | None = None,
    ) -> str:
        """A stored document, as if uploaded and read. Facts: {name: "40"} for numbers and
        strings, {name: ("72.00", "EUR")} for money, {name: date(…)} for dates.
        `original=("statement.xml", data)` stores the file as the document's original."""
        from docuhive import db, documents, vault
        from docuhive.contracts import MetadataPatch
        from docuhive.db.models import Document

        self._count += 1
        doc_id = str(ULID())  # a real id, so links to the document page work
        vault_path, mime = None, "application/pdf"
        if original is not None:
            name, data = original
            folder = vault.root() / "2026" / doc_id
            folder.mkdir(parents=True)
            (folder / f"original{Path(name).suffix or '.bin'}").write_bytes(data)
            vault_path = f"2026/{doc_id}"
            mime = "text/plain" if Path(name).suffix in {".xml", ".csv", ".sta", ".txt"} else mime
        with db.session() as s:
            s.add(
                Document(
                    id=doc_id,
                    owner_id=owner.id,
                    shared=shared,
                    status="stored",
                    sha256=f"{self._count:064d}",
                    mime=mime,
                    vault_path=vault_path,
                    content=content,
                    added_at=datetime.now(UTC),
                )
            )
        values: dict[str, FactValue] = {}
        for name, value in (facts or {}).items():
            if isinstance(value, tuple):
                values[name] = FactValue(type="money", value=value[0], currency=value[1])
            elif isinstance(value, Date):
                values[name] = FactValue(type="date", value=value.isoformat())
            else:
                values[name] = FactValue(
                    type="number" if _numeric(value) else "string", value=str(value)
                )
        documents.apply_metadata(
            doc_id,
            MetadataPatch(
                title=title,
                document_type=document_type,
                category=category,
                document_date=date,
                facts=values or None,
            ),
            actor="system",
        )
        return doc_id

    def document(self, doc_id: str) -> DocumentView:
        from docuhive import documents

        return documents.get(doc_id)

    # Running -----------------------------------------------------------------------------
    def emit(self, event: str, **payload: Any) -> None:
        from docuhive import events

        self._count += 1
        events.emit(event, payload, key=f"test{self._count}")

    def run_jobs(self, limit: int = 100, queues: tuple[str, ...] = ("default",)) -> int:
        """Run the plugins' queued jobs, as the worker would. Returns how many ran. Add
        `queues=("default", "ocr")` to also store generated documents in the vault."""
        from docuhive.jobs.runner import claim, run

        if "ocr" in queues:
            from docuhive.ingest import process  # noqa: F401 - registers the storing job

        ran = 0
        for _ in range(limit):
            job = claim(list(queues))
            if job is None:
                break
            run(job)
            ran += 1
        return ran

    def tool(self, plugin_id: str, name: str) -> Any:
        """A plugin's Ask tool as plain Python: call it with (user, …)."""
        from docuhive.plugins import runtime

        return next(f for f, _ in runtime.LOADED[plugin_id].registry.tools if f.__name__ == name)

    def registry(self, plugin_id: str) -> Any:
        from docuhive.plugins import runtime

        return runtime.LOADED[plugin_id].registry


def _numeric(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True
