"""Holds on PostgreSQL: nobody changes a held record, only an administrator lifts a hold, and
holds survive a rebuild from the vault."""

from datetime import date

import pytest
from docuhive import documents
from docuhive.api.app import create_app
from docuhive.contracts import MetadataPatch
from docuhive.db import session
from docuhive.db.models import AuditLog, DocumentHold
from docuhive.documents.holds import Held
from docuhive.sdk.testing import Archive
from docuhive.vault import meta, rebuild
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

pytestmark = pytest.mark.integration
CSRF = {"X-DocuHive-CSRF": "1"}
PLUGIN = """id: holder
name: Holder
version: 0.1.0
requires_sdk: ">=1,<2"
capabilities: [documents:read, documents:write-metadata, documents:hold]
"""
PLUGIN_PY = """
from docuhive.sdk import Registry, documents, retention


def setup(registry: Registry) -> None:
    @registry.action("lock")
    def lock(user, params):
        fields = params.get("fields")
        until = retention.until("booking_document", 2026) if params.get("retain") else None
        return str(documents.hold(params["id"], "Issued invoice", fields=fields, until=until))

    @registry.action("retitle")
    def retitle(user, params):
        return ",".join(documents.apply_metadata(params["id"], title=params["title"]))
"""


@pytest.fixture
def archive(tmp_path):
    folder = tmp_path / "plugins" / "holder"
    folder.mkdir(parents=True)
    (folder / "plugin.yaml").write_text(PLUGIN)
    (folder / "plugin.py").write_text(PLUGIN_PY)
    with Archive(folder) as made:
        yield made


def act(archive, name, user, **params):
    return archive.registry("holder").actions[name][0](user, params)


def signed_in(name):
    client = TestClient(create_app(), base_url="https://testserver")
    response = client.post(
        "/api/auth/login",
        json={"username": name, "password": "a synthetic test password"},
        headers=CSRF,
    )
    assert response.status_code == 204
    return client


def test_a_held_document_cannot_change_until_an_administrator_lifts_it(archive):
    alice = archive.user("alice")
    archive.user("admin", admin=True)
    doc = archive.add(
        alice, title="Invoice 7", facts={"amount_total": ("119.00", "EUR")}, shared=True
    )

    # Only the title is held: the title is refused for a person, tags still change.
    act(archive, "lock", alice, id=doc, fields=["title"])
    with pytest.raises(Held, match="Issued invoice"):
        documents.apply_metadata(doc, MetadataPatch(title="Changed"), actor=f"user:{alice.id}")
    documents.apply_metadata(doc, MetadataPatch(tags_add=["paid"]), actor=f"user:{alice.id}")

    # Everything held, with a retention date: AI, plugins, people and trash are all refused.
    act(archive, "lock", alice, id=doc, retain=True)
    for actor in ("ai:extract", "plugin:other", f"user:{alice.id}"):
        with pytest.raises(Held):
            documents.apply_metadata(doc, MetadataPatch(tags_add=["x"]), actor=actor, force=True)
    with pytest.raises(Held):
        act(archive, "retitle", alice, id=doc, title="By a plugin")
    with pytest.raises(Held):
        documents.set_trashed(doc, alice, True)
    assert archive.document(doc).title == "Invoice 7" and archive.document(doc).deleted_at is None

    # Through the API: a plain refusal, the lock on the detail, and bulk edit skips it.
    client = signed_in("alice")
    refused = client.patch(f"/api/documents/{doc}", json={"title": "Nope"}, headers=CSRF)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "document_held"
    assert refused.json()["error"]["details"]["fields"] == ["title"]
    assert [h["reason"] for h in client.get(f"/api/documents/{doc}").json()["holds"]] == [
        "Issued invoice",
        "Issued invoice",
    ]
    bulk = client.post(
        "/api/documents/bulk", json={"ids": [doc], "patch": {"tags_add": ["y"]}}, headers=CSRF
    )
    assert bulk.json() == {"updated": 0, "skipped": [doc]}
    assert client.post(f"/api/documents/{doc}/trash", headers=CSRF).status_code == 409

    # A member cannot lift; an administrator can, with a reason that stays in the history.
    holds = client.get(f"/api/documents/{doc}/holds").json()
    lift = f"/api/documents/{doc}/holds/{{}}/lift"
    reason = {"reason": "Wrong document locked by mistake"}
    assert client.post(lift.format(holds[0]["id"]), json=reason, headers=CSRF).status_code == 403
    administrator = signed_in("admin")
    assert (
        administrator.post(
            lift.format(holds[0]["id"]), json={"reason": ""}, headers=CSRF
        ).status_code
        == 422
    )
    for hold in holds:
        lifted = administrator.post(lift.format(hold["id"]), json=reason, headers=CSRF)
        assert lifted.status_code == 200 and lifted.json()["lift_reason"] == reason["reason"]
    assert (
        administrator.post(lift.format(holds[0]["id"]), json=reason, headers=CSRF).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/documents/{doc}", json={"title": "Invoice 7a"}, headers=CSRF
        ).status_code
        == 200
    )
    history = [e["action"] for e in client.get(f"/api/documents/{doc}/history").json()]
    assert history.count("hold") == 2 and history.count("hold_lifted") == 2


def test_holds_are_in_meta_json_and_survive_a_rebuild(archive):
    alice = archive.user("alice")
    doc = archive.add(alice, title="Filed return", original=("return.xml", b"<x/>"))
    act(archive, "lock", alice, id=doc, retain=True)
    rendered = meta.render(doc)
    assert [(h.reason, h.until) for h in rendered.holds] == [("Issued invoice", date(2034, 12, 31))]

    with session() as s:
        s.execute(delete(DocumentHold).where(DocumentHold.document_id == doc))
        rebuild.upsert(s, rendered, "2026/" + doc, "", [])
    with pytest.raises(Held):
        documents.apply_metadata(doc, MetadataPatch(title="x"), actor=f"user:{alice.id}")

    with session() as s:
        actions = s.scalars(select(AuditLog.action).where(AuditLog.document_id == doc)).all()
    assert "hold" in actions
