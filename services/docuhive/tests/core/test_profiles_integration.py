"""Identities through the API: the same visibility as documents, passwords never come back."""

import pytest
from cryptography.fernet import Fernet
from docuhive.api.app import create_app
from docuhive.mail.settings import get_mail_settings
from docuhive.sdk.testing import Archive
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration
CSRF = {"X-DocuHive-CSRF": "1"}
ROOT = "plugins-example/schule"
BUSINESS = {
    "kind": "business",
    "name": "Muster Design",
    "address": {"street": "Beispielweg 1", "postcode": "12345", "city": "Musterstadt"},
    "email": "post@example.org",
    "bank": {"holder": "Muster Design", "iban": "DE89 3704 0044 0532 0130 00"},
    "smtp": {"host": "smtp.example.org", "from_address": "post@example.org", "password": "s3cret"},
}


def signed_in(name):
    client = TestClient(create_app(), base_url="https://testserver")
    client.post(
        "/api/auth/login",
        json={"username": name, "password": "a synthetic test password"},
        headers=CSRF,
    )
    return client


@pytest.fixture
def archive(monkeypatch):
    monkeypatch.setenv("DOCUHIVE_MAIL_TOKEN_KEY", Fernet.generate_key().decode())
    get_mail_settings.cache_clear()
    with Archive(ROOT) as made:
        yield made
    get_mail_settings.cache_clear()


def test_identities(archive):
    archive.user("alice"), archive.user("bob")
    alice, bob = signed_in("alice"), signed_in("bob")

    made = alice.post("/api/profiles", json=BUSINESS, headers=CSRF)
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["bank"]["iban"] == "DE89370400440532013000"
    assert body["has_smtp_password"] is True and "password" not in body["smtp"]
    assert "s3cret" not in alice.get("/api/profiles").text

    assert bob.get("/api/profiles").json() == []  # private by default
    shared = alice.put(
        f"/api/profiles/{body['id']}", json=BUSINESS | {"shared": True}, headers=CSRF
    )
    assert shared.json()["has_smtp_password"] is True  # no password sent: the old one stays
    assert [p["name"] for p in bob.get("/api/profiles").json()] == ["Muster Design"]
    assert bob.put(f"/api/profiles/{body['id']}", json=BUSINESS, headers=CSRF).status_code == 404
    assert bob.delete(f"/api/profiles/{body['id']}", headers=CSRF).status_code == 404

    wrong = BUSINESS | {"bank": {"iban": "DE89 3704 0044 0532 0130 01"}}
    assert alice.post("/api/profiles", json=wrong, headers=CSRF).status_code == 422
    assert (
        alice.post("/api/profiles", json=BUSINESS | {"vat_id": "DE123"}, headers=CSRF).status_code
        == 422
    )
    assert alice.delete(f"/api/profiles/{body['id']}", headers=CSRF).status_code == 204
