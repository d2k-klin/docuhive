"""Vault health, custom fields, saved views, near-duplicates and export against a network-free
storage fake. The same scenarios run on real PostgreSQL in test_archive_tools_integration.py.
"""

import csv
import hashlib
import io
import json
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from docuhive import config, db, duplicates, fields, taxonomy
from docuhive.api.export import cell, filename
from docuhive.db.models import (
    AuditLog,
    Correspondent,
    CustomField,
    DocFact,
    DocSource,
    Document,
    DocumentTag,
    DuplicatePair,
    Job,
    KnowledgeBase,
    Note,
    SavedView,
    Setting,
    Tag,
)
from docuhive.vault import health
from sqlalchemy import BigInteger, DateTime, Integer, String, select, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, REGCONFIG, TSVECTOR
from sqlalchemy.types import JSON

from .test_auth_integration import CSRF, login
from .test_auth_memory import AwareDateTime
from .test_auth_memory import client as auth_client

client = auth_client
DAY = date(2026, 3, 2)


@pytest.fixture
def tools(client, monkeypatch, tmp_path):
    tables = [
        Correspondent.__table__,
        Tag.__table__,
        Document.__table__,
        DocumentTag.__table__,
        DocFact.__table__,
        DocSource.__table__,
        KnowledgeBase.__table__,
        Setting.__table__,
        AuditLog.__table__,
        CustomField.__table__,
        SavedView.__table__,
        DuplicatePair.__table__,
        Note.__table__,
    ]
    originals = [(c, c.type, c.server_default) for t in tables for c in t.columns]
    try:
        for c, original, _ in originals:
            if isinstance(original, BigInteger):
                c.type = original.with_variant(Integer(), "sqlite")
            elif isinstance(original, ARRAY | JSONB):
                c.type = original.with_variant(JSON(), "sqlite")
            elif isinstance(original, REGCONFIG | TSVECTOR):
                c.type = original.with_variant(String(), "sqlite")
                c.server_default = None
            elif isinstance(original, DateTime):
                c.type = original.with_variant(AwareDateTime(), "sqlite")
        db.CoreBase.metadata.create_all(db.get_engine(), tables=tables)
        with db.get_engine().begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE doc_chunks (document_id TEXT, chunk_no INTEGER, "
                    "embed_model TEXT, created_at TIMESTAMP)"
                )
            )
        yield setup(client, monkeypatch, tmp_path)
    finally:
        for c, original, default in originals:
            c.type, c.server_default = original, default


def setup(client, monkeypatch, tmp_path):
    """Shared by the integration module: a synthetic vault and a signed-in owner."""
    vault = tmp_path / "vault"
    (vault / "_system").mkdir(parents=True)
    monkeypatch.setenv("DOCUHIVE_VAULT_DIR", str(vault))
    monkeypatch.setenv("DOCUHIVE_STAGING_DIR", str(tmp_path / "staging"))
    config.reload()
    taxonomy.reload()
    monkeypatch.setattr(duplicates, "similarities", lambda owner_id, doc_id: {})
    login(client)
    client.vault = vault
    return client


