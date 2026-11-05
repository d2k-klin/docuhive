import pytest
from docuhive import auth
from docuhive.agents.classify import classify
from docuhive.contracts import CurrentUser
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.intel.test_classify_extract import INVOICE, out

OWNER = CurrentUser(id=1, username="dev", role="admin")
MEMBER = CurrentUser(id=2, username="member", role="member")


@pytest.fixture
def client(core):
    from docuhive.ai.routers import CL_ROUTERS

    app = FastAPI()
    for r in CL_ROUTERS:
        app.include_router(r)
    app.dependency_overrides[auth.current_user] = lambda: OWNER
    app.dependency_overrides[auth.require_admin] = lambda: OWNER
    return TestClient(app)


def as_user(client, user):
    client.app.dependency_overrides[auth.current_user] = lambda: user


def test_taxonomy_tree(client):
    body = client.get("/api/taxonomy").json()
    utilities = next(n for n in body["tree"] if n["id"] == "utilities")
    assert {c["id"] for c in utilities["children"]} >= {"utilities/electricity"}
    assert body["default_currency"] == "EUR"


def test_review_queue_count_accept_reject(client, core, fake):
    fake(outputs={"*": out(tags=["energy"])})
    doc = core.docs.add(INVOICE)
    classify(doc)
    assert client.get("/api/review/count").json()["pending"] == 6  # 5 fields + 1 new tag
    [group] = client.get("/api/review/queue").json()["items"]
    assert group["document"]["id"] == doc and group["document"]["can_resolve"]
    items = {i["field"]: i for i in group["items"]}
    r = client.post(f"/api/review/items/{items['category']['id']}/accept", json={})
    assert r.status_code == 200 and core.docs.get(doc).category == "utilities/electricity"
    client.post(f"/api/review/items/{items['title']['id']}/reject")
    term = client.post(f"/api/review/terms/{items['tag:energy']['id']}/accept").json()
    assert "energy" in term["snippet"] and "energy" in core.docs.get(doc).tags
    bad = client.post(
        f"/api/review/items/{items['document_type']['id']}/accept", json={"value": "nope"}
    )
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "invalid_value"
    assert client.post(f"/api/review/documents/{doc}/accept-all").json()["applied"]


def test_review_non_owner_forbidden_and_reclassify(client, core, fake):
    fake(outputs={"*": out()})
    doc = core.docs.add(INVOICE, owner_id=1, shared=True)
    classify(doc)
    as_user(client, MEMBER)
    [group] = client.get("/api/review/queue").json()["items"]
    assert group["document"]["can_resolve"] is False
    item = group["items"][0]["id"]
    assert client.post(f"/api/review/items/{item}/accept", json={}).status_code == 403
    assert (
        client.post("/api/review/reclassify", json={"document_ids": [doc]}).json()["documents"] == 0
    )
    as_user(client, OWNER)
    assert client.post("/api/review/reclassify", json={"document_ids": [doc]}).json() == {
        "documents": 1,
        "jobs": 2,
    }


def test_ai_runs_usage_and_under_the_hood(client, core, fake):
    fake(outputs={"*": out()})
    doc = core.docs.add(INVOICE)
    classify(doc)
    runs = client.get(f"/api/ai/runs?document_id={doc}").json()["items"]
    detail = client.get(f"/api/ai/runs/{runs[0]['id']}").json()
    assert (
        detail["prompt_version"] == "classify@1"
        and "Classify one document" in detail["prompt_text"]
    )
    assert detail["output"]["category"] == "utilities/electricity" and detail["learn"]
    usage = client.get("/api/ai/usage").json()
    assert usage["privacy"]["local_runs"] == 1 and usage["providers"][0]["provider"] == "local"
    as_user(client, MEMBER)
    assert client.get("/api/ai/runs").status_code == 403


