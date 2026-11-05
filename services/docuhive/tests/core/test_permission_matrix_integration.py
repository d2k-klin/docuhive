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
from docuhive.config.settings import get_settings
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
                "manual_fields, fts_config, vault_path) VALUES (:id, :owner, false, 'stored', "
                ":sha, 'application/pdf', 'Synthetic private letter', '{}', 'dh_simple', :path)"
            ),
            {"id": DOC, "owner": owner, "sha": "0" * 64, "path": f"2026/{DOC}"},
        )
    # Real files, so a refusal can never be a "file missing" 404 in disguise.
    folder = get_settings().vault_dir / "2026" / DOC
    folder.mkdir(parents=True)
    for name in ("original.pdf", "archive.pdf", "thumb.webp"):
        (folder / name).write_bytes(b"%PDF-1.4 synthetic")
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
    sign_in("owner")
    reads = [path for method, path in routes if method == "get" and "similar" not in path]
    for kind in ("original", "archive", "thumb"):
        assert client.get(f"/api/documents/{DOC}/file?kind={kind}").status_code == 200
    assert [(p, call(client, "get", p).status_code) for p in reads] == [(p, 200) for p in reads]

    sign_in("intruder")
    leaks = []
    for method, path in routes:
        response = call(client, method, path)
        code = response.json().get("error", {}).get("code") if response.content else None
        if response.status_code not in {403, 404} or code == "document_file_missing":
            leaks.append((method, path, response.status_code, code))
    for kind in ("original", "archive", "thumb"):
        response = client.get(f"/api/documents/{DOC}/file?kind={kind}")
        if response.status_code != 404 or response.json()["error"]["code"] != "document_not_found":
            leaks.append(("get", f"file?kind={kind}", response.status_code, response.text[:80]))
    assert leaks == [], "\n".join(map(str, leaks))