def add(
    doc_id,
    *,
    owner=1,
    shared=False,
    title="Synthetic invoice",
    day=DAY,
    sender=None,
    amount=None,
    tags=(),
    files=True,
    category="utilities/electricity",
    vault=None,
):
    original = f"original bytes {doc_id}".encode()
    with db.session() as session:
        sender_id = None
        if sender:
            sender_id = session.scalar(select(Correspondent.id).where(Correspondent.name == sender))
            if sender_id is None:
                row = Correspondent(name=sender, norm_name=sender.lower())
                session.add(row)
                session.flush()
                sender_id = row.id
        session.add(
            Document(
                id=doc_id,
                owner_id=owner,
                shared=shared,
                status="stored",
                sha256=hashlib.sha256(original).hexdigest(),
                mime="application/pdf",
                title=title,
                document_date=day,
                category=category,
                document_type="invoice",
                correspondent_id=sender_id,
                vault_path=f"2026/{doc_id}",
                manual_fields=[],
                fts_config="dh_simple",
                added_at=datetime.now(UTC),
            )
        )
        session.flush()
        session.add(DocSource(document_id=doc_id, kind="upload", original_filename=f"{doc_id}.pdf"))
        if amount:
            session.add(
                DocFact(
                    document_id=doc_id,
                    field="amount_total",
                    type="money",
                    value_text=amount,
                    value_num=Decimal(amount),
                    currency="EUR",
                )
            )
        for name in tags:
            tag_id = session.scalar(select(Tag.id).where(Tag.name == name))
            if tag_id is None:
                tag = Tag(name=name, slug=name)
                session.add(tag)
                session.flush()
                tag_id = tag.id
            session.add(DocumentTag(document_id=doc_id, tag_id=tag_id))
    if files and vault is not None:
        folder = vault / "2026" / doc_id
        folder.mkdir(parents=True)
        (folder / "original.pdf").write_bytes(original)
        (folder / "archive.pdf").write_bytes(b"%PDF-1.7 " + doc_id.encode())
        (folder / "meta.json").write_text(json.dumps({"schema": 1, "id": doc_id}))


def test_vault_health_reports_every_problem_without_changing_files(tools):
    vault = tools.vault
    for doc_id in ["good", "no-archive", "bad-meta", "tampered"]:
        add(doc_id, vault=vault)
    add("no-folder", vault=vault, files=False)
    (vault / "2026" / "no-archive" / "archive.pdf").unlink()
    (vault / "2026" / "bad-meta" / "meta.json").write_text('{"id": "someone-else"}')
    (vault / "2026" / "tampered" / "original.pdf").write_bytes(b"changed")
    (vault / "2026" / "orphan").mkdir()
    before = sorted(p.relative_to(vault) for p in vault.rglob("*"))

    quick = health.scan()
    kinds = {(p.kind, p.document_id) for p in quick.problems}
    assert kinds == {
        ("archive_missing", "no-archive"),
        ("meta_invalid", "bad-meta"),
        ("folder_missing", "no-folder"),
        ("orphan_folder", None),
    }
    assert quick.documents == 5 and quick.hashed == 0 and not quick.ok
    assert all(not p.path.startswith("/") for p in quick.problems)

    full = health.scan(full=True)
    assert ("checksum_mismatch", "tampered") in {(p.kind, p.document_id) for p in full.problems}
    assert full.hashed == 4
    assert sorted(p.relative_to(vault) for p in vault.rglob("*")) == before

    report = tools.get("/api/system/vault/health")
    assert report.status_code == 200 and report.json()["full"] is True
    assert tools.post("/api/system/vault/health?full=true", headers=CSRF).status_code == 202
    with db.session() as session:
        assert session.scalar(select(Job.payload).where(Job.kind == "vault.check")) == {
            "full": True
        }
    login(tools, "other")
    assert tools.get("/api/system/vault/health").status_code == 403


def test_storage_info_says_which_storage_is_used(tools, monkeypatch):
    add("a", vault=tools.vault)
    add("b", vault=tools.vault)
    (tools.vault / "_system" / "VAULT_ID").write_text("vault-123\n")
    info = tools.get("/api/system/storage").json()
    assert info["location"] == str(tools.vault) and info["vault_id"] == "vault-123"
    assert info["documents"] == 2 and info["free_bytes"] > 0 and info["total_bytes"] > 0
    assert info["available"] is False and info["reason"] == "id_mismatch"  # not registered
    # In a container the vault is always /srv/vault: the host path is the useful label.
    monkeypatch.setenv("DOCUHIVE_VAULT_LABEL", "/srv/docuhive/vault (wdnas)")
    config.reload()
    assert tools.get("/api/system/storage").json()["location"] == "/srv/docuhive/vault (wdnas)"
    login(tools, "other")
    assert tools.get("/api/system/storage").status_code == 403


