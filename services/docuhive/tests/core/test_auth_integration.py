"""Real storage tests for session lifecycle, scoped tokens and visibility SQL."""

from datetime import UTC, datetime, timedelta

import pytest
from docuhive.api.app import create_app
from docuhive.auth import create_user, token_hash, visible_docs, visible_docs_incl_trash
from docuhive.auth.rate_limit import LoginLimiter
from docuhive.contracts import CurrentUser
from docuhive.db import session
from docuhive.db.models import ApiToken, AuthSession, Document
from fastapi.testclient import TestClient
from sqlalchemy import select

pytestmark = pytest.mark.integration
CSRF = {"X-DocuHive-CSRF": "1"}
PASSWORD = "a synthetic strong password"


@pytest.fixture
def client(postgres, monkeypatch):
    monkeypatch.setattr("docuhive.api.app.start_intelligence", lambda: None)
    monkeypatch.setattr("docuhive.api.auth.limiter", LoginLimiter())
    create_user("owner", PASSWORD, admin=True)
    create_user("other", PASSWORD)
    with TestClient(create_app(), base_url="https://testserver") as client:
        yield client


def login(client, username="owner"):
    response = client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}, headers=CSRF
    )
    assert response.status_code == 204
    return client.cookies["dh_session"]


def test_login_csrf_cookie_hash_slide_and_logout(client):
    assert (
        client.post("/api/auth/login", json={"username": "owner", "password": PASSWORD}).status_code
        == 403
    )
    raw = login(client)
    with session() as db:
        row = db.get(AuthSession, token_hash(raw))
        assert row and row.token_hash != raw
        row.expires_at = datetime.now(UTC) + timedelta(days=1)
    assert client.get("/api/auth/me").json()["username"] == "owner"
    with session() as db:
        assert db.get(AuthSession, token_hash(raw)).expires_at > datetime.now(UTC) + timedelta(
            days=29
        )
    assert client.post("/api/auth/logout", headers=CSRF).status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert login(client) != raw


def test_login_failure_rate_limit_and_expiry(client):
    for _ in range(5):
        assert (
            client.post(
                "/api/auth/login", json={"username": "owner", "password": "incorrect"}, headers=CSRF
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login", json={"username": "owner", "password": PASSWORD}, headers=CSRF
        ).status_code
        == 429
    )
    raw = login(client, "other")
    with session() as db:
        db.get(AuthSession, token_hash(raw)).expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert client.get("/api/auth/me").status_code == 401


def test_personal_tokens_scopes_revocation_and_user_boundaries(client):
    login(client)
    created = client.post(
        "/api/tokens", json={"name": "scanner", "scopes": ["upload"]}, headers=CSRF
    )
    assert created.status_code == 201
    data = created.json()
    assert data["token"].startswith(f"dh_{data['prefix']}_")
    with session() as db:
        assert db.get(ApiToken, data["id"]).token_hash == token_hash(data["token"])
    assert "token" not in client.get("/api/tokens").json()["items"][0]
    bearer = {"Authorization": f"Bearer {data['token']}"}
    # No CSRF is needed for a valid bearer, but its upload scope cannot read user data.
    assert client.get("/api/auth/me", headers=bearer).status_code == 403
    assert client.get("/api/system/jobs", headers=bearer).status_code == 403
    login(client, "other")
    assert client.delete(f"/api/tokens/{data['id']}", headers=CSRF).status_code == 404
    assert (
        client.post(
            "/api/tokens", json={"name": "escalation", "scopes": ["admin"]}, headers=CSRF
        ).status_code
        == 403
    )
    login(client)
    assert client.delete(f"/api/tokens/{data['id']}", headers=CSRF).status_code == 204
    assert client.get("/api/auth/me", headers=bearer).status_code == 401


def test_admin_users_and_password_revokes_old_credentials(client):
    login(client)
    response = client.post(
        "/api/users", json={"username": "third", "password": PASSWORD}, headers=CSRF
    )
    assert response.status_code == 201
    third_id = response.json()["id"]
    assert (
        client.patch(f"/api/users/{third_id}", json={"disabled": True}, headers=CSRF).status_code
        == 204
    )
    assert (
        client.post(
            "/api/auth/login", json={"username": "third", "password": PASSWORD}, headers=CSRF
        ).status_code
        == 401
    )
    assert client.get("/api/users?limit=1").json()["next_cursor"]
    login(client, "other")
    assert client.get("/api/users").status_code == 403
    assert (
        client.post(
            "/api/auth/password",
            json={"current_password": PASSWORD, "new_password": "a different synthetic password"},
            headers=CSRF,
        ).status_code
        == 204
    )
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("role", ["admin", "member"])
@pytest.mark.parametrize("shared", [False, True])
@pytest.mark.parametrize("trashed", [False, True])
def test_visibility_matrix(postgres, role, shared, trashed):
    owner_id = create_user("owner", PASSWORD)
    other_id = create_user("other", PASSWORD, admin=role == "admin")
    with session() as db:
        db.add(
            Document(
                id="synthetic",
                owner_id=owner_id,
                shared=shared,
                status="stored",
                sha256="a" * 64,
                mime="application/pdf",
                deleted_at=datetime.now(UTC) if trashed else None,
            )
        )
    for user_id, expected in ((owner_id, not trashed), (other_id, shared and not trashed)):
        user = CurrentUser(id=user_id, username="test", role=role)
        with session() as db:
            assert bool(db.scalar(select(Document.id).where(visible_docs(user)))) is expected
            assert bool(db.scalar(select(Document.id).where(visible_docs_incl_trash(user)))) is (
                user_id == owner_id or shared
            )
