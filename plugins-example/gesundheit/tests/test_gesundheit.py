"""Health claims: bills to submit, the insurer's statement matched to them, the own share."""

from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
from docuhive.ai import fake
from docuhive.db import session
from docuhive.reminders.models import Reminder
from docuhive.sdk import ActionError
from docuhive.sdk.testing import Archive
from sqlalchemy import select

pytestmark = pytest.mark.integration
PLUGIN = Path(__file__).resolve().parents[1]


def call(archive, how, source, user, /, **params):
    registry = archive.registry("gesundheit")
    fn = registry.data_sources[source] if how == "data" else registry.actions[source][0]
    return fn(user, params)


def arrive(archive, owner, kind, **doc):
    doc_id = archive.add(owner, document_type=kind, **doc)
    archive.emit("document.classified", document_id=doc_id, document_type=kind)
    archive.run_jobs()
    return doc_id


def bill(archive, owner, title, amount, day, number):
    return arrive(
        archive,
        owner,
        "medical_bill",
        title=title,
        date=day,
        facts={"amount_total": (amount, "EUR"), "treatment_date": day, "bill_number": number},
    )


def reminder_labels():
    with session() as s:
        return {r.fact: r.label for r in s.scalars(select(Reminder))}


def test_from_bill_to_statement_to_own_share():
    with Archive(PLUGIN, ai={"*": {}}) as archive:
        alice, bob = archive.user("alice"), archive.user("bob")
        dentist = bill(archive, alice, "Zahnarzt", "480.00", date(2026, 2, 3), "R-2026-17")
        doctor = bill(archive, alice, "Hausarzt", "86.40", date(2026, 2, 10), "")
        glasses = bill(archive, alice, "Optiker", "320.00", date(2026, 3, 1), "O-55")
        twice = bill(archive, alice, "Labor", "12.00", date(2026, 3, 2), "")
        bill(archive, alice, "Labor 2", "12.00", date(2026, 3, 2), "")

        rows = {r["title"]: r for r in call(archive, "data", "claims", alice)}
        assert {r["state_label"] for r in rows.values()} == {"To submit"}
        assert reminder_labels()[f"plugin:gesundheit:claim:{rows['Zahnarzt']['id']}"] == (
            "Submit to your insurer: Zahnarzt"
        )
        assert call(archive, "data", "claims", bob) == []
        with pytest.raises(ActionError):
            call(archive, "action", "submitted", bob, id=rows["Zahnarzt"]["id"])

        picked = [rows[t] for t in ("Zahnarzt", "Hausarzt", "Labor", "Labor 2")]
        assert "4 bills" in call(archive, "action", "submitted", alice, rows=picked)
        call(archive, "action", "not_claimed", alice, id=rows["Optiker"]["id"])
        assert reminder_labels()[f"plugin:gesundheit:claim:{rows['Hausarzt']['id']}"].startswith(
            "Nothing paid back yet"
        )

        # The statement: one line by number, one by amount and date, one that fits two bills.
        fake.REGISTRY["test/model"].outputs["*"] = {
            "notice_date": "2026-03-20",
            "lines": [
                {"bill_number": "R 2026-17", "billed": "480.00", "reimbursed": "300.00"},
                {"bill_number": "R 2026-17", "billed": "480.00", "reimbursed": "60.00"},
                {"treatment_date": "2026-02-10", "billed": "86.40", "reimbursed": "86.40"},
                {"treatment_date": "2026-03-02", "billed": "12.00", "reimbursed": "12.00"},
            ],
        }
        notice = arrive(archive, alice, "reimbursement_notice", title="Leistungsabrechnung")
        archive.emit(
            "document.classified", document_id=notice, document_type="reimbursement_notice"
        )
        archive.run_jobs()  # read once, never twice

        rows = {r["title"]: r for r in call(archive, "data", "claims", alice)}
        assert rows["Zahnarzt"]["reimbursed"]["value"] == D("360.00")
        assert rows["Zahnarzt"]["own_share"]["value"] == D("120.00")
        assert rows["Hausarzt"]["state_label"] == "Paid back"
        assert rows["Labor"]["state_label"] == "Submitted"
        [line] = call(archive, "data", "unmatched", alice)
        assert line["reimbursed"]["value"] == D("12.00")
        assert f"plugin:gesundheit:claim:{rows['Hausarzt']['id']}" not in reminder_labels()

        call(archive, "action", "match_line", alice, line=line["id"], claim=rows["Labor"]["id"])
        assert call(archive, "data", "unmatched", alice) == []
        call(archive, "action", "paid_back", alice, claim=rows["Labor 2"]["id"], amount="10")

        share = archive.registry("gesundheit").services["own_share"](alice, 2026)
        # 120 (dentist) + 0 (doctor) + 320 (glasses, kept) + 0 + 2
        assert share["own_share"] == D("442.00")
        assert share["still_open"] == 0
        assert set(share["documents"]) == {dentist, doctor, glasses, twice} | {
            rows["Labor 2"]["document_id"]
        }
        [panel] = call(archive, "data", "document_claim", alice, document_id=dentist)
        assert panel["state_label"] == "Paid back"
        assert archive.tool("gesundheit", "health_claims")(alice)["waiting"] == []