@pytest.fixture
def storage_root(tools, monkeypatch, tmp_path):
    from docuhive import vault

    root = tmp_path / "mnt"
    (root / "photos").mkdir(parents=True)
    (root / "photos" / "cat.jpg").write_text("x")
    (root / "old" / "_system").mkdir(parents=True)
    (root / "old" / "_system" / "VAULT_ID").write_text("someone-else")
    (root / "system-disk").symlink_to("/")  # like macOS /Volumes/Macintosh HD
    monkeypatch.setenv("DOCUHIVE_STORAGE_ROOT", str(root))
    monkeypatch.setenv("DOCUHIVE_STORAGE_ROOT_LABEL", "/mnt")
    config.reload()
    vault.forget_chosen()
    yield root
    vault.forget_chosen()


def test_choosing_storage_without_a_storage_root_is_refused(tools):
    assert tools.get("/api/system/storage").json()["choosable"] is False
    r = tools.get("/api/system/storage/folders")
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_storage_root"


def test_choose_an_empty_folder_for_an_empty_archive(tools, storage_root):
    from docuhive import vault

    assert tools.get("/api/system/storage").json()["choosable"] is True
    made = tools.post("/api/system/storage/folders", json={"name": "docuhive"}, headers=CSRF)
    assert made.status_code == 201 and made.json()["state"] == "empty"
    states = {
        f["name"]: f["state"] for f in tools.get("/api/system/storage/folders").json()["folders"]
    }
    assert states == {"docuhive": "empty", "old": "other_vault", "photos": "not_empty"}
    info = tools.post("/api/system/storage/choose", json={"path": "docuhive"}, headers=CSRF)
    assert info.status_code == 200, info.text
    body = info.json()
    assert body["location"] == "/mnt/docuhive" and body["available"] is True
    assert (storage_root / "docuhive" / "_system" / "VAULT_ID").read_text() == body["vault_id"]
    assert vault.root() == (storage_root / "docuhive").resolve()
    listing = tools.get("/api/system/storage/folders").json()
    assert listing["current"] == "docuhive" and listing["root"] == "/mnt"


def test_unsafe_storage_choices_are_refused(tools, storage_root):
    def code(path):
        r = tools.post("/api/system/storage/choose", json={"path": path}, headers=CSRF)
        return r.status_code, r.json()["error"]["code"]

    assert code("photos") == (409, "not_empty")
    assert code("old") == (409, "other_vault")
    assert code("../vault") == (409, "outside_storage_root")
    assert code("missing") == (404, "not_found")
    bad = tools.post("/api/system/storage/folders", json={"name": "../x"}, headers=CSRF)
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "invalid_name"
    add("a", vault=tools.vault)  # an archive with documents keeps its storage
    (storage_root / "new").mkdir()
    assert code("new") == (409, "archive_not_empty")
    login(tools, "other")
    assert (
        tools.post("/api/system/storage/choose", json={"path": "new"}, headers=CSRF).status_code
        == 403
    )


def test_the_archives_own_vault_found_elsewhere_can_be_chosen(tools, storage_root):
    """A share mounted at a new place: same vault ID, so the documents come along."""
    from docuhive import vault

    first = tools.post("/api/system/storage/folders", json={"name": "share"}, headers=CSRF)
    assert first.status_code == 201
    vault_id = tools.post(
        "/api/system/storage/choose", json={"path": "share"}, headers=CSRF
    ).json()["vault_id"]
    add("a", vault=storage_root / "share")
    (storage_root / "share").rename(storage_root / "moved")
    vault.forget_chosen()
    states = {
        f["name"]: f["state"] for f in tools.get("/api/system/storage/folders").json()["folders"]
    }
    assert states["moved"] == "this_vault"
    info = tools.post("/api/system/storage/choose", json={"path": "moved"}, headers=CSRF).json()
    assert info["vault_id"] == vault_id and info["location"] == "/mnt/moved"


