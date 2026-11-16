"""Guest links: read-only, no cookie, fixed list, logged, expiring, throttled, off by default."""

from datetime import UTC, datetime, timedelta

import pytest
from docuhive import config, vault
from docuhive.api import guest as guest_api
from docuhive.api.app import create_app
from docuhive.db import session
from docuhive.db.models import AuditLog, Document, GuestLink
from docuhive.sdk._plugin import NotInteractive
from docuhive.sdk.testing import Archive
from fastapi.testclient import TestClient
from sqlalchemy import select, update

pytestmark = pytest.mark.integration
CSRF = {"X-DocuHive-CSRF": "1"}
PLUGIN = """id: advisor
name: Advisor
version: 0.1.0
requires_sdk: ">=1,<2"
capabilities: [documents:read]
"""
PLUGIN_PY = """
from docuhive.sdk import Registry, guest_links


def setup(registry: Registry) -> None:
    @registry.action("share")
    def share(user, params):
        return guest_links.create(user, "For the advisor", params["ids"], 3)["path"]
"""


def signed_in(name):
    client = TestClient(create_app(), base_url="https://testserver")
    client.post(
        "/api/auth/login",
        json={"username": name, "password": "a synthetic test password"},
        headers=CSRF,
    )
    return client


@pytest.fixture
def archive(tmp_path, monkeypatch):
    folder = tmp_path / "plugins" / "advisor"
    folder.mkdir(parents=True)
    (folder / "plugin.yaml").write_text(PLUGIN)
    (folder / "plugin.py").write_text(PLUGIN_PY)
    guest_api.limiter.failures.clear()
    with Archive(folder) as made:
        yield made, monkeypatch
    monkeypatch.delenv("DOCUHIVE_GUEST_LINKS", raising=False)
    config.reload()


def with_pdf(archive, owner, **doc):
    doc_id = archive.add(owner, original=("scan.pdf", b"%PDF-1.4 original"), **doc)
    (vault.root() / "2026" / doc_id / "archive.pdf").write_bytes(b"%PDF-1.4 archive")
    return doc_id


def test_guest_links(archive):
    archive, monkeypatch = archive
    alice = archive.user("alice")
    archive.user("bob")
    invoice = with_pdf(archive, alice, title="Invoice 7", shared=False)
    medical = with_pdf(archive, alice, title="Lab results", category="health")
    owner = signed_in("alice")
    body = {"label": "Tax 2026", "document_ids": [invoice], "days": 7}

    assert owner.post("/api/guest-links", json=body, headers=CSRF).status_code == 403  # off

    monkeypatch.setenv("DOCUHIVE_GUEST_LINKS", "true")
    config.reload()
    assert owner.post("/api/guest-links", json=body | {"days": 31}, headers=CSRF).status_code == 422
    made = owner.post("/api/guest-links", json=body, headers=CSRF)
    assert made.status_code == 201
    path = made.json()["path"]
    token = path.removeprefix("/guest/")
    with session() as s:
        assert token not in s.scalar(select(GuestLink.token_hash))  # only the hash is kept

    guest = TestClient(create_app(), base_url="https://testserver")
    page = guest.get(f"/api/guest/{token}")
    assert page.status_code == 200 and "set-cookie" not in page.headers
    assert [d["title"] for d in page.json()["documents"]] == ["Invoice 7"]
    pdf = guest.get(f"/api/guest/{token}/documents/{invoice}/file")
    assert pdf.content == b"%PDF-1.4 archive" and pdf.headers["cache-control"] == "no-store"
    assert guest.get(f"/api/guest/{token}/documents/{medical}/file").status_code == 404
    with session() as s:
        seen = s.scalars(
            select(AuditLog.after["what"].astext).where(
                AuditLog.document_id == invoice, AuditLog.action == "guest_view"
            )
        ).all()
    assert sorted(seen) == ["list", "view"]

    # A later document is never added; a deleted one disappears.
    with session() as s:
        s.execute(
            update(Document).where(Document.id == invoice).values(deleted_at=datetime.now(UTC))
        )
    assert guest.get(f"/api/guest/{token}").json()["documents"] == []

    # Private documents need a second confirmation; another person's documents are refused.
    private = body | {"document_ids": [medical]}
    asked = owner.post("/api/guest-links", json=private, headers=CSRF)
    assert asked.status_code == 409 and asked.json()["error"]["details"]["document_ids"] == [
        medical
    ]
    sure = owner.post("/api/guest-links", json=private | {"include_private": True}, headers=CSRF)
    assert sure.status_code == 201
    assert signed_in("bob").post("/api/guest-links", json=private, headers=CSRF).status_code == 404

    # Revoked and expired links are gone.
    link_id = made.json()["id"]
    assert owner.post(f"/api/guest-links/{link_id}/revoke", headers=CSRF).status_code == 204
    assert guest.get(f"/api/guest/{token}").status_code == 404
    other = sure.json()["path"].removeprefix("/guest/")
    with session() as s:
        s.execute(update(GuestLink).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    assert guest.get(f"/api/guest/{other}").status_code == 404

    # Guessing is throttled.
    guest_api.limiter.failures.clear()
    codes = [guest.get(f"/api/guest/wrong{n}").status_code for n in range(7)]
    assert codes[:5] == [404] * 5 and codes[-1] == 429

    # A plugin may only make a link when a person pressed its button.
    with pytest.raises(NotInteractive):
        archive.registry("advisor").actions["share"][0](alice, {"ids": [medical]})
