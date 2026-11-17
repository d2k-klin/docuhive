"""Craftsman invoices: labour, warranty, the § 35a reduction; upkeep tasks."""

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

ROOF = {
    "labour_net": "4000.00",
    "vat_rate": "19",
    "material_gross": "6000.00",
    "total": "10760.00",
    "work_date": "2026-03-10",
    "kind": "building",
}


def call(archive, how, source, user, /, **params):
    registry = archive.registry("handwerk")
    fn = registry.data_sources[source] if how == "data" else registry.actions[source][0]
    return fn(user, params)


def arrive(archive, owner, answer, **doc):
    fake.REGISTRY["test/model"].outputs["*"] = answer
    doc_id = archive.add(owner, document_type="craftsman_invoice", **doc)
    archive.emit("document.classified", document_id=doc_id, document_type="craftsman_invoice")
    archive.run_jobs()
    return doc_id


def test_labour_warranty_and_the_tax_reduction():
    with Archive(PLUGIN, ai={"*": ROOF}) as archive:
        alice, bob = archive.user("alice"), archive.user("bob")
        roof = arrive(archive, alice, ROOF, title="Dach", date=date(2026, 3, 12))
        facts = archive.document(roof).facts
        assert facts["labour_cost"].value == "4760.00"  # net labour plus 19 %
        assert facts["warranty_until"].value == "2031-03-10"  # building work: five years
        cleaning = arrive(
            archive,
            alice,
            {"labour_gross": "900.00", "total": "900.00", "kind": "household"},
            title="Fensterreinigung",
            date=date(2026, 5, 2),
        )
        assert "warranty_until" not in archive.document(cleaning).facts
        cash = arrive(
            archive,
            alice,
            {
                "labour_gross": "300.00",
                "total": "300.00",
                "kind": "craftsman",
                "paid_in_cash": True,
            },
            title="Reparatur",
            date=date(2026, 6, 1),
        )
        # A reading with more labour than the whole invoice is dropped, not believed.
        wrong = arrive(
            archive,
            alice,
            {"labour_gross": "500.00", "total": "200.00", "kind": "craftsman"},
            title="Kleinreparatur",
            date=date(2026, 7, 1),
        )
        assert "labour_cost" not in archive.document(wrong).facts

        rows = {r["title"]: r for r in call(archive, "data", "invoices", alice, year="2026")}
        assert rows["Dach"]["share"]["value"] == D("952.00")
        assert rows["Reparatur"]["note"] == "Paid in cash: does not count"
        assert rows["Kleinreparatur"]["note"] == "Labour missing"
        reduction = {
            r["kind"]: r["reduction"]["value"]
            for r in call(archive, "data", "reduction", alice, year="2026")
        }
        assert reduction == {"craftsman": D("952.00"), "household": D("180.00")}
        assert call(archive, "data", "invoices", bob, year="2026") == []
        assert call(archive, "data", "reduction", alice, year="2019") == []
        assert cash in [r["id"] for r in call(archive, "data", "invoices", alice, year="2026")]

        # The cap: another big job in the same year adds nothing beyond 1,200 €.
        arrive(
            archive,
            alice,
            {"labour_gross": "2000.00", "total": "2500.00", "kind": "craftsman"},
            title="Bad",
            date=date(2026, 9, 1),
        )
        craftsman = call(archive, "data", "reduction", alice, year="2026")[0]
        assert craftsman["reduction"]["value"] == D("1200")
        assert (
            archive.tool("handwerk", "home_costs")(alice, year=2026)["reduction"][
                craftsman["label"]
            ]
            == "1200"
        )
        [panel] = call(archive, "data", "document_work", alice, document_id=roof)
        assert panel["warranty_until"] == "2031-03-10"


def test_upkeep_tasks_and_an_invoice_that_marks_one_done():
    with Archive(PLUGIN, ai={"*": {}}) as archive:
        alice = archive.user("alice")
        assert call(archive, "action", "add_task", alice).errors == {
            "name": "Name the task, or choose one of the usual ones"
        }
        made = call(
            archive, "action", "add_task", alice, preset="chimney_sweep", last_done="2025-11-20"
        )
        assert "due on 20.11.2026" in made.message
        again = call(archive, "action", "add_task", alice, name="Chimney sweep", every_months=6)
        assert again.errors == {"name": "You already have a task with this name"}
        call(archive, "action", "add_task", alice, name="Garage door", every_months=24)
        names = [t["name"] for t in call(archive, "data", "tasks", alice)]
        assert names == ["Garage door", "Chimney sweep"]  # due now, then November
        presets = [o["value"] for o in call(archive, "data", "preset_options", alice)]
        assert "chimney_sweep" not in presets
        ids = {t["id"] for t in call(archive, "data", "tasks", alice)}
        with session() as s:
            facts = {r.fact for r in s.scalars(select(Reminder))}
        assert {f"plugin:handwerk:task:{i}" for i in ids} <= facts

        sweep = arrive(
            archive,
            alice,
            {
                "labour_gross": "95.00",
                "total": "95.00",
                "kind": "craftsman",
                "task": "chimney_sweep",
                "work_date": "2026-11-18",
            },
            title="Kehrung",
            date=date(2026, 11, 18),
        )
        task = next(t for t in call(archive, "data", "tasks", alice) if t["preset"])
        assert (task["last_done"], task["next_due"], task["document_id"]) == (
            date(2026, 11, 18),
            date(2027, 11, 18),
            sweep,
        )
        with pytest.raises(ActionError):
            call(archive, "action", "task_done", archive.user("bob"), id=task["id"])
        assert call(archive, "action", "remove_task", alice, id=task["id"]) == "Removed."
        with session() as s:
            gone = f"plugin:handwerk:task:{task['id']}"
            assert gone not in {r.fact for r in s.scalars(select(Reminder))}
