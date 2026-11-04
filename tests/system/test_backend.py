"""Black-box assertions against the running real API; no dependency overrides."""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.system]


class MissingArchiveEndpoint(Exception):
    pass


@pytest.mark.req("NFR-08")
def test_health_is_real_and_versioned(api):
    from docuhive import __version__

    assert api.get("/api/system/health").json() == {"status": "ok", "version": __version__}


@pytest.mark.req("AUTH-01", "AUTH-04", "NFR-02")
def test_login_csrf_session_logout_and_member_admin_boundary(api):
    credentials = {"username": "bob", "password": "synthetic qa password 2026"}
    assert (
        api.post("/api/auth/login", json=credentials, headers={"X-DocuHive-CSRF": ""}).status_code
        == 403
    )
    assert api.get("/api/system/jobs").status_code == 401
    assert api.post("/api/auth/login", json=credentials).status_code == 204
    first = api.cookies["dh_session"]
    assert api.get("/api/auth/me").json()["username"] == "bob"
    assert api.get("/api/system/jobs").status_code == 403
    assert api.post("/api/auth/logout").status_code == 204
    assert api.get("/api/auth/me").status_code == 401
    assert api.post("/api/auth/login", json=credentials).status_code == 204
    assert api.cookies["dh_session"] != first


@pytest.mark.req("AUTH-02")
def test_token_scope_and_revocation(alice):
    response = alice.post("/api/tokens", json={"name": "qa-scanner", "scopes": ["upload"]})
    assert response.status_code == 201
    token = response.json()
    headers = {"Authorization": "Bearer " + token["token"]}
    try:
        assert alice.get("/api/auth/me", headers=headers).status_code == 403
        assert alice.get("/api/system/jobs", headers=headers).status_code == 403
    finally:
        assert alice.delete(f"/api/tokens/{token['id']}").status_code == 204
    assert alice.get("/api/auth/me", headers=headers).status_code == 401


@pytest.mark.req("ING-01", "ING-05", "CAP-04")
@pytest.mark.xfail(
    strict=True,
    raises=MissingArchiveEndpoint,
    reason="OA-M3 upload route absent: docs/Developer-QA/bugs.md#qa-001",
)
def test_upload_deduplication(alice, corpus):
    root, _ = corpus
    results = []
    for _ in range(2):
        with (root / "case-001.pdf").open("rb") as file:
            response = alice.post(
                "/api/upload", files={"files": ("invoice.pdf", file, "application/pdf")}
            )
        if response.status_code == 404:
            raise MissingArchiveEndpoint("Upload not implemented")
        assert response.status_code in {200, 201, 202}, response.text
        results.append(response.json())
    assert results[0]["document_id"] == results[1]["document_id"]
    assert results[1]["status"] == "duplicate"
