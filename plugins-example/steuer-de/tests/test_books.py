"""A golden quarter: invoices in, bookings confirmed, the VAT return figures, closing, deadlines."""

from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
from docuhive import documents as documents_core
from docuhive.documents.holds import Held
from docuhive.sdk import ActionError
from docuhive.sdk.testing import Archive
from sqlalchemy import text
from steuer_samples import CII, UBL

pytestmark = pytest.mark.integration
PLUGIN = Path(__file__).resolve().parents[1]
Q1 = {"key": "2026-Q1"}


def call(archive, how, source, user, /, **params):
    registry = archive.registry("steuer-de")
    fn = registry.data_sources[source] if how == "data" else registry.actions[source][0]
    return fn(user, params)


def entries(archive, where="true", **params):
    with archive.registry("steuer-de").db.session() as s:
        return [
            dict(r)
            for r in s.execute(
                text(f"SELECT * FROM entries WHERE {where} ORDER BY id"), params
            ).mappings()
        ]


def arrive(archive, owner, **doc):
    doc_id = archive.add(owner, **doc)
    archive.emit("document.classified", document_id=doc_id, document_type=doc.get("document_type"))
    archive.run_jobs()
    return doc_id


def test_a_quarter_from_invoice_to_closed_return():
    with Archive(PLUGIN) as archive:
        alice, bob = archive.user("alice"), archive.user("bob")
        made = call(
            archive,
            "action",
            "save_book",
            alice,
            name="Studio",
            kind="euer",
            chart="skr03",
            vat_status="regular",
            vat_period="quarterly",
            vat_basis="invoice",
        )
        assert "created" in made.message

        office = arrive(
            archive,
            alice,
            document_type="invoice",
            date=date(2026, 3, 2),
            original=("rechnung.xml", CII.encode()),
        )
        cloud = arrive(
            archive,
            alice,
            document_type="invoice",
            date=date(2026, 3, 5),
            original=("invoice.xml", UBL.encode()),
        )
        receipt = arrive(
            archive,
            alice,
            document_type="receipt",
            date=date(2026, 3, 20),
            facts={"amount_total": ("11.90", "EUR"), "amount_tax": ("1.90", "EUR")},
        )
        archive.emit("document.classified", document_id=office, document_type="invoice")
        archive.run_jobs()  # the same event twice books nothing twice

        rows = entries(archive)
        assert [
            (r["document_id"], r["net"], r["vat"], r["vat_code"], r["origin"]) for r in rows
        ] == [
            (office, D("100.00"), D("19.00"), "purchase_19", "e_invoice"),
            (office, D("50.00"), D("3.50"), "purchase_7", "e_invoice"),
            (cloud, D("200.00"), D("0.00"), "purchase_rc_eu", "e_invoice"),
            (receipt, D("10.00"), D("1.90"), "purchase_19", "ai"),
        ]
        assert all(r["state"] == "proposed" for r in rows)
        assert "Reverse charge" in rows[2]["note"]
        assert archive.document(office).facts["invoice_number"].value == "RE-2026-0042"

        # Nothing counts until confirmed; an account must be chosen first.
        assert call(archive, "data", "period_fields", alice, **Q1)[-1]["value"]["value"] == 0
        with pytest.raises(ActionError):
            call(archive, "action", "confirm_as_proposed", alice, id=rows[3]["id"])
        for row, account in zip(rows, ["4930", "3300", "3123", "4930"], strict=True):
            call(
                archive,
                "action",
                "confirm_entry",
                alice,
                entry=row["id"],
                account=account,
                always=row["document_id"] == office and account == "4930",
            )
        call(
            archive,
            "action",
            "add_entry",
            alice,
            direction="income",
            entry_date="2026-03-10",
            counterparty="Kunde Beispiel",
            gross="1190.00",
            vat_code="sale_19",
            account="8400",
            paid_on="2026-03-12",
        )
        with pytest.raises(ActionError):  # bob has no book and cannot write in alice's
            call(archive, "action", "confirm_entry", bob, entry=rows[0]["id"], account="4930")

        fields = {f["field"]: f for f in call(archive, "data", "period_fields", alice, **Q1)}
        assert fields["81"]["value"]["value"] == D("1000") and fields["81"]["tax"]["value"] == D(
            "190.00"
        )
        assert fields["46"]["value"]["value"] == D("200")  # reverse charge base
        assert fields["47"]["value"]["value"] == D("38.00")  # the VAT alice owes on it
        assert fields["67"]["value"]["value"] == D("38.00")  # and may deduct again
        assert fields["66"]["value"]["value"] == D("24.40")  # 19.00 + 3.50 + 1.90
        assert fields["83"]["value"]["value"] == D("165.60")  # 190 + 38 - 24.40 - 38
        assert (
            archive.tool("steuer-de", "vat_return")(alice, year=2026, period="Q1")["amount_due"]
            == "165.60"
        )
        assert archive.tool("steuer-de", "vat_return")(bob, year=2026)["summary"] == "No book yet"

        # Income-surplus accounting counts what was paid: only the sale so far.
        year = {
            r["label"]: r["amount"]["value"]
            for r in call(archive, "data", "year_statement", alice, year=2026)
        }
        assert year["Business income subject to VAT"] == D("1000.00")
        assert year["Surplus (income minus expenses)"] == D("1190.00")

        # The rule learnt from "always": the next office invoice is proposed on 4930 by itself.
        again = arrive(
            archive,
            alice,
            document_type="invoice",
            date=date(2026, 4, 2),
            original=(
                "rechnung-2.xml",
                CII.replace("RE-2026-0042", "RE-2026-0077")
                .replace("20260302", "20260402")
                .encode(),
            ),
        )
        proposed = entries(archive, "document_id = :d", d=again)
        assert proposed[0]["account"] == "4930" and "Your rule" in proposed[0]["note"]

        # Closing freezes the quarter; the figures stay as they were closed.
        assert "closed" in call(archive, "action", "close_period", alice, **Q1)
        assert {r["state"] for r in entries(archive, "period_vat = '2026-Q1'")} == {"closed"}
        with pytest.raises(ActionError):
            call(archive, "action", "confirm_entry", alice, entry=rows[0]["id"], account="4910")
        with pytest.raises(Exception, match="closed period"):
            with archive.registry("steuer-de").db.session() as s:
                s.execute(
                    text("UPDATE entries SET net = 1, gross = 1 + vat WHERE id = :i"),
                    {"i": rows[0]["id"]},
                )
        assert call(archive, "data", "period_summary", alice, **Q1)[0]["value"] == "Closed"
        # The documents are locked for the retention period (eight years after 2026).
        held = archive.document(office)
        with pytest.raises(Held):
            documents_core.set_trashed(office, alice, True)
        assert held.deleted_at is None


