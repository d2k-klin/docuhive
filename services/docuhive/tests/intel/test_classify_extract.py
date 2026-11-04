from datetime import date

import pytest
from docuhive import review
from docuhive.agents import pipeline
from docuhive.agents.classify import classify
from docuhive.agents.extract import extract
from docuhive.contracts import CurrentUser

from tests.fakes.intel import use_routing

INVOICE = """Stadtwerke Musterstadt GmbH
Stromrechnung Nr. 2025-1101
Rechnungsdatum: 01.11.2025
Zeitraum 01.10.2025 - 31.10.2025
Gesamtbetrag: 84,20 €
Zahlbar bis 20.11.2025
IBAN DE89 3704 0044 0532 0130 00"""

CONF = {
    f: 0.95
    for f in (
        "title",
        "category",
        "document_type",
        "correspondent",
        "tags",
        "document_date",
        "language",
    )
}


def out(**kw):
    base = {
        "title": "Stromrechnung November 2025",
        "category": "utilities/electricity",
        "document_type": "invoice",
        "correspondent": "Stadtwerke Musterstadt",
        "tags": [],
        "document_date": "2025-11-01",
        "language": "de",
        "confidence": dict(CONF),
        "reasoning": "Electricity invoice.",
    }
    return base | kw


EXTRACT = {
    "amount_total": {
        "value": "84,20 €",
        "currency": None,
        "confidence": 0.95,
        "evidence": "Gesamtbetrag: 84,20 €",
    },
    "due_date": {"value": "20.11.2025", "confidence": 0.9},
    "iban": {"value": "DE89 3704 0044 0532 0130 00", "confidence": 0.9},
    "invoice_number": {"value": "2025-1101", "confidence": 0.9},
}


def auto(mp, on=True):
    use_routing(
        mp,
        tasks={
            "classify": {
                "route": "local/m",
                "apply": {
                    "auto": on,
                    "threshold": 0.8,
                    "per_field": {"document_date": 0.9, "correspondent": 0.85},
                },
            },
            "extract": {"route": "local/m", "apply": {"auto": on}},
        },
    )


def test_auto_false_only_review_items_plus_language(core, fake):
    fake(outputs={"*": out()})
    doc = core.docs.add(INVOICE)
    classify(doc)
    v = core.docs.get(doc)
    assert v.language == "de" and v.category is None
    fields = {r["field"] for r in core.rows("review_items", status="pending")}
    assert fields == {"title", "category", "document_type", "correspondent", "document_date"}
    assert core.docs.calls[0][2] == "ai:classify"
    assert core.docs.provenance[doc]["classify"].prompt_version == "classify@1"


def test_auto_true_threshold_split(core, fake, monkeypatch):
    auto(monkeypatch)
    fake(outputs={"*": out(confidence=CONF | {"document_date": 0.85, "title": 0.5})})
    doc = core.docs.add(INVOICE)
    classify(doc)
    v = core.docs.get(doc)
    assert (v.category, v.document_type) == ("utilities/electricity", "invoice")
    assert v.document_date is None  # 0.85 < per-field 0.90
    pending = {r["field"] for r in core.rows("review_items", status="pending")}
    # a correspondent not seen before is capped at 0.7, so it is reviewed
    assert pending == {"title", "document_date", "correspondent"}


def test_unknown_category_retried_with_error(core, fake):
    m = fake(outputs={"*": [out(category="utilities/strom"), out()]})
    classify(core.docs.add(INVOICE))
    assert "category 'utilities/strom' is not one of the listed ids" in m.calls[1]["text"]


def test_unknown_tag_becomes_proposed_term(core, fake):
    fake(outputs={"*": out(tags=["important", "energy"])})
    doc = core.docs.add(INVOICE)
    classify(doc)
    terms = core.rows("review_items", kind="new_term")
    assert [t["field"] for t in terms] == ["tag:energy"]
    tags = [r for r in core.rows("review_items", field="tags")]
    assert tags[0]["suggested"] == {"value": ["important"]}


def test_correspondent_fuzzy_match_and_new_name_capped(core, fake, monkeypatch):
    auto(monkeypatch)
    core.docs.add("old", correspondent="Stadtwerke Musterstadt")
    fake(outputs={"*": out(correspondent="Stadtwerke Musterstadt GmbH")})
    doc = core.docs.add(INVOICE)
    classify(doc)
    assert core.docs.get(doc).correspondent == "Stadtwerke Musterstadt"
    fake(outputs={"*": out(correspondent="Brand New Energy AG")})
    doc2 = core.docs.add(INVOICE + " 2")
    classify(doc2)
    [item] = core.rows("review_items", document_id=doc2, field="correspondent")
    assert item["confidence"] == 0.7  # new correspondents are reviewed until auto is trusted


def test_future_date_is_nulled(core, fake, monkeypatch):
    auto(monkeypatch)
    fake(outputs={"*": out(document_date="2099-01-01")})
    doc = core.docs.add(INVOICE)
    classify(doc)
    assert core.docs.get(doc).document_date is None
    assert not core.rows("review_items", field="document_date")


def test_manual_fields_not_touched(core, fake, monkeypatch):
    auto(monkeypatch)
    fake(outputs={"*": out()})
    doc = core.docs.add(INVOICE, category="housing/rent", manual_fields=["category"])
    classify(doc)
    assert core.docs.get(doc).category == "housing/rent"
    assert not core.rows("review_items", field="category")