def test_storage_kind_from_mountinfo():
    from pathlib import Path

    from docuhive.api.system import storage_kind

    table = (
        "22 1 8:1 / / rw - ext4 /dev/sda1 rw\n"
        "40 22 0:50 / /srv/vault rw - nfs4 wdnas.local:/nfs/docuhive rw\n"
        "41 22 0:51 / /srv/staging rw - ext4 /dev/sda1 rw\n"
    )
    assert storage_kind(Path("/srv/vault"), table) == "network"
    assert storage_kind(Path("/srv/vault/2026"), table) == "network"
    assert storage_kind(Path("/srv/staging"), table) == "local"
    assert storage_kind(Path("/srv/vaultx"), table) == "local"  # a prefix is not a mount
    assert storage_kind(Path("/srv/vault"), "") is None
    spaced = table + "42 22 0:52 / /mnt/NAS\\040Archive rw - cifs //nas/archive rw\n"
    assert storage_kind(Path("/mnt/NAS Archive/vault"), spaced) == "network"
    desktop = "40 22 0:50 / /srv/vault rw - fuse.sshfs :/Users/me rw\n"
    assert storage_kind(Path("/srv/vault"), desktop) is None  # Docker Desktop: unknowable


def test_unmounted_vault_is_one_problem(tools):
    add("a", vault=tools.vault)
    add("b", vault=tools.vault)
    (tools.vault / "_system").rmdir()
    report = health.scan(full=True)
    assert [p.kind for p in report.problems] == ["vault_unavailable"]
    assert report.documents == 2


def test_custom_fields_extend_extraction_and_stay_admin_only(tools):
    tax = taxonomy.load()
    builtin = tax.document_types[0].facts[0].name
    field = {
        "name": "warranty_end",
        "label": "Warranty end",
        "type": "date",
        "document_types": ["invoice"],
        "remind_days_before": [30],
    }
    created = tools.post("/api/custom-fields", json=field, headers=CSRF)
    assert created.status_code == 201, created.text
    field_id = created.json()["id"]
    assert tools.post("/api/custom-fields", json=field, headers=CSRF).json()["error"]["code"] == (
        "field_name_taken"
    )
    clash = {**field, "name": builtin, "document_types": []}
    assert tools.post("/api/custom-fields", json=clash, headers=CSRF).status_code == 409
    unknown = {**field, "name": "x", "document_types": ["no-such-type"]}
    assert tools.post("/api/custom-fields", json=unknown, headers=CSRF).status_code == 422
    reminder = {**field, "name": "plate", "type": "string"}
    assert tools.post("/api/custom-fields", json=reminder, headers=CSRF).json()["error"][
        "code"
    ] == ("field_reminder_needs_date")

    invoice = fields.document_type(tax, "invoice")
    added = invoice.facts[-1]
    assert (added.name, added.type, added.remind_days_before) == ("warranty_end", "date", [30])
    other = next(t.id for t in tax.document_types if t.id != "invoice")
    assert "warranty_end" not in {f.name for f in fields.document_type(tax, other).facts}
    assert "warranty_end" not in {f.name for f in taxonomy.document_type(tax, "invoice").facts}

    edited = tools.patch(
        f"/api/custom-fields/{field_id}", json={"label": "Guarantee ends"}, headers=CSRF
    )
    assert edited.json()["label"] == "Guarantee ends" and edited.json()["name"] == "warranty_end"
    login(tools, "other")
    assert tools.get("/api/custom-fields").json()[0]["name"] == "warranty_end"
    assert tools.delete(f"/api/custom-fields/{field_id}", headers=CSRF).status_code == 403
    login(tools)
    assert tools.delete(f"/api/custom-fields/{field_id}", headers=CSRF).status_code == 204
    assert fields.document_type(tax, "invoice").facts == invoice.facts[:-1]


