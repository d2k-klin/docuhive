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
    refused = login_problem(
        imaplib.IMAP4.error("b'[AUTHENTICATIONFAILED] Invalid credentials (Failure)'"),
        "imap.gmail.com",
    )
    assert "refused the login" in refused and "app password" in refused
    assert "folder" in login_problem(LookupError("private folder"), "imap.example.org")
    assert "secret" not in login_problem(RuntimeError("secret password"), "imap.example.org")


@pytest.fixture
def configured_mail(monkeypatch):
    from cryptography.fernet import Fernet
    from docuhive.mail.settings import MailSettings

    settings = MailSettings(_env_file=None, token_key=Fernet.generate_key().decode())
    monkeypatch.setattr("docuhive.mail.routes.get_mail_settings", lambda: settings)
    monkeypatch.setattr("docuhive.mail.settings.get_mail_settings", lambda: settings)
    return settings


def test_connect_imap_tests_login_encrypts_and_starts_sync(
    client, core, configured_mail, monkeypatch
):
    from docuhive.mail import accounts
    from docuhive.mail.models import MailAccount

    tested = []
    monkeypatch.setattr(
        "docuhive.mail.routes.Imap.test_login", lambda self: tested.append(self.host)
    )
    body = {
        "host": "imap.example.org",
        "username": "archive@example.org",
        "password": "app-password",
        "folders": ["INBOX", "Receipts"],
    }
    response = client.post("/api/sources/accounts", json=body)
    assert response.status_code == 200
    account = response.json()
    assert tested == [body["host"]]
    assert "password" not in account and "enc_credentials" not in account
    with core.session() as s:
        saved = s.get(MailAccount, account["id"])
        assert b"app-password" not in saved.enc_credentials
        assert accounts.credentials(saved)["folders"] == body["folders"]
    [job] = core.jobs.pending("mail.sync")
    assert job.payload == {"account_id": account["id"]} and job.queue == "mail"
    assert client.post("/api/sources/accounts", json=body).status_code == 409
    assert len(core.jobs.pending("mail.sync")) == 1


def test_failed_imap_login_saves_nothing(client, core, configured_mail, monkeypatch):
    import imaplib

    def refused(self):
        raise imaplib.IMAP4.error("AUTHENTICATIONFAILED secret")

    monkeypatch.setattr("docuhive.mail.routes.Imap.test_login", refused)
    body = {"host": "imap.example.org", "username": "a@example.org", "password": "secret"}
    response = client.post("/api/sources/accounts", json=body)
    assert response.status_code == 400 and "secret" not in response.text
    assert core.rows("mail_accounts") == [] and core.jobs.pending("mail.sync") == []
    assert client.post("/api/sources/accounts", json=body | {"port": 0}).status_code == 422
    assert client.post("/api/sources/accounts", json=body | {"folders": []}).status_code == 422


def test_mail_connection_setup_exposes_no_secrets(client, configured_mail):
    connection = client.get("/api/sources/accounts").json()["connection"]
    assert connection["credentials_ready"] is True
    assert connection["sync_every_min"] == configured_mail.sync_every_min
    assert connection["oauth_redirects"]["google"].endswith("/api/sources/oauth/google/callback")
    configured_mail.token_key = None
    assert client.get("/api/sources/accounts").json()["connection"]["credentials_ready"] is False


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


def test_shared_category_choices_persist_and_keep_privacy(client, core):
    from docuhive import taxonomy
    from docuhive.ai.privacy import restricted_category

    response = client.put("/api/taxonomy/categories", json={"enabled_ids": ["finance/banking"]})
    assert response.status_code == 200
    taxonomy.reload()
    tax = taxonomy.load()
    assert {c.id for c in tax.categories if c.enabled} == {"finance", "finance/banking", "other"}
    assert restricted_category("health/medical", tax)  # disabling never weakens privacy
    assert (
        client.put("/api/taxonomy/categories", json={"enabled_ids": ["missing"]}).status_code == 422
    )
    assert {c.id for c in taxonomy.load().categories if c.enabled} == {
        "finance",
        "finance/banking",
        "other",
    }
    as_user(client, MEMBER)
    client.app.dependency_overrides.pop(auth.require_admin)
    assert client.get("/api/taxonomy").status_code == 200
    assert client.put("/api/taxonomy/categories", json={"enabled_ids": []}).status_code == 403
    assert (
        client.post("/api/taxonomy/categories", json={"label": "Private business"}).status_code
        == 403
    )


