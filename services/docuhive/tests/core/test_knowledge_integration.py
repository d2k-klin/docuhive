"""Saved scopes and indexing counts against the real, disposable PostgreSQL schema."""

import pytest
from docuhive import db
from docuhive.api.app import create_app
from docuhive.auth import create_user
from docuhive.db.models import Job
from fastapi.testclient import TestClient
from sqlalchemy import text

from .test_auth_integration import CSRF, PASSWORD, login
from .test_knowledge import (
    add_document,
)
from .test_knowledge import (
    test_kb_scopes_and_local_consumer_cannot_be_self_granted_by_tokens as token_boundaries,
)
from .test_knowledge import (
    test_owner_shared_and_admin_boundaries as ownership,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def client(postgres, monkeypatch):
    monkeypatch.setattr("docuhive.api.app.start_intelligence", lambda: None)
    create_user("owner", PASSWORD, admin=True)
    create_user("other", PASSWORD)
    with db.session() as session:
        session.execute(text("TRUNCATE doc_chunks"))
    with TestClient(create_app(), base_url="https://testserver") as client:
        login(client)
        yield client


def test_real_crud_permissions_and_tokens(client):
    ownership(client)
    token_boundaries(client)


def test_real_status_and_pagination(client):
    for doc_id in ["current", "old", "pending", "failed"]:
        add_document(doc_id)
    add_document("private-other", owner=2)
    add_document("trashed", deleted=True)
    vector = "[" + ",".join(["1"] + ["0"] * 1023) + "]"
    with db.session() as session:
        for doc_id, model in [("current", "ollama/bge-m3"), ("old", "old/model")]:
            session.execute(
                text(
                    "INSERT INTO doc_chunks (document_id, chunk_no, text, embedding, embed_model) "
                    "VALUES (:doc, 0, 'Synthetic bill', CAST(:vector AS vector), :model)"
                ),
                {"doc": doc_id, "vector": vector, "model": model},
            )
        session.add(Job(kind="index.embed", payload={"document_id": "failed"}, status="dead"))
    base_id = client.post(
        "/api/kb",
        json={"name": "Utilities", "shared": True, "filters": {"categories": ["utilities"]}},
        headers=CSRF,
    ).json()["id"]
    result = client.get(f"/api/kb/{base_id}/status")
    assert result.status_code == 200
    status = result.json()
    assert [status[k] for k in ["documents", "embedded", "pending", "failed", "stale"]] == [
        4,
        2,
        1,
        1,
        1,
    ]
    client.post("/api/kb", json={"name": "Second"}, headers=CSRF)
    first = client.get("/api/kb?limit=1").json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = client.get(f"/api/kb?limit=1&cursor={first['next_cursor']}").json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    assert second["items"][0]["id"] != first["items"][0]["id"]
    login(client, "other")
    assert client.get(f"/api/kb/{base_id}/status").json()["documents"] == 1
