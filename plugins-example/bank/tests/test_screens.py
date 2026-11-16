"""The bank screens, through the same API the web app uses."""

from datetime import date
from pathlib import Path

import pytest
from docuhive.api.app import create_app
from docuhive.sdk.testing import Archive
from fastapi.testclient import TestClient

from .samples import CAMT

pytestmark = pytest.mark.integration
PLUGIN = Path(__file__).resolve().parents[1]
CSRF = {"X-DocuHive-CSRF": "1"}
PAGES = "/api/plugin-pages/bank"


def signed_in(name):
    client = TestClient(create_app(), base_url="https://testserver")
    response = client.post(
        "/api/auth/login",
        json={"username": name, "password": "a synthetic test password"},
        headers=CSRF,
    )
    assert response.status_code == 204
    return client


def test_pages_data_actions_and_access():
    with Archive(PLUGIN) as archive:
        alice, _ = archive.user("alice"), archive.user("bob")
        first = archive.add(
            alice,
            document_type="invoice",
            title="March power",
            date=date(2026, 3, 1),
            facts={"amount_total": ("84.20", "EUR")},
        )
        second = archive.add(
            alice,
            document_type="invoice",
            title="March power again",
            date=date(2026, 3, 2),
            facts={"amount_total": ("84.20", "EUR")},
        )
        statement = archive.add(alice, original=("march.xml", CAMT.encode()))
        archive.emit("document.stored", document_id=statement)
        archive.run_jobs()
        client = signed_in("alice")

        nav = client.get("/api/plugin-pages/nav").json()
        assert [(e["page"], e["icon"]) for e in nav] == [
            ("inbox", "landmark"),
            ("transactions", "banknote"),
            ("accounts", "wallet"),
        ]
        page = client.get(f"{PAGES}/inbox").json()
        assert page["plugin_name"] == "Bank statements" and len(page["blocks"]) == 2

        rows = client.get(f"{PAGES}/inbox/blocks/0").json()["rows"]
        power = [r for r in rows if r["counterparty"] == "Stadtwerke Beispiel"]
        assert {r["document_id"] for r in power} == {first, second}  # two equal bills: suggested
        unpaid = client.get(f"{PAGES}/inbox/blocks/1").json()
        assert unpaid["total"] == 2 and unpaid["totals"]["amount"] == {"EUR": "168.40"}

        pick = next(r for r in power if r["document_id"] == second)
        assert client.post(f"{PAGES}/inbox/actions/accept", json=pick).status_code == 403  # CSRF
        done = client.post(f"{PAGES}/inbox/actions/accept", json=pick, headers=CSRF)
        assert done.json()["message"] == "Matched."
        assert archive.document(second).facts["paid_on"].value == "2026-03-03"
        refused = client.post(
            f"{PAGES}/inbox/actions/accept", json={"transaction_id": 0}, headers=CSRF
        )
        assert refused.status_code == 422 and "No document" in refused.json()["error"]["message"]
        elsewhere = client.post(f"{PAGES}/accounts/actions/accept", json=pick, headers=CSRF)
        assert elsewhere.status_code == 404  # an action works only on the page that shows it

        table = client.get(f"{PAGES}/transactions/blocks/0", params={"q": "stadtwerke"}).json()
        assert [r["state"] for r in table["rows"]] == ["Matched"]
        yearly = client.get(
            f"{PAGES}/transactions/blocks/0", params={"booking_date": "2025"}
        ).json()
        assert yearly["total"] == 0
        options = client.get(f"{PAGES}/transactions/blocks/0").json()["options"]["account"]
        account = options[0]["value"]
        renamed = client.post(
            f"{PAGES}/accounts/actions/rename_account",
            json={"account": account, "name": "Household", "shared": True},
            headers=CSRF,
        )
        assert renamed.json()["message"] == "Saved."
        empty = client.post(
            f"{PAGES}/accounts/actions/rename_account",
            json={"account": account, "name": ""},
            headers=CSRF,
        )
        assert empty.json()["error"]["details"]["fields"] == {"name": "Give the account a name"}

        dashboard = client.get("/api/plugin-pages/slots/dashboard").json()
        assert [d["plugin"] for d in dashboard] == ["bank"]
        summary = client.get(f"{PAGES}/_dashboard/blocks/0").json()["items"]
        assert summary[2] == {"label": "Latest statement", "value": "2026-03-31", "format": "date"}

        panel = client.get(f"/api/plugin-pages/slots/document/{second}").json()
        assert [p["plugin"] for p in panel] == ["bank"]
        paid = client.get(f"{PAGES}/_document/blocks/0", params={"document_id": second}).json()
        assert [r["amount"] for r in paid["rows"]] == ["-84.20"]

        bob = signed_in("bob")
        assert bob.get(f"{PAGES}/inbox/blocks/0").json()["rows"] == []
        shared = bob.get(f"{PAGES}/transactions/blocks/0").json()
        assert shared["total"] == 4  # alice shared the account with the household
        assert (
            bob.get(f"{PAGES}/_document/blocks/0", params={"document_id": second}).status_code
            == 404
        )
        assert bob.post(f"{PAGES}/inbox/actions/accept", json=pick, headers=CSRF).status_code == 422
        assert bob.get(f"{PAGES}/nowhere").status_code == 404
