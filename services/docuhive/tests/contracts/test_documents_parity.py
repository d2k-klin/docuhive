"""Identical assertions against the public fake and real document contracts."""

import pytest
from docuhive import documents
from docuhive.auth import create_user
from docuhive.contracts import CurrentUser, FactValue, MetadataPatch
from docuhive.db import session
from docuhive.db.models import DocSource, Document
from docuhive.documents import NotFound


@pytest.fixture(
    params=[
        "fake",
        pytest.param(
            "real",
            marks=[
                pytest.mark.integration,
                pytest.mark.xfail(
                    strict=True,
                    raises=NotImplementedError,
                    reason="I3/OA-M3: docs/Developer-QA/bugs.md#qa-001",
                ),
            ],
        ),
    ]
)
def backend(request, document):
    if request.param == "fake":
        fake = request.getfixturevalue("fake_core").documents
        fake.docs[document.id] = document
        return fake
    request.getfixturevalue("postgres")
    owner = create_user("qa-owner", "synthetic qa password 2026")
    document.owner_id = owner
    with session() as db:
        db.add(
            Document(
                id=document.id,
                owner_id=owner,
                shared=False,
                status="stored",
                sha256="a" * 64,
                mime="application/pdf",
                title=document.title,
            )
        )
        db.flush()
        db.add(DocSource(document_id=document.id, kind="upload", original_filename="synthetic.pdf"))
    return documents


@pytest.mark.req("DOC-07", "CLS-06")
def test_user_value_survives_ai_then_unlock_allows_ai(backend, document):
    actor = f"user:{document.owner_id}"
    backend.apply_metadata(document.id, MetadataPatch(title="User title"), actor=actor)
    result = backend.apply_metadata(
        document.id, MetadataPatch(title="AI title"), actor="ai:classify"
    )
    assert "title" in result.skipped_manual
    assert backend.get(document.id).title == "User title"
    backend.apply_metadata(document.id, MetadataPatch(unlock_fields=["title"]), actor=actor)
    backend.apply_metadata(document.id, MetadataPatch(title="AI title"), actor="ai:classify")
    assert backend.get(document.id).title == "AI title"


@pytest.mark.req("AUTH-03", "QA-06")
def test_admin_has_no_private_document_override(backend, document):
    user = CurrentUser(id=document.owner_id + 100, username="qa-other", role="admin")
    with pytest.raises(NotFound):
        backend.get_for_user(document.id, user)


@pytest.mark.req("CLS-03", "DOC-03")
def test_facts_merge_and_delete_only_the_requested_key(backend, document):
    fact = FactValue(type="money", value="84.20", currency="EUR")
    backend.apply_metadata(
        document.id, MetadataPatch(facts={"amount": fact, "premium": fact}), actor="system"
    )
    backend.apply_metadata(document.id, MetadataPatch(facts={"amount": None}), actor="system")
    assert backend.get(document.id).facts == {"premium": fact}