def test_routing_providers_setup_status(client):
    routing = client.get("/api/ai/routing").json()
    assert routing["tasks"]["classify"]["routes"][0] == {"route": "local/m", "local": True}
    assert {p["name"] for p in client.get("/api/ai/providers").json()} == {"local", "cloud"}
    ids = {c["id"] for c in client.get("/api/ai/setup-status").json()}
    assert {"ai.provider", "ai.privacy", "ai.auto_apply"} <= ids
    assert client.get("/api/notifications/setup-status").json()[0]["status"] == "optional"
    assert client.get("/api/sources/setup-status").json()[0]["id"] == "mail.key"


def test_mailbox_login_problems_in_plain_words():
    import imaplib
    import socket

    from docuhive.mail.routes import login_problem

    assert "can't be found" in login_problem(socket.gaierror(-2, "x"), "imap.example.invalid")
    assert "didn't answer" in login_problem(TimeoutError(), "imap.example.org")
    refused = login_problem(imaplib.IMAP4.error("AUTHENTICATIONFAILED"), "imap.gmail.com")
    assert "refused the login" in refused and "app password" in refused


def test_unconfigured_oauth_returns_to_sources_with_a_reason(client, monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    from docuhive.mail import oauth

    def missing(*args, **kwargs):
        raise LookupError("not set")

    monkeypatch.setattr(oauth, "start_url", missing)
    assert client.get("/api/sources/accounts").json()["oauth"] == {
        "google": False,
        "microsoft": False,
    }
    r = client.get("/api/sources/oauth/google/start", follow_redirects=False)
    assert r.status_code == 302
    url = urlsplit(r.headers["location"])
    query = parse_qs(url.query)
    assert url.path == "/sources" and query["error"] == ["not_configured"]
    assert "Gmail isn't set up" in query["message"][0] and "IMAP" in query["message"][0]
    r = client.get("/api/sources/oauth/microsoft/start", follow_redirects=False)
    outlook = parse_qs(urlsplit(r.headers["location"]).query)["message"][0]
    assert "Outlook isn't set up" in outlook and "IMAP" not in outlook


def test_similar_and_reminders_endpoints(client, core):
    from docuhive.index.jobs import embed_document

    a = core.docs.add("Stromrechnung Stadtwerke kWh")
    b = core.docs.add("Stromrechnung Stadtwerke kWh Oktober")
    embed_document(a)
    embed_document(b)
    body = client.get(f"/api/ai/similar/{a}").json()
    assert body["items"][0]["id"] == b and body["semantic_available"]
    assert client.get("/api/reminders").json()["items"] == []
    assert client.get("/api/reminders.ics?token=nope").status_code == 401


def test_ics_needs_calendar_token(client, core):
    import hashlib
    from datetime import date

    from docuhive import reminders
    from sqlalchemy import insert

    from tests.fakes.intel import api_tokens

    doc = core.docs.add(
        "x",
        document_type="contract",
        title="Vertrag",
        facts={"end_date": {"type": "date", "value": "2030-01-31"}},
    )
    reminders.sync(doc, today=date.today())
    with core.session() as s:
        s.execute(
            insert(api_tokens).values(
                user_id=1, scopes=["calendar"], token_hash=hashlib.sha256(b"tok").hexdigest()
            )
        )
        # A broader token must not work in a URL that calendar services store.
        s.execute(
            insert(api_tokens).values(
                user_id=1, scopes=["read", "admin"], token_hash=hashlib.sha256(b"wide").hexdigest()
            )
        )
    r = client.get("/api/reminders.ics?token=tok")
    assert r.status_code == 200 and "SUMMARY:End date: Vertrag" in r.text
    assert client.get("/api/reminders.ics?token=wide").status_code == 401
    with core.session() as s:
        s.execute(
            insert(api_tokens).values(
                user_id=1,
                scopes=["calendar", "read"],
                token_hash=hashlib.sha256(b"mixed").hexdigest(),
            )
        )
    assert client.get("/api/reminders.ics?token=mixed").status_code == 401