def test_deadlines_become_reminders():
    from docuhive import db
    from docuhive.reminders.models import Reminder
    from sqlalchemy import select

    with Archive(PLUGIN) as archive:
        alice = archive.user("alice")
        call(
            archive,
            "action",
            "save_book",
            alice,
            name="Studio",
            kind="euer",
            chart="skr03",
            vat_period="quarterly",
        )
        archive.run_jobs()  # saving a book queues the deadline check
        with db.session() as s:
            due = s.execute(
                select(Reminder.fact, Reminder.due_on).where(Reminder.owner_id == alice.id)
            ).all()
        assert due, "the coming VAT deadline is a reminder"
        assert all(r.fact.startswith("plugin:steuer-de:vat:") for r in due)
        assert all(r.due_on.weekday() < 5 for r in due)


def test_a_paper_receipt_read_by_the_ai_must_add_up():
    answers = {
        "Copy what is printed": [
            {  # 19 % of 20.00 is not 5.00: refused, so the second reading is used
                "supplier": "Copyshop Beispiel",
                "invoice_date": "2026-02-11",
                "lines": [{"rate": "19", "net": "20.00", "tax": "5.00"}],
                "gross": "25.00",
            },
            {
                "supplier": "Copyshop Beispiel",
                "invoice_date": "2026-02-11",
                "lines": [{"rate": "19", "net": "20.00", "tax": "3.80"}],
                "gross": "23.80",
            },
        ],
        "choose the bookkeeping account": {
            "account": "4930",
            "reason": "Copies",
            "confidence": 0.8,
        },
    }
    with Archive(PLUGIN, ai=answers) as archive:
        alice = archive.user("alice")
        call(archive, "action", "save_book", alice, name="Studio", kind="euer", chart="skr03")
        doc = arrive(
            archive, alice, document_type="receipt", date=date(2026, 2, 11), content="Kopien 23,80"
        )
        (row,) = entries(archive, "document_id = :d", d=doc)
        assert (row["net"], row["vat"], row["account"]) == (D("20.00"), D("3.80"), "4930")
        assert row["counterparty"] == "Copyshop Beispiel" and row["state"] == "proposed"


def test_documents_from_before_the_book_can_be_booked_later():
    with Archive(PLUGIN) as archive:
        alice = archive.user("alice")
        early = arrive(
            archive,
            alice,
            document_type="invoice",
            date=date(2026, 3, 2),
            original=("rechnung.xml", CII.encode()),
        )
        assert entries(archive) == []  # no book yet: nothing to propose into
        call(archive, "action", "save_book", alice, name="Studio", kind="euer", chart="skr03")
        message = call(archive, "action", "book_missing", alice, **Q1)
        assert message.startswith("1 documents")
        archive.run_jobs()
        assert [r["document_id"] for r in entries(archive)] == [early, early]
        assert "Every invoice" in call(archive, "action", "book_missing", alice, **Q1)


def test_small_business_watch_and_hand_over_books():
    this_year = date.today().year
    with Archive(PLUGIN) as archive:
        alice, bob = archive.user("alice"), archive.user("bob")
        call(
            archive,
            "action",
            "save_book",
            alice,
            name="Shop",
            kind="euer",
            chart="skr03",
            vat_status="small_business",
            vat_period="none",
        )
        call(
            archive,
            "action",
            "add_entry",
            alice,
            direction="income",
            entry_date=f"{this_year}-01-15",
            gross="85000.00",
            vat_code="sale_small_business",
            account="8195",
        )
        (watch,) = [
            r for r in call(archive, "data", "overview", alice) if r["label"].startswith("Turnover")
        ]
        assert watch["value"]["value"] == D("85000.00") and "80 %" in watch["hint"]

        call(
            archive,
            "action",
            "save_book",
            bob,
            name="GmbH",
            kind="hand_over",
            chart="skr04",
            vat_period="monthly",
        )
        with pytest.raises(ActionError, match="tax advisor"):
            call(archive, "action", "close_period", bob, key=f"{this_year}-01")


def test_a_plugin_message_on_a_page_is_shown_not_a_server_error():
    from docuhive.api.app import create_app
    from fastapi.testclient import TestClient

    with Archive(PLUGIN) as archive:
        archive.user("alice")
        client = TestClient(create_app(), base_url="https://testserver")
        client.post(
            "/api/auth/login",
            headers={"X-DocuHive-CSRF": "1"},
            json={"username": "alice", "password": "a synthetic test password"},
        )
        response = client.get("/api/plugin-pages/steuer-de/period/blocks/0?key=2026-Q1")
        assert response.status_code == 422
        assert response.json()["error"]["message"] == "Create a book first."
