"""Non-destructive clients for the explicitly selected, loopback-only QA stack."""

import os
import ssl
import time
from urllib.parse import urlsplit

import httpx
import pytest
from qa_plugin import ROOT


@pytest.fixture
def api():
    url = os.environ.get("DOCUHIVE_QA_API_URL", "https://127.0.0.1:58000")
    parsed = urlsplit(url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.port != 58000:
        pytest.fail("System checks require the isolated QA API on loopback port 58000")
    with httpx.Client(
        base_url=url,
        timeout=10,
        trust_env=False,
        headers={"X-DocuHive-CSRF": "1"},
        verify=ssl.create_default_context(cafile=ROOT / "tmp/qa/tls/cert.pem"),
    ) as client:
        response = client.get("/api/system/health")
        assert response.status_code == 200, "Start the isolated stack with make qa-up"
        yield client


@pytest.fixture
def alice(api):
    response = api.post(
        "/api/auth/login", json={"username": "alice", "password": "synthetic qa password 2026"}
    )
    assert response.status_code == 204
    return api


def wait_for(
    client: httpx.Client, doc_id: str, status: str = "stored", timeout: float = 60
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/documents/{doc_id}")
        response.raise_for_status()
        body = response.json()
        if body["status"] == status:
            return body
        assert body["status"] != "quarantined", body
        time.sleep(0.25)
    pytest.fail(f"Document did not reach {status} within {timeout}s")


@pytest.fixture
def corpus():
    import yaml

    root = ROOT / "tmp/qa/corpus"
    assert (root / "manifest.yaml").exists(), "Run make qa-corpus first"
    return root, yaml.safe_load((root / "manifest.yaml").read_text())
