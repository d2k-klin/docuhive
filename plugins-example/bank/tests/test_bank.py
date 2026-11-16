"""A statement upload becomes payments, matched to the invoices they pay."""

from datetime import date
from pathlib import Path

import pytest
from docuhive.sdk import services
from docuhive.sdk.testing import Archive
from sqlalchemy import text

from .samples import CAMT, ING_CSV

pytestmark = pytest.mark.integration
PLUGIN = Path(__file__).resolve().parents[1]


CAMT_BYTES = CAMT.encode()


def statement(archive, owner, name="march.xml", data=CAMT_BYTES):
    doc = archive.add(owner, original=(name, data))
    archive.emit("document.stored", document_id=doc)
    archive.run_jobs()
    return doc


def rows(archive, sql, **params):
    with archive.registry("bank").db.session() as s:
        return s.execute(text(sql), params).all()


def test_import_match_and_ask():
    with Archive(PLUGIN) as archive:
        alice, bob = archive.user("alice"), archive.user("bob")
        power = archive.add(
            alice,
            document_type="invoice",
            date=date(2026, 2, 28),
            facts={"amount_total": ("84.20", "EUR"), "invoice_number": "RE-2026-0042"},
        )
        twin = archive.add(  # same amount, other sender: must not be taken by mistake
            alice,
            document_type="invoice",
            date=date(2026, 3, 1),
            facts={"amount_total": ("84.20", "EUR")},
        )
        doc = statement(archive, alice)

        view = archive.document(doc)
        assert view.document_type == "bank-statement" and view.category == "finance/banking"
        assert view.facts["closing_balance"].value == "2715.80"
        assert "private" in view.tags  # statements stay with local AI models
        assert rows(archive, "SELECT complete FROM statements") == [(True,)]
        amounts = [
            r[0]
            for r in rows(archive, "SELECT amount FROM transactions ORDER BY booking_date, amount")
        ]
        assert [str(a) for a in amounts] == ["-84.20", "500.00", "1500.00", "-200.00"]
        assert rows(archive, "SELECT ignored_reason FROM transactions WHERE amount = -200") == [
            ("Cash withdrawal",)
        ]
        assert archive.document(power).facts["paid_on"].value == "2026-03-03"
        assert "paid_on" not in archive.document(twin).facts
        assert services.get("bank.payments_for")(power)[0]["date"] == date(2026, 3, 3)

        # The same statement again, and an overlapping CSV export: nothing twice.
        statement(archive, alice, "march-again.xml", CAMT.encode() + b"\n")
        assert rows(archive, "SELECT count(*) FROM transactions WHERE amount = -84.20") == [(1,)]

        ask = archive.tool("bank", "payments")
        answer = ask(alice, counterparty="Stadtwerke", year=2026)
        assert answer["totals"] == {"EUR": {"paid": "84.20", "received": "0"}}
        assert answer["documents"]
        assert ask(bob, year=2026)["payments"] == 0  # bob sees nothing of alice's accounts
        hidden = ask(alice, year=2026, exclude_ids=set(answer["documents"]))
        assert hidden["payments"] == 0  # a cloud model gets nothing from private statements


def test_a_person_confirms_a_suggestion_and_ignores_a_payee():
    with Archive(PLUGIN) as archive:
        alice = archive.user("alice")
        first = archive.add(
            alice,
            document_type="invoice",
            date=date(2026, 3, 1),
            facts={"amount_total": ("84.20", "EUR")},
            title="Stadtwerke Beispiel",
        )
        second = archive.add(
            alice,
            document_type="invoice",
            date=date(2026, 3, 2),
            facts={"amount_total": ("84.20", "EUR")},
        )
        from docuhive import documents
        from docuhive.contracts import MetadataPatch

        for doc in (first, second):  # two equal bills from the same sender: a person decides
            documents.apply_metadata(
                doc, MetadataPatch(correspondent="Stadtwerke Beispiel"), actor="system"
            )
        statement(archive, alice, "march.csv", ING_CSV)
        [(tx_id,)] = rows(archive, "SELECT id FROM transactions WHERE amount = -84.20")
        suggested = {
            r[0] for r in rows(archive, "SELECT document_id FROM matches WHERE state = 'suggested'")
        }
        assert suggested == {first, second}
        assert services.get("bank.accept_suggestion")(alice, tx_id, second) == "Matched."
        assert archive.document(second).facts["paid_on"].value == "2026-03-03"
        assert rows(archive, "SELECT count(*) FROM matches WHERE state = 'suggested'") == [(0,)]
        intruder = archive.user("mallory")
        with pytest.raises(LookupError):
            services.get("bank.accept_suggestion")(intruder, tx_id, first)
        [(income_id,)] = rows(archive, "SELECT id FROM transactions WHERE amount = 2000")
        services.get("bank.ignore_counterparty")(alice, income_id, "Salary")
        assert rows(
            archive, "SELECT ignored_reason FROM transactions WHERE id = :i", i=income_id
        ) == [("Salary",)]
