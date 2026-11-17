"""Plugin state, settings and the administrator API on PostgreSQL."""

import pytest
from docuhive import config
from docuhive.api.app import create_app
from docuhive.auth import create_user
from docuhive.auth.rate_limit import LoginLimiter
from docuhive.db import session
from docuhive.db.models import AuditLog, Setting
from docuhive.plugins import runtime, state
from docuhive.plugins.manifest import load
from fastapi.testclient import TestClient
from sqlalchemy import select

pytestmark = pytest.mark.integration
CSRF = {"X-DocuHive-CSRF": "1"}
PASSWORD = "a synthetic strong password"
MANIFEST = """id: fuel
name: Fuel
version: 0.1.0
requires_sdk: ">=1,<2"
capabilities: [documents:read, secrets, {network: [api.fuel.test]}]
settings:
  - {key: plate, type: string, label: Number plate, required: true}
  - {key: litres, type: number, label: Tank size}
  - {key: card_key, type: secret, label: Fuel card key}
setup_checks:
  - {id: plate, title: Number plate, when_missing: plate, required: true}
"""


@pytest.fixture
def plugin(postgres, monkeypatch, tmp_path):
    folder = tmp_path / "plugins" / "fuel"
    folder.mkdir(parents=True)
    (folder / "plugin.yaml").write_text(MANIFEST)
    (folder / "README.md").write_text("# Fuel\n")
    monkeypatch.setenv("DOCUHIVE_PLUGINS_DIR", str(folder.parent))
    secret = "synthetic-test-secret-with-at-least-32-bytes"  # gitleaks:allow
    monkeypatch.setenv("DOCUHIVE_SECRET_KEY", secret)
    config.reload()
    runtime.reset()
    yield folder
    runtime.reset()


@pytest.fixture
def client(plugin, monkeypatch):
    monkeypatch.setattr("docuhive.api.app.start_intelligence", lambda: None)
    monkeypatch.setattr("docuhive.api.auth.limiter", LoginLimiter())
    create_user("owner", PASSWORD, admin=True)
    create_user("member", PASSWORD)
    with TestClient(create_app(), base_url="https://testserver") as client:
        yield client


def login(client, username):
    response = client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}, headers=CSRF
    )
    assert response.status_code == 204


def test_enable_disable_and_settings_with_a_secret(plugin):
    manifest = load(plugin)
    state.enable("fuel", manifest.capability_names(), actor="user:1")
    assert state.states()["fuel"].enabled
    assert state.save(manifest, {"litres": "x"}, actor="user:1") == {
        "litres": "Enter a number",
        "plate": "Required",
    }
    assert state.save(manifest, {"plate": "B-DH 2026", "card_key": "s3cret"}, actor="user:1") == {}
    with session() as s:
        stored = s.scalar(select(Setting.value).where(Setting.key == "plugin:fuel:card_key"))
        audit = s.scalars(select(AuditLog.after).where(AuditLog.action == "plugin.settings")).all()
    assert "s3cret" not in str(stored) and "enc" in stored
    assert all("s3cret" not in str(a) for a in audit)
    secret = next(f for f in manifest.settings if f.key == "card_key")
    assert state.get_value("fuel", secret) == "s3cret"
    assert state.public_values(manifest)["card_key"] == {"saved": True}
    assert state.save(manifest, {"card_key": ""}, actor="user:1") == {}  # empty keeps it
    assert state.get_value("fuel", secret) == "s3cret"
    state.disable("fuel", actor="user:1")
    assert not state.states()["fuel"].enabled


