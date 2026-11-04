"""Every API route, walked from the OpenAPI schema so a new route is covered automatically.

1. Without a session, every route answers 401 (except the short public list below).
2. On a private document, every document route refuses another user, administrators included.

ponytail: other per-user resources (chats, views, analyses, tokens…) are checked in their own
tests; extend `ids` and the second sweep if a new kind of private object is added.
"""

import re

import pytest
from docuhive.api.app import create_app
from docuhive.auth import create_user
from docuhive.auth.rate_limit import LoginLimiter
from docuhive.db import session
from fastapi.testclient import TestClient
from sqlalchemy import text

pytestmark = pytest.mark.integration
CSRF = {"X-DocuHive-CSRF": "1"}
PASSWORD = "a synthetic strong password"
DOC = "01JSYNTHETICPRIVATE0000000"
PUBLIC = {
    ("post", "/api/auth/login"),
    ("get", "/api/system/health"),
    ("get", "/api/reminders.ics"),  # calendar apps cannot send headers: ?token= instead
}


@pytest.fixture
def client(postgres, monkeypatch):
    monkeypatch.setattr("docuhive.api.app.start_intelligence", lambda: None)
    monkeypatch.setattr("docuhive.api.auth.limiter", LoginLimiter())
    owner = create_user("owner", PASSWORD)
    create_user("intruder", PASSWORD, admin=True)
    with session() as db:
        db.execute(
            text(
                "INSERT INTO documents (id, owner_id, shared, status, sha256, mime, title, "
                "manual_fields, fts_config) VALUES (:id, :owner, false, 'stored', :sha, "
                "'application/pdf', 'Synthetic private letter', '{}', 'dh_simple')"
            ),
            {"id": DOC, "owner": owner, "sha": "0" * 64},
        )
    with TestClient(create_app(), base_url="https://testserver") as client:
        yield client


def operations(client):
    for path, ops in client.app.openapi()["paths"].items():
        if not path.startswith("/api/"):
            continue
        for method in ops:
            yield method, path


def fill(path: str) -> str:
    ids = {"doc_id": DOC, "document_id": DOC, "kind": "tags", "provider": "google", "action": "x"}
    return re.sub(r"\{(\w+)\}", lambda m: ids.get(m.group(1), "1"), path)


def call(client, method: str, path: str):
    body = {} if method in {"post", "put", "patch"} else None
    return client.request(method.upper(), fill(path), json=body, headers=CSRF)


def test_every_route_requires_a_session(client):
    open_routes = [
        (method, path, response.status_code)
        for method, path in operations(client)
        if (method, path) not in PUBLIC
        and (response := call(client, method, path)).status_code != 401
    ]
    assert open_routes == [], "\n".join(map(str, open_routes))
    assert client.get("/api/reminders.ics?token=dh_wrong").status_code == 401


@pytest.mark.req("AUTH-03")
def test_document_routes_refuse_everyone_but_the_owner(client):
    def sign_in(username):
        client.cookies.clear()
        response = client.post(
            "/api/auth/login", json={"username": username, "password": PASSWORD}, headers=CSRF
        )
        assert response.status_code == 204

    routes = [
        (method, path)
        for method, path in operations(client)
        if "{doc_id}" in path or "{document_id}" in path
    ]
    assert len(routes) >= 10
    sign_in("intruder")
    leaks = [
        (method, path, response.status_code)
        for method, path in routes
        if (response := call(client, method, path)).status_code < 400
        or response.status_code in {401, 500}
    ]
    assert leaks == []
    sign_in("owner")
    assert client.get(f"/api/documents/{DOC}").status_code == 200