def test_custom_categories_are_used_by_real_classify_validation(client, core, fake):
    from docuhive import taxonomy
    from docuhive.agents.classify import ClassifyOut, make_validator
    from docuhive.ai.privacy import restricted_category

    response = client.post(
        "/api/taxonomy/categories",
        json={
            "label": "Home business",
            "parent_id": "finance",
            "description": "My business receipts",
            "restricted": True,
        },
    )
    assert response.status_code == 200
    category = next(c for c in response.json()["categories"] if c["label"] == "Home business")
    assert category["id"] == "finance/home-business" and category["enabled"]
    assert (
        client.post(
            "/api/taxonomy/categories", json={"label": "Home business", "parent_id": "finance"}
        ).status_code
        == 409
    )
    client.put("/api/taxonomy/categories", json={"enabled_ids": [category["id"]]})
    model = fake(outputs={"*": out(category=category["id"])})
    doc = core.docs.add(INVOICE)
    assert classify(doc)["category"] == category["id"]
    assert (
        "My business receipts" in model.seen_text()
        and "utilities/electricity" not in model.seen_text()
    )
    assert restricted_category(category["id"], taxonomy.load())
    with pytest.raises(ValueError):
        make_validator(taxonomy.load(), [])(ClassifyOut.model_validate(out()))


def test_document_ai_progress_tracks_jobs_and_distinguishes_review(client, core, fake):
    from docuhive.review import accept_all

    fake(outputs={"*": out()})
    doc = core.docs.add(INVOICE)

    def status():
        response = client.post("/api/ai/documents/status", json={"document_ids": [doc]})
        assert response.status_code == 200
        return response.json()["items"][0]

    core.jobs.enqueue("ai.classify", {"document_id": doc}, queue="ai")
    job = core.jobs.all[-1]
    assert status()["status"] == "queued"
    job.status = "running"
    assert status()["status"] == "running" and status()["stage"] == "ai.classify"
    classify(doc)
    job.status = "done"
    result = status()
    assert result["status"] == "needs_review" and result["category"] is None
    assert result["suggested_category"] == "Electricity" and result["ai_run_id"]
    accept_all(doc, OWNER)
    result = status()
    assert result["status"] == "categorized" and result["category_label"] == "Electricity"
    core.jobs.enqueue("ai.classify", {"document_id": doc}, queue="ai")
    assert status()["status"] == "queued"  # a re-run must not show the previous completion


def test_document_ai_progress_is_private_and_reports_failures(client, core):
    from datetime import UTC, datetime, timedelta

    private = core.docs.add("private", owner_id=2, shared=False)
    doc = core.docs.add("visible", owner_id=1)
    core.jobs.enqueue("ai.classify", {"document_id": doc}, queue="ai")
    job = core.jobs.all[-1]

    def state():
        items = client.post(
            "/api/ai/documents/status", json={"document_ids": [private, doc, "unknown"]}
        ).json()["items"]
        assert [i["document_id"] for i in items] == [doc]
        return items[0]["status"]

    job.status = "dead"
    assert state() == "failed"
    job.status = "pending"
    job.run_after = datetime.now(UTC) + timedelta(minutes=10)
    assert state() == "retrying"
    job.status = "deferred"
    assert state() == "paused"
    assert (
        client.post("/api/ai/documents/status", json={"document_ids": [doc] * 501}).status_code
        == 422
    )


def test_progress_does_not_hide_failed_extraction_or_disabled_ai(client, core, fake, monkeypatch):
    from types import SimpleNamespace

    from docuhive.ai.models import AIRun

    fake(outputs={"*": out()})
    doc = core.docs.add(INVOICE)
    classify(doc)
    with core.session() as session:
        session.add(
            AIRun(
                document_id=doc,
                task="extract",
                provider="fake",
                model="m",
                local=True,
                restricted=False,
                prompt_version="extract@1",
                status="invalid",
            )
        )
    body = {"document_ids": [doc]}
    assert (
        client.post("/api/ai/documents/status", json=body).json()["items"][0]["status"] == "failed"
    )
    monkeypatch.setattr(
        "docuhive.ai.progress.get_ai_settings", lambda: SimpleNamespace(enabled=False)
    )
    assert (
        client.post("/api/ai/documents/status", json=body).json()["items"][0]["status"]
        == "disabled"
    )
