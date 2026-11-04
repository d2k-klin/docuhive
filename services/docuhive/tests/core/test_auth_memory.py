"""Run the same auth acceptance scenarios against a network-free test database."""

from datetime import UTC, datetime

import pytest
from docuhive import db
from docuhive.api.app import create_app
from docuhive.auth import create_user
from docuhive.auth.rate_limit import LoginLimiter
from docuhive.db.models import ApiToken, AuthSession, Job, User
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, DateTime, Integer, String, create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import JSON, TypeDecorator

from . import test_auth_integration as scenarios


class AwareDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


@pytest.fixture
def client(monkeypatch):
    # This is a test fake of storage, not a supported application database backend.
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def configure(connection, record):
        connection.create_function("now", 0, lambda: datetime.now(UTC).isoformat())
        connection.execute("PRAGMA foreign_keys=ON")

    tables = [User.__table__, AuthSession.__table__, ApiToken.__table__, Job.__table__]
    originals = [(column, column.type) for table in tables for column in table.columns]
    try:
        for column, original in originals:
            if isinstance(original, BigInteger):
                column.type = original.with_variant(Integer(), "sqlite")
            elif isinstance(original, ARRAY | JSONB):
                column.type = original.with_variant(JSON(), "sqlite")
            elif isinstance(original, INET):
                column.type = original.with_variant(String(), "sqlite")
            elif isinstance(original, DateTime):
                column.type = original.with_variant(AwareDateTime(), "sqlite")
        db.CoreBase.metadata.create_all(engine, tables=tables)
        monkeypatch.setattr(db, "get_engine", lambda: engine)
        monkeypatch.setattr("docuhive.api.app.start_intelligence", lambda: None)
        monkeypatch.setattr("docuhive.api.auth.limiter", LoginLimiter())
        create_user("owner", scenarios.PASSWORD, admin=True)
        create_user("other", scenarios.PASSWORD)
        with TestClient(create_app(), base_url="https://testserver") as client:
            yield client
    finally:
        engine.dispose()
        for column, original in originals:
            column.type = original


@pytest.mark.parametrize(
    "scenario",
    [
        scenarios.test_login_csrf_cookie_hash_slide_and_logout,
        scenarios.test_login_failure_rate_limit_and_expiry,
        scenarios.test_personal_tokens_scopes_revocation_and_user_boundaries,
        scenarios.test_admin_users_and_password_revokes_old_credentials,
    ],
    ids=["session-lifecycle", "rate-and-expiry", "token-permissions", "user-management"],
)
def test_auth_contract_on_memory_storage(client, scenario):
    scenario(client)


def test_admin_job_listing_cursor_and_retry_are_safe(client):
    scenarios.login(client)
    with db.session() as session:
        for _ in range(3):
            session.add(
                Job(
                    kind="synthetic",
                    queue="ocr",
                    payload={"private": "not returned"},
                    status="dead",
                    attempts=5,
                    last_error="private details",
                )
            )
    first = client.get("/api/system/jobs?status=dead&kind=synthetic&queue=ocr&limit=1").json()
    item = first["items"][0]
    assert "payload" not in item and "private details" not in str(first)
    next_page = client.get(f"/api/system/jobs?cursor={first['next_cursor']}&limit=1").json()
    assert next_page["items"][0]["id"] != item["id"]
    assert client.post(f"/api/system/jobs/{item['id']}/retry").status_code == 403
    assert (
        client.post(f"/api/system/jobs/{item['id']}/retry", headers=scenarios.CSRF).status_code
        == 204
    )
    with db.session() as session:
        row = session.get(Job, item["id"])
        assert row.status == "pending" and row.attempts == 0 and row.last_error is None
    assert (
        client.post(f"/api/system/jobs/{item['id']}/retry", headers=scenarios.CSRF).status_code
        == 409
    )
    assert client.post("/api/system/jobs/999/retry", headers=scenarios.CSRF).status_code == 404
    scenarios.login(client, "other")
    assert client.get("/api/system/jobs").status_code == 403


def test_sse_endpoint_is_authenticated_and_has_ten_ticks(client, monkeypatch):
    assert client.get("/api/system/sse-test").status_code == 401

    async def immediately(seconds):
        pass

    monkeypatch.setattr("docuhive.api.system.asyncio.sleep", immediately)
    scenarios.login(client)
    response = client.get("/api/system/sse-test")
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.count("event: tick") == 10


def test_read_tokens_and_session_revocation(client):
    scenarios.login(client)
    token = client.post(
        "/api/tokens", json={"name": "reader", "scopes": ["read"]}, headers=scenarios.CSRF
    ).json()["token"]
    assert (
        client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    )
    assert client.get("/api/auth/me", headers={"Authorization": "Basic invalid"}).status_code == 401
    assert client.get("/api/auth/sessions").json()["items"]
    assert client.post("/api/auth/logout-everywhere", headers=scenarios.CSRF).status_code == 204
    assert client.get("/api/auth/me").status_code == 401