def test_saved_views_share_filters_not_documents(tools):
    add("mine", sender="Utility Co", tags=["home"])
    add("household", owner=2, shared=True)
    add("private-other", owner=2)
    add("insurance", category="insurance")
    view = {"name": "Power", "filters": {"categories": ["utilities"]}, "shared": True}
    created = tools.post("/api/views", json=view, headers=CSRF)
    assert created.status_code == 201, created.text
    view_id = created.json()["id"]
    private = tools.post("/api/views", json={"name": "Mine"}, headers=CSRF).json()["id"]
    bad = {"name": "Bad", "filters": {"categories": ["no-such-category"]}}
    assert tools.post("/api/views", json=bad, headers=CSRF).status_code == 422

    page = tools.get(f"/api/views/{view_id}/documents").json()
    assert page["total"] == 2 and {d["id"] for d in page["items"]} == {"mine", "household"}
    mine = next(d for d in page["items"] if d["id"] == "mine")
    assert (mine["correspondent"], mine["tags"]) == ("Utility Co", ["home"])
    first = tools.get(f"/api/views/{view_id}/documents?limit=1").json()
    assert len(first["items"]) == 1 and first["next_offset"] == 1

    login(tools, "other")
    assert [v["id"] for v in tools.get("/api/views").json()] == [view_id]
    assert tools.get(f"/api/views/{private}").status_code == 404
    other_page = tools.get(f"/api/views/{view_id}/documents").json()
    assert {d["id"] for d in other_page["items"]} == {"household", "private-other"}
    assert "mine" not in {d["id"] for d in other_page["items"]}
    assert tools.patch(f"/api/views/{view_id}", json={"name": "X"}, headers=CSRF).status_code == 403
    login(tools)
    renamed = tools.patch(f"/api/views/{view_id}", json={"pinned": False}, headers=CSRF)
    assert renamed.json()["pinned"] is False and renamed.json()["name"] == "Power"
    assert tools.delete(f"/api/views/{view_id}", headers=CSRF).status_code == 204


def test_duplicate_rules():
    doc = {"correspondent_id": 1, "document_date": DAY}
    same = {"correspondent_id": 1, "document_date": DAY + timedelta(days=2)}
    later = {"correspondent_id": 1, "document_date": DAY + timedelta(days=31)}
    money = {("84.20", "EUR")}
    close = duplicates.signals(doc, same, money, money, None)
    assert close == ["same_sender", "same_amount", "close_date"]
    assert duplicates.is_duplicate(close, None, dates_known=True)
    monthly = duplicates.signals(doc, later, money, money, 0.99)
    assert not duplicates.is_duplicate(monthly, 0.99, dates_known=True)
    assert not duplicates.is_duplicate(["same_sender", "close_date"], None, dates_known=True)
    assert duplicates.is_duplicate(["close_date"], 0.98, dates_known=True)
    undated = ["same_sender", "same_amount"]
    assert not duplicates.is_duplicate(undated, None, dates_known=False)
    assert duplicates.is_duplicate([*undated, "similar_content"], 0.93, dates_known=False)


