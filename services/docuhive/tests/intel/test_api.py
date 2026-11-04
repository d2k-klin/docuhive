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


def test_ics_with_read_token(client, core):
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
                user_id=1, scopes=["read"], token_hash=hashlib.sha256(b"tok").hexdigest()
            )
        )
    r = client.get("/api/reminders.ics?token=tok")
    assert r.status_code == 200 and "SUMMARY:End date: Vertrag" in r.text
