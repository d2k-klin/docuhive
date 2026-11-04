"""Reusable contract assertions for the fakes supplied to CL."""

import pytest
from docuhive.contracts import CurrentUser, FactValue, IngestRequest, MetadataPatch, SearchFilters
from docuhive.documents import NotFound


@pytest.fixture
def store(fake_core, document):
    fake_core.documents.docs[document.id] = document
    return fake_core.documents


def test_manual_field_protection_force_and_unlock(store, document):
    doc_id = document.id
    result = store.apply_metadata(doc_id, MetadataPatch(title="My title"), actor="user:1")
    assert result.applied == ["title"]
    result = store.apply_metadata(doc_id, MetadataPatch(title="AI title"), actor="ai:classify")
    assert result.skipped_manual == ["title"]
    assert store.get(doc_id).title == "My title"
    store.apply_metadata(doc_id, MetadataPatch(title="Forced"), actor="ai:classify", force=True)
    assert store.get(doc_id).title == "Forced"
    store.apply_metadata(doc_id, MetadataPatch(unlock_fields=["title"]), actor="user:1")
    assert store.jobs.jobs[-1]["payload"]["unlocked"] == ["title"]
    store.apply_metadata(doc_id, MetadataPatch(title="New AI"), actor="ai:classify")
    assert store.get(doc_id).title == "New AI"


def test_facts_merge_delete_and_no_event_on_no_change(store, document):
    patch = MetadataPatch(facts={"amount": FactValue(type="money", value="84.20", currency="EUR")})
    store.apply_metadata(document.id, patch, actor="system")
    count = len(store.jobs.jobs)
    store.apply_metadata(document.id, patch, actor="system")
    assert len(store.jobs.jobs) == count
    store.apply_metadata(document.id, MetadataPatch(facts={"amount": None}), actor="system")
    assert store.get(document.id).facts == {}


def test_invalid_patch_is_atomic_and_non_user_cannot_unlock(store, document):
    with pytest.raises(ValueError):
        store.apply_metadata(
            document.id, MetadataPatch(title="changed", tags_add=[" "]), actor="user:1"
        )
    assert store.get(document.id).title == document.title
    with pytest.raises(ValueError):
        store.apply_metadata(
            document.id, MetadataPatch(unlock_fields=["title"]), actor="ai:classify"
        )


def test_read_permissions_include_no_admin_data_override(store, document):
    other = CurrentUser(id=2, username="other", role="admin")
    with pytest.raises(NotFound):
        store.get_for_user(document.id, other)
    store.docs[document.id].shared = True
    assert store.get_for_user(document.id, other).id == document.id
    assert list(store.iter_ids(filters=SearchFilters(document_ids=["other"]))) == []


def test_content_bound_and_copy_isolation(store, document):
    store.contents[document.id] = "abcdef"
    assert store.get_content(document.id, 3) == "abc"
    assert store.get_content(document.id, 0) == ""
    copy = store.get(document.id)
    copy.tags.append("changed")
    assert store.get(document.id).tags == []


def test_ingest_dedupe_is_per_owner_and_events_preserve_hints(fake_core, document):
    files = fake_core.ingest.incoming_dir()
    path = files / "first.pdf"
    path.write_bytes(b"%PDF-1.4\nsynthetic")
    request = IngestRequest(owner_id=1, source=document.source, hints={"doc_hint": "invoice"})
    result = fake_core.ingest.submit([path], request)
    assert result.status == "staged" and not path.exists()
    path.write_bytes(b"%PDF-1.4\nsynthetic")
    duplicate = fake_core.ingest.submit([path], request)
    assert duplicate.status == "duplicate" and duplicate.document_id == result.document_id
    assert not path.exists()
    path.write_bytes(b"%PDF-1.4\nsynthetic")
    other = fake_core.ingest.submit([path], request.model_copy(update={"owner_id": 2}))
    assert other.document_id != result.document_id
    assert fake_core.jobs.jobs[0]["payload"]["hints"] == {"doc_hint": "invoice"}


def test_fake_jobs_dedupe(fake_core):
    jobs = fake_core.jobs
    first = jobs.enqueue("document.stored", {}, queue="ai", dedupe_key="one")
    assert jobs.enqueue("document.stored", {}, queue="ai", dedupe_key="one") == first
    jobs.jobs[0]["status"] = "done"
    assert jobs.enqueue("document.stored", {}, dedupe_key="one") != first


@pytest.mark.parametrize(
    "fact",
    [
        FactValue(type="money", value="NaN", currency="EUR"),
        FactValue(type="number", value="invalid"),
        FactValue(type="date", value="2026-02-29"),
    ],
)
def test_invalid_canonical_facts_leave_all_metadata_unchanged(store, document, fact):
    before = store.get(document.id)
    with pytest.raises(ValueError):
        store.apply_metadata(
            document.id, MetadataPatch(title="Changed", facts={"field": fact}), actor="user:1"
        )
    assert store.get(document.id) == before


def test_valid_date_fact_and_title_boundary(store, document):
    result = store.apply_metadata(
        document.id,
        MetadataPatch(facts={"due_date": FactValue(type="date", value="2026-11-20")}),
        actor="user:1",
    )
    assert result.applied == ["facts.due_date"]
    with pytest.raises(ValueError):
        store.apply_metadata(document.id, MetadataPatch(title="a" * 121), actor="user:1")
    with pytest.raises(ValueError):
        store.apply_metadata(document.id, MetadataPatch(title="Changed"), actor="unknown")
