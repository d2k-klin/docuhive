"""Plugin platform, part 2 on PostgreSQL: events, taxonomy, SDK documents, tools, tables."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from docuhive import config, events, jobs, taxonomy, vault
from docuhive.auth import create_user
from docuhive.contracts import CurrentUser, FactValue, MetadataPatch
from docuhive.db import session
from docuhive.db.models import Document, Job, PluginState
from docuhive.plugins import data, discovery, runtime, state
from docuhive.plugins.check import check
from sqlalchemy import select, text

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[4]
LEDGER = """id: ledger
name: Ledger
version: 0.1.0
requires_sdk: ">=1,<2"
capabilities: [documents:read, documents:write-metadata]
snapshot: true
taxonomy:
  categories:
    - {id: utilities, label: Already in the core}
    - {id: hobbies, label: Hobbies}
  document_types:
    - id: fuel_receipt
      label: Fuel receipt
      facts: [{name: litres, type: number}]
    - id: invoice
      label: ignored, the core defines it
      facts: [{name: cost_centre, type: string}]
"""
PLUGIN_PY = '''
from docuhive.sdk import Registry, documents


def setup(registry: Registry) -> None:
    @registry.on("document.stored")
    def first(event) -> None:
        documents.apply_metadata(event.document_id, tags_add=["seen-by-ledger"])

    @registry.on("document.stored")
    def second(event) -> None:
        raise RuntimeError("this listener always fails")

    @registry.tool
    def litres(user, year: int, exclude_ids: set | None = None) -> dict:
        """Fuel bought in a year."""
        docs = [d for d in documents.find(user, document_type="fuel_receipt", year=year)
                if d.id not in (exclude_ids or set())]
        return {"documents": [d.id for d in docs], "count": len(docs)}

    @registry.job("tally")
    def tally(payload, ctx) -> None:
        with registry.db.session() as s:
            from sqlalchemy import text
            s.execute(text("INSERT INTO trips (owner_id, km) VALUES (:o, :k)"), payload)
'''
MIGRATIONS = {
    "001_trips.sql": "CREATE TABLE cars (id bigserial PRIMARY KEY, owner_id bigint NOT NULL,"
    " plate text);\n"
    "CREATE TABLE trips (id bigserial PRIMARY KEY, owner_id bigint NOT NULL,"
    " car_id bigint REFERENCES cars(id), km numeric NOT NULL, day date);\n",
    "002_note.sql": "ALTER TABLE trips ADD COLUMN note text;\n",
}


@pytest.fixture
def ledger(postgres, monkeypatch, tmp_path):
    folder = tmp_path / "plugins" / "ledger"
    (folder / "migrations").mkdir(parents=True)
    (folder / "plugin.yaml").write_text(LEDGER)
    (folder / "plugin.py").write_text(PLUGIN_PY)
    (folder / "README.md").write_text("# Ledger\n")
    for name, sql in MIGRATIONS.items():
        (folder / "migrations" / name).write_text(sql)
    monkeypatch.setenv("DOCUHIVE_PLUGINS_DIR", str(folder.parent))
    monkeypatch.setenv("DOCUHIVE_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("DOCUHIVE_STAGING_DIR", str(tmp_path / "staging"))
    config.reload()
    runtime.reset()
    data.drop("ledger")
    owner = create_user("owner", "a synthetic strong password")
    other = create_user("other", "a synthetic strong password")
    found = discovery.find("ledger")
    assert found and found.manifest
    state.enable("ledger", found.manifest.capability_names(), actor="test")
    runtime.start("worker")
    assert "ledger" in runtime.LOADED, state.states()["ledger"].last_error
    yield folder, owner, other
    runtime.reset()
    data.drop("ledger")


def add_document(doc_id: str, owner: int, *, document_type=None, shared=False, date=None) -> None:
    with session() as db:
        db.add(
            Document(
                id=doc_id,
                owner_id=owner,
                shared=shared,
                status="stored",
                sha256=doc_id.ljust(64, "0"),
                mime="application/pdf",
                document_type=document_type,
                document_date=date,
            )
        )


def run_jobs(kind_prefix: str) -> list[SimpleNamespace]:
    """Run every queued job whose kind starts with the prefix, through the real queue."""
    from docuhive.jobs.runner import claim, run

    for _ in range(50):
        with session() as db:
            waiting = db.scalar(
                select(Job.id).where(
                    Job.kind.like(f"{kind_prefix}%"),
                    Job.status == "pending",
                    Job.run_after <= datetime.now(UTC),
                )
            )
        if waiting is None:
            break
        job = claim(["default"])  # plugin jobs; the core's own event job waits on "ai"
        if job is None:
            break
        run(job)
    with session() as db:
        rows = db.execute(
            select(Job.kind, Job.status, Job.last_error).where(Job.kind.like(f"{kind_prefix}%"))
        ).all()
    return [SimpleNamespace(kind=k, status=st, last_error=e) for k, st, e in rows]


def test_each_listener_gets_its_own_job_in_the_same_transaction(ledger):
    _, owner, _ = ledger
    add_document("d1", owner)
    jobs.enqueue("document.stored", {"document_id": "d1"}, queue="ai")
    listeners = run_jobs("event:plugin:ledger:")
    by_kind = {j.kind: j for j in listeners}
    assert set(by_kind) == {
        "event:plugin:ledger:first:document.stored",
        "event:plugin:ledger:second:document.stored",
    }
    first = by_kind["event:plugin:ledger:first:document.stored"]
    assert first.status == "done", first.last_error
    failing = by_kind["event:plugin:ledger:second:document.stored"]
    assert failing.status == "pending" and "always fails" in (failing.last_error or "")
    from docuhive import documents

    assert documents.get("d1").tags == ["seen-by-ledger"]
    # A rolled-back change takes its events with it.
    with pytest.raises(RuntimeError), session() as db:
        jobs.enqueue("document.stored", {"document_id": "gone"}, in_session=db)
        raise RuntimeError("roll back")
    with session() as db:
        assert not db.scalar(select(Job.id).where(Job.payload["document_id"].astext == "gone"))
    # The same occurrence emitted twice runs a listener once.
    events.subscribe("ledger.done", "test", lambda e: None)
    events.emit("ledger.done", {"n": 1}, key="once")
    events.emit("ledger.done", {"n": 1}, key="once")
    with session() as db:
        assert db.scalar(select(Job.id).where(Job.kind == "event:test:ledger.done").limit(2))
        count = db.scalar(text("SELECT count(*) FROM jobs WHERE kind = 'event:test:ledger.done'"))
    assert count == 1
    events.unsubscribe("event:test:ledger.done")


def test_taxonomy_contributions_add_but_never_change(ledger):
    tax = taxonomy.load()
    hobbies = next(c for c in tax.categories if c.id == "hobbies")
    utilities = next(c for c in tax.categories if c.id == "utilities")
    fuel = next(t for t in tax.document_types if t.id == "fuel_receipt")
    invoice = next(t for t in tax.document_types if t.id == "invoice")
    assert hobbies.source == "plugin:ledger" and utilities.source is None
    assert utilities.label != "Already in the core"
    assert fuel.source == "plugin:ledger" and [f.name for f in fuel.facts] == ["litres"]
    assert invoice.label != "ignored, the core defines it"
    assert "cost_centre" in [f.name for f in invoice.facts]
    runtime.reset()
    assert "hobbies" not in [c.id for c in taxonomy.load().categories]


def test_find_respects_visibility_and_metadata_respects_people(ledger, monkeypatch):
    _, owner, other = ledger
    add_document("mine", owner, document_type="fuel_receipt", date=datetime(2026, 3, 1, tzinfo=UTC))
    add_document(
        "theirs", other, document_type="fuel_receipt", date=datetime(2026, 3, 1, tzinfo=UTC)
    )
    add_document("shared", other, document_type="fuel_receipt", shared=True)
    from docuhive import documents as core

    core.apply_metadata("mine", MetadataPatch(title="My title"), actor=f"user:{owner}")
    tool = runtime.LOADED["ledger"].registry.tools[0][0]
    user = CurrentUser(id=owner, username="owner", role="member")
    result = tool(user, year=2026)
    assert sorted(result["documents"]) == ["mine", "shared"]  # never "theirs"
    # A plugin never overwrites what a person set.
    from docuhive.sdk import documents

    registry = runtime.LOADED["ledger"].registry
    monkeypatch.setattr(documents, "current", lambda: registry)
    applied = documents.apply_metadata(
        "mine", title="Plugin title", facts={"litres": FactValue(type="number", value="40")}
    )
    assert applied == ["facts.litres"]
    view = core.get("mine")
    assert view.title == "My title" and view.facts["litres"].value == "40"
    assert "facts.litres" not in view.manual_fields


def test_ask_tool_hides_restricted_documents_from_cloud_models(ledger):
    from docuhive.plugins.install import _tool

    registry = runtime.LOADED["ledger"].registry
    fn = registry.tools[0][0]
    calls = []

    def spy(user, year: int, exclude_ids: set | None = None) -> dict:
        calls.append(exclude_ids)
        return {"documents": ["private-doc", "plain-doc"]}

    spy.__doc__ = fn.__doc__
    wrapped = _tool(registry, spy, "the user", None, {"private-doc"})
    assert list(__import__("inspect").signature(wrapped).parameters) == ["year"]
    assert wrapped(year=2026) == {"withheld": 1, "summary": "1 restricted documents not included"}
    assert calls == [{"private-doc"}]
    local = _tool(registry, spy, "the user", None, set())
    assert local(year=2026)["documents"] == ["private-doc", "plain-doc"]


def test_tables_migrate_once_snapshot_and_restore(ledger):
    folder, owner, _ = ledger
    with session() as db:
        assert db.get(PluginState, "ledger").migration == 2
    registry = runtime.LOADED["ledger"].registry
    with registry.db.session() as s:
        car = s.scalar(
            text("INSERT INTO cars (owner_id, plate) VALUES (:o, 'B-1') RETURNING id"), {"o": owner}
        )
        s.execute(
            text(
                "INSERT INTO trips (owner_id, car_id, km, day, note) "
                "VALUES (:o, :c, 12.5, '2026-03-01', 'x')"
            ),
            {"o": owner, "c": car},
        )
    registry.enqueue("tally", {"o": owner, "k": 7})
    run_jobs("plugin:ledger:tally")
    assert data.migrate("ledger", folder) == 2  # nothing applied twice
    vault.init()
    path = data.snapshot("ledger")
    assert path and path.parent == vault.root() / "_system" / "plugins" / "ledger"
    with registry.db.session() as s:
        s.execute(text("DELETE FROM trips"))
        s.execute(text("DELETE FROM cars"))
    assert data.restore("ledger") == 3
    with registry.db.session() as s:
        rows = s.execute(text("SELECT km, day, note FROM trips ORDER BY id")).all()
        new_id = s.scalar(text("INSERT INTO cars (owner_id) VALUES (1) RETURNING id"))
    assert [(str(r.km), str(r.day), r.note) for r in rows] == [
        ("12.5", "2026-03-01", "x"),
        ("7", "None", None),
    ]
    assert new_id == car + 1  # ids continue after the restored ones


def test_check_reports_unsafe_migrations(tmp_path):
    folder = tmp_path / "unsafe"
    (folder / "migrations").mkdir(parents=True)
    (folder / "plugin.yaml").write_text(
        LEDGER.replace("ledger", "unsafe").replace("snapshot: true\n", "")
    )
    (folder / "README.md").write_text("x")
    (folder / "migrations" / "001_x.sql").write_text(
        "CREATE TABLE notes (id bigserial PRIMARY KEY, body text);\n"
        "INSERT INTO public.settings(key) VALUES ('x');\nDROP TABLE notes;\n"
    )
    (folder / "migrations" / "003_gap.sql").write_text("SELECT 1;\n")
    problems = "\n".join(check(folder))
    assert "table notes has no owner_id" in problems
    assert "refers to public.settings" in problems
    assert "drops data" in problems
    assert "without gaps" in problems
    assert "no way to get them back" in problems


def test_school_example_tags_school_letters(postgres, monkeypatch):
    monkeypatch.setenv("DOCUHIVE_ENV", "dev")
    monkeypatch.setenv("DOCUHIVE_PLUGINS_DEV", "1")
    monkeypatch.setenv("DOCUHIVE_PLUGINS_DIR", str(ROOT / "tmp" / "no-plugins"))
    config.reload()
    runtime.reset()
    owner = create_user("parent", "a synthetic strong password")
    found = discovery.find("schule")
    assert found and found.loadable, found and found.problems
    state.enable("schule", found.manifest.capability_names(), actor="test")
    runtime.start("worker")
    try:
        assert "school_letter" in [t.id for t in taxonomy.load().document_types]
        add_document("letter", owner, document_type="school_letter")
        add_document("bill", owner, document_type="invoice")
        for doc_id, kind in (("letter", "school_letter"), ("bill", "invoice")):
            events.emit(
                "document.classified", {"document_id": doc_id, "document_type": kind}, key=doc_id
            )
        run_jobs("event:plugin:schule:")
        from docuhive import documents

        assert documents.get("letter").tags == ["school"]
        assert documents.get("bill").tags == []
    finally:
        runtime.reset()
    assert json.loads(json.dumps(check(found.path))) == []


def test_use_in_ask_switch_removes_the_plugins_tools(ledger):
    from docuhive.agents.tools import build_tools
    from docuhive.ai.router import Route
    from docuhive.api.plugins import AskIn, list_plugins, use_in_ask
    from docuhive.contracts import SearchFilters

    _, owner, _ = ledger
    admin = CurrentUser(id=owner, username="owner", role="admin")
    user = CurrentUser(id=owner, username="owner", role="member")

    def names() -> set[str]:
        return {t.tool_name for t in build_tools(user, SearchFilters(), Route("l", "m", True))}

    assert {p.id: p.in_ask for p in list_plugins(admin)} == {"ledger": True}
    assert any(n.startswith("ledger__") for n in names())
    assert use_in_ask("ledger", AskIn(use=False), admin).in_ask is False
    assert not any(n.startswith("ledger__") for n in names())
    assert use_in_ask("ledger", AskIn(use=True), admin).in_ask is True
    assert any(n.startswith("ledger__") for n in names())
