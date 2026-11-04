"""Knowledge-base boundaries against a network-free relational storage fake."""

from datetime import UTC, datetime

import pytest
from docuhive import db
from docuhive.db.models import (
    Correspondent,
    DocSource,
    Document,
    DocumentTag,
    Job,
    KnowledgeBase,
    Tag,
)
from sqlalchemy import BigInteger, DateTime, Integer, String, insert, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, REGCONFIG, TSVECTOR
from sqlalchemy.types import JSON

from .test_auth_integration import CSRF, login
from .test_auth_memory import AwareDateTime
from .test_auth_memory import client as auth_client

client = auth_client


@pytest.fixture
def knowledge(client):
    tables = [
        Correspondent.__table__,
        Tag.__table__,
        Document.__table__,
        DocumentTag.__table__,
        DocSource.__table__,
        KnowledgeBase.__table__,
    ]
    originals = [(c, c.type, c.server_default) for t in tables for c in t.columns]
    engine = db.get_engine()
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
        db.CoreBase.metadata.create_all(engine, tables=tables)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE doc_chunks (document_id TEXT, chunk_no INTEGER, "
                    "embed_model TEXT, created_at TIMESTAMP)"
                )
            )
        login(client)
        yield client
    finally:
        for c, original, default in originals:
            c.type, c.server_default = original, default


def add_document(doc_id, *, owner=1, shared=False, category="utilities/electricity", deleted=False):
    with db.session() as session:
        session.add(
            Document(
                id=doc_id,
                owner_id=owner,
                shared=shared,
                status="stored",
                sha256=doc_id,
                mime="application/pdf",
                category=category,
                manual_fields=[],
                fts_config="dh_simple",
                deleted_at=datetime.now(UTC) if deleted else None,
            )
        )


def test_owner_shared_and_admin_boundaries(knowledge):
    private = knowledge.post("/api/kb", json={"name": "Private"}, headers=CSRF)
    assert private.status_code == 201
    private_id = private.json()["id"]
    shared_id = knowledge.post(
        "/api/kb", json={"name": "Shared", "shared": True}, headers=CSRF
    ).json()["id"]
    assert (
        knowledge.patch(
            f"/api/kb/{shared_id}", json={"description": "Updated"}, headers=CSRF
        ).json()["name"]
        == "Shared"
    )
    login(knowledge, "other")
    assert [k["name"] for k in knowledge.get("/api/kb").json()["items"]] == ["Shared"]
    assert knowledge.get(f"/api/kb/{private_id}").status_code == 404
    assert (
        knowledge.patch(f"/api/kb/{private_id}", json={"name": "No"}, headers=CSRF).status_code
        == 404
    )
    assert knowledge.delete(f"/api/kb/{shared_id}", headers=CSRF).status_code == 403
    other_id = knowledge.post(
        "/api/kb", json={"name": "Other", "shared": True}, headers=CSRF
    ).json()["id"]
    login(knowledge)
    assert (
        knowledge.patch(f"/api/kb/{other_id}", json={"shared": False}, headers=CSRF).status_code
        == 403
    )
    assert knowledge.delete(f"/api/kb/{private_id}", headers=CSRF).status_code == 204
    assert knowledge.get(f"/api/kb/{private_id}").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"name": " "},
        {"name": "x", "filters": {"categories": ["missing"]}},
        {"name": "x", "filters": {"tags": ["missing"]}},
        {"name": "x", "filters": {"document_types": ["missing"]}},
        {"name": "x", "filters": {"include_trashed": True}},
        {"name": "x", "filters": {"typo": []}},
        {"name": "x", "filters": {"date_from": "2026-11-01", "date_to": "2026-01-01"}},
        {"name": "x", "filters": {"document_ids": ["x"] * 501}},
    ],
)
def test_invalid_scope_is_rejected(knowledge, body):
    assert knowledge.post("/api/kb", json=body, headers=CSRF).status_code == 422


def test_status_and_suggestions_only_count_caller_visible_documents(knowledge):
    assert knowledge.get("/api/kb/suggestions").json() == []
    for doc_id in ["indexed", "old", "waiting", "failed", "retry"]:
        add_document(doc_id)
    add_document("hidden", owner=2)
    add_document("trash", deleted=True)
    add_document("outside", category="health")
    add_document("retired-category", category="retired/category")
    with db.session() as session:
        for doc_id, model in [
            ("indexed", "ollama/bge-m3"),
            ("old", "old/model"),
            ("hidden", "old/model"),
        ]:
            session.execute(
                text("INSERT INTO doc_chunks VALUES (:doc, 0, :model, :at)"),
                {"doc": doc_id, "model": model, "at": datetime.now(UTC).isoformat()},
            )
        for doc_id, state in [("failed", "dead"), ("retry", "dead"), ("retry", "pending")]:
            session.execute(
                insert(Job).values(
                    kind="index.embed", payload={"document_id": doc_id}, status=state
                )
            )
    suggestions = knowledge.get("/api/kb/suggestions").json()
    assert suggestions[0]["name"] == "Everything"
    assert any(s["filters"]["categories"] == ["utilities"] for s in suggestions)
    assert not any(s["filters"]["categories"] == ["retired"] for s in suggestions)
    base = knowledge.post(
        "/api/kb",
        json={"name": "Utilities", "shared": True, "filters": {"categories": ["utilities"]}},
        headers=CSRF,
    ).json()
    status = knowledge.get(f"/api/kb/{base['id']}/status").json()
    assert {k: status[k] for k in ["documents", "embedded", "pending", "failed", "stale"]} == {
        "documents": 5,
        "embedded": 2,
        "pending": 2,
        "failed": 1,
        "stale": 1,
    }
    assert status["last_indexed_at"] and status["embedding_model"] == "ollama/bge-m3"
    login(knowledge, "other")
    assert knowledge.get(f"/api/kb/{base['id']}/status").json()["documents"] == 1


def test_kb_scopes_and_local_consumer_cannot_be_self_granted_by_tokens(knowledge):
    base_id = knowledge.post("/api/kb", json={"name": "Private"}, headers=CSRF).json()["id"]
    reader = knowledge.post(
        "/api/tokens",
        json={"name": "KB reader", "scopes": ["kb:read"], "local_consumer": True},
        headers=CSRF,
    ).json()
    assert reader["local_consumer"] is True
    headers = {"Authorization": f"Bearer {reader['token']}"}
    assert knowledge.get(f"/api/kb/{base_id}", headers=headers).status_code == 200
    assert knowledge.post("/api/kb", json={"name": "No"}, headers=headers).status_code == 403
    admin = knowledge.post(
        "/api/tokens", json={"name": "Admin", "scopes": ["admin"]}, headers=CSRF
    ).json()
    assert (
        knowledge.post(
            "/api/tokens",
            json={"name": "Escalate", "scopes": ["kb:read"], "local_consumer": True},
            headers={"Authorization": f"Bearer {admin['token']}"},
        ).status_code
        == 403
    )
    assert "token" not in knowledge.get("/api/tokens").json()["items"][0]
