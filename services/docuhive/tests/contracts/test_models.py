"""The binding schema must retain a stable, JSON-friendly public surface."""

from datetime import UTC, datetime

from docuhive.contracts import (
    CONTRACT_VERSION,
    DocumentView,
    FactValue,
    IngestRequest,
    MetadataPatch,
    Provenance,
    SearchFilters,
    SetupCheck,
    SourceInfo,
    SourceKind,
)


def test_document_round_trip(document):
    assert CONTRACT_VERSION == 1
    assert DocumentView.model_validate_json(document.model_dump_json()) == document


def test_mutable_defaults_are_independent():
    left, right = MetadataPatch(), MetadataPatch()
    left.tags_add.append("synthetic")
    assert right.tags_add == []
    assert right.unlock_fields == []
    assert SearchFilters().document_ids == []


def test_event_and_setup_models_round_trip():
    req = IngestRequest(
        owner_id=1, source=SourceInfo(kind=SourceKind.api, original_filename="x.pdf")
    )
    assert IngestRequest.model_validate_json(req.model_dump_json()) == req
    provenance = Provenance(
        task="classify",
        provider="fake",
        model="fake",
        prompt_version="classify@1",
        at=datetime.now(UTC),
    )
    assert provenance.ai_run_id is None
    assert FactValue(type="money", value="84.20", currency="EUR").value == "84.20"
    check = SetupCheck(
        id="vault",
        area="storage",
        title="Connect storage",
        status="todo",
        message="Initialise your vault.",
    )
    assert SetupCheck.model_validate_json(check.model_dump_json()) == check