def test_api_is_for_administrators_and_requires_the_current_capabilities(client, plugin):
    login(client, "member")
    assert client.get("/api/plugins").status_code == 403
    client.post("/api/auth/logout", headers=CSRF)
    login(client, "owner")
    [listed] = client.get("/api/plugins").json()
    assert listed["state"] == "off" and listed["running"] is False
    assert {c["id"] for c in listed["capabilities"]} == {
        "documents:read",
        "secrets",
        "network:api.fuel.test",
    }
    stale = client.post(
        "/api/plugins/fuel/enable", json={"capabilities": ["documents:read"]}, headers=CSRF
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "capabilities_changed"
    wanted = [c["id"] for c in listed["capabilities"]]
    assert client.post("/api/plugins/fuel/enable", json={"capabilities": wanted}).status_code == 403
    enabled = client.post("/api/plugins/fuel/enable", json={"capabilities": wanted}, headers=CSRF)
    assert enabled.json()["state"] == "needs_restart"
    state.record("fuel", error="migrations/001.sql: table exists")  # a start that failed
    assert client.get("/api/plugins").json()[0]["state"] == "problem"
    state.enable("fuel", wanted, actor="test")  # switching on again clears it
    bad = client.put("/api/plugins/fuel/settings", json={"plate": ""}, headers=CSRF)
    assert bad.status_code == 422 and bad.json()["error"]["details"]["fields"] == {
        "plate": "Required"
    }
    saved = client.put(
        "/api/plugins/fuel/settings", json={"plate": "B-DH 1", "card_key": "s3cret"}, headers=CSRF
    )
    assert saved.json()["values"] == {
        "plate": "B-DH 1",
        "litres": None,
        "card_key": {"saved": True},
    }
    assert "s3cret" not in saved.text and "s3cret" not in client.get("/api/plugins").text

    # A restart starts it; a new version asking for more stays off until approved.
    runtime.reset()
    runtime.start("api")
    assert "fuel" in runtime.LOADED
    assert client.get("/api/plugins").json()[0]["state"] == "on"
    (plugin / "plugin.yaml").write_text(
        MANIFEST.replace("secrets,", "secrets, ai,").replace("0.1.0", "0.2.0")
    )
    runtime.reset()
    runtime.start("api")
    [listed] = client.get("/api/plugins").json()
    assert "fuel" not in runtime.LOADED and listed["state"] == "needs_approval"
    checks = {c["id"]: c for c in client.get("/api/system/setup-status").json()}
    assert "plugin.fuel.plate" not in checks  # not running, so no setup step


def test_setup_step_appears_while_running(client, plugin):
    manifest = load(plugin)
    state.enable("fuel", manifest.capability_names(), actor="user:1")
    runtime.start("api")
    login(client, "owner")
    checks = {c["id"]: c for c in client.get("/api/system/setup-status").json()}
    assert checks["plugin.fuel.plate"]["status"] == "todo"
    state.save(manifest, {"plate": "B-DH 1"}, actor="user:1")
    checks = {c["id"]: c for c in client.get("/api/system/setup-status").json()}
    assert checks["plugin.fuel.plate"]["status"] == "ok"


def test_a_sending_action_needs_a_preview(tmp_path):
    """Anything that leaves the house is shown to the person first: no preview, no start."""
    from docuhive.plugins import install
    from docuhive.plugins.manifest import load
    from docuhive.sdk.registry import Registry

    folder = tmp_path / "sender"
    (folder / "pages").mkdir(parents=True)
    (folder / "plugin.yaml").write_text(
        'id: sender\nname: Sender\nversion: 0.1.0\nrequires_sdk: ">=1,<2"\n'
        "capabilities: [mail:send]\n"
    )
    (folder / "pages" / "send.yaml").write_text(
        "title: Send\nblocks:\n  - type: actions\n    actions:\n"
        "      - { label: Send, action: send }\n"
    )
    registry = Registry(load(folder), folder)
    registry.action("send", outgoing=True)(lambda user, params: "sent")
    with pytest.raises(install.Refused, match="give it a preview"):
        install.prepare(registry, "api")
    registry.action("send", outgoing=True, preview=lambda u, p: {"to": []})(lambda u, p: "sent")
    install.prepare(registry, "api")