def test_duplicate_scan_and_decisions(tools, monkeypatch):
    add("a-email", sender="Utility Co", amount="84.20")
    add("b-scan", sender="Utility Co", amount="84.20", day=DAY + timedelta(days=2))
    add("c-next-month", sender="Utility Co", amount="84.20", day=DAY + timedelta(days=31))
    add("d-other-owner", owner=2, sender="Utility Co", amount="84.20")
    add("e-copy", sender="Someone", day=DAY + timedelta(days=1))
    monkeypatch.setattr(
        duplicates,
        "similarities",
        lambda owner_id, doc_id: {"e-copy": 0.98} if doc_id == "a-email" else {},
    )
    assert duplicates.scan("a-email") == 2
    assert duplicates.scan("a-email") == 0
    assert duplicates.scan("missing") == 0
    pairs = tools.get("/api/duplicates").json()
    assert {(p["document"]["id"], p["other"]["id"]) for p in pairs} == {
        ("a-email", "b-scan"),
        ("a-email", "e-copy"),
    }
    scan_pair = next(p for p in pairs if p["other"]["id"] == "b-scan")
    assert scan_pair["reasons"] == ["same_sender", "same_amount", "close_date"]
    assert scan_pair["document"]["correspondent"] == "Utility Co"

    login(tools, "other")
    assert tools.get("/api/duplicates").json() == []
    assert (
        tools.post(
            f"/api/duplicates/{scan_pair['id']}", json={"status": "dismissed"}, headers=CSRF
        ).status_code
        == 404
    )
    login(tools)
    decided = tools.post(
        f"/api/duplicates/{scan_pair['id']}", json={"status": "dismissed"}, headers=CSRF
    )
    assert decided.status_code == 204
    assert duplicates.scan("b-scan") == 0  # a dismissed pair is never reopened
    assert [p["other"]["id"] for p in tools.get("/api/duplicates").json()] == ["e-copy"]
    with db.session() as session:
        assert session.scalar(select(Document.id).where(Document.id == "b-scan")) == "b-scan"
    duplicates.queue_scan("a-email")
    with db.session() as session:
        assert session.scalar(select(Job.kind).where(Job.kind == "duplicates.scan"))


def read_zip(response):
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    rows = list(csv.DictReader(io.StringIO(archive.read("documents.csv").decode("utf-8-sig"))))
    return archive, rows


def test_export_zip_csv_and_boundaries(tools):
    vault = tools.vault
    add("one", sender="Utility Co", amount="84.20", tags=["home"], vault=vault)
    add("evil", title='=HYPERLINK("http://x")', vault=vault)
    add("no-file", files=False, vault=vault)
    add("private-other", owner=2, vault=vault)
    add("insurance", category="insurance", vault=vault)
    response = tools.post(
        "/api/export", json={"filters": {"categories": ["utilities"]}}, headers=CSRF
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    archive, rows = read_zip(response)
    assert {r["id"] for r in rows} == {"one", "evil", "no-file"}
    one = next(r for r in rows if r["id"] == "one")
    assert (one["correspondent"], one["tags"], one["fact:amount_total"]) == (
        "Utility Co",
        "home",
        "84.20 EUR",
    )
    assert archive.read(one["file"]) == b"%PDF-1.7 one"
    assert next(r for r in rows if r["id"] == "evil")["title"].startswith("'=")
    assert "no-file" in archive.read("MISSING.txt").decode()
    assert all(not n.startswith("/") and ".." not in n for n in archive.namelist())

    view_id = tools.post(
        "/api/views",
        json={"name": "Insurance", "filters": {"categories": ["insurance"]}},
        headers=CSRF,
    ).json()["id"]
    by_view = tools.post("/api/export", json={"view_id": view_id}, headers=CSRF)
    assert [r["id"] for r in read_zip(by_view)[1]] == ["insurance"]
    both = {"view_id": view_id, "filters": {"categories": ["insurance"]}}
    assert tools.post("/api/export", json=both, headers=CSRF).status_code == 422
    empty = {"filters": {"categories": ["utilities"], "date_from": "2030-01-01"}}
    assert tools.post("/api/export", json=empty, headers=CSRF).json()["error"]["code"] == (
        "export_empty"
    )
    assert tools.post("/api/export", json={"view_id": 999}, headers=CSRF).status_code == 404
    with db.session() as session:
        audits = list(session.scalars(select(AuditLog.after).where(AuditLog.action == "export")))
    assert [a["documents"] for a in audits] == [3, 1]


def test_export_cells_and_names():
    assert cell("=1+1") == "'=1+1" and cell("-5") == "'-5" and cell(None) == ""
    assert cell("Invoice") == "Invoice"

    class Row:
        id, title, document_date = "01JCAAAAAAAAAAAAAAAAAAAAAA", "../../etc/passwd", None

    used: set[str] = set()
    first = filename(Row, used)
    assert "/" not in first and first.startswith("undated ") and first.endswith(").pdf")
    assert filename(Row, used) != first