def test_extract_validates_and_applies(core, fake, monkeypatch):
    auto(monkeypatch)
    fake(outputs={"*": EXTRACT})
    doc = core.docs.add(INVOICE, document_type="invoice")
    extract(doc)
    facts = core.docs.get(doc).facts
    assert facts["amount_total"].value == "84.20" and facts["amount_total"].currency == "EUR"
    assert facts["due_date"].value == "2025-11-20"
    assert facts["iban"].value == "DE89370400440532013000"


def test_extract_invalid_and_missing_required(core, fake, monkeypatch):
    auto(monkeypatch)
    fake(outputs={"*": {"iban": {"value": "DE00 1234", "confidence": 0.9}}})
    doc = core.docs.add(INVOICE, document_type="invoice")
    extract(doc)
    items = {r["field"]: r["reason"] for r in core.rows("review_items", status="pending")}
    assert items["facts.amount_total"] == "missing required fact"
    assert items["facts.iban"].startswith("invalid:")


def test_pipeline_stored_to_embed(core, fake):
    fake(outputs={"Classify": out(), "Extract facts": EXTRACT})
    doc = core.docs.add(INVOICE)
    core.jobs.enqueue("document.stored", {"document_id": doc, "hints": {}}, queue="ai")
    core.jobs.run()
    done = {j.kind for j in core.jobs.all if j.status == "done"}
    assert {"document.stored", "ai.classify", "ai.extract"} <= done
    assert {"index.embed", "reminders.sync"} <= {j.kind for j in core.jobs.all}
    assert core.rows("review_items", field="facts.amount_total")


def test_pipeline_rebuild_hint_only_embeds(core):
    doc = core.docs.add(INVOICE)
    core.jobs.enqueue("document.stored", {"document_id": doc, "hints": {"rebuild": "true"}})
    core.jobs.run({"document.stored"})
    assert [j.kind for j in core.jobs.pending()] == ["index.embed"]


def test_restricted_without_local_route_gives_notice(core, fake, monkeypatch):
    use_routing(
        monkeypatch, tasks={"classify": {"route": "cloud/m"}, "extract": {"route": "cloud/m"}}
    )
    m = fake("cloud/m", outputs={"*": out()})
    doc = core.docs.add("Befund ...")  # unclassified -> classified locally first; none exists
    core.jobs.enqueue("ai.classify", {"document_id": doc}, queue="ai")
    core.jobs.run({"ai.classify"})
    assert m.calls == []
    [n] = core.rows("review_items", kind="notice")
    assert "no local model configured" in n["reason"]


def test_budget_defers_bulk_job(core, fake, monkeypatch):
    use_routing(monkeypatch, tasks={"extract": {"route": "cloud/m"}}, budgets={"cloud": 0.0})
    fake("cloud/m", outputs={"*": EXTRACT})
    doc = core.docs.add(INVOICE, category="utilities", document_type="invoice")
    core.jobs.enqueue("ai.extract", {"document_id": doc}, queue="ai")
    [job] = core.jobs.run({"ai.extract"})
    assert job.status == "deferred" and job.note.startswith("budget")


def test_user_change_supersedes_and_reextracts(core, fake):
    fake(outputs={"*": out()})
    doc = core.docs.add(INVOICE)
    classify(doc)
    user = CurrentUser(id=1, username="dev", role="admin")
    [item] = core.rows("review_items", field="document_type", status="pending")
    review.accept(item["id"], user, value="receipt")
    assert "document_type" in core.docs.get(doc).manual_fields
    core.jobs.run({"document.metadata_changed"})
    assert "ai.extract" in core.jobs.kinds()


def test_metadata_changed_from_user_supersedes_pending(core, fake):
    fake(outputs={"*": out()})
    doc = core.docs.add(INVOICE)
    classify(doc)
    pipeline.on_metadata_changed(
        {"document_id": doc, "fields": ["category"], "actor": "user:1"}, None
    )
    assert core.rows("review_items", field="category")[0]["status"] == "superseded"


def test_purge_deletes_intel_rows(core, fake):
    fake(outputs={"*": out()})
    doc = core.docs.add(INVOICE)
    classify(doc)
    pipeline.on_purged({"document_id": doc}, None)
    assert core.count("review_items", document_id=doc) == 0
    assert all(r["document_id"] is None for r in core.rows("ai_runs"))


@pytest.mark.parametrize("value", [date(2025, 1, 1)])
def test_review_accept_with_edit_makes_field_manual(core, fake, value):
    fake(outputs={"*": out()})
    doc = core.docs.add(INVOICE)
    classify(doc)
    [item] = core.rows("review_items", field="document_date")
    review.accept(
        item["id"], CurrentUser(id=1, username="dev", role="admin"), value=value.isoformat()
    )
    v = core.docs.get(doc)
    assert v.document_date == value and "document_date" in v.manual_fields


def test_non_owner_cannot_resolve(core, fake):
    fake(outputs={"*": out()})
    doc = core.docs.add(INVOICE, owner_id=1, shared=True)
    classify(doc)
    [item] = core.rows("review_items", field="category")
    with pytest.raises(review.ReviewError) as e:
        review.accept(item["id"], CurrentUser(id=2, username="m", role="member"))
    assert e.value.status == 403
