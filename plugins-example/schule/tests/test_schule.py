"""The school plugin tags school letters and nothing else."""

from pathlib import Path

import pytest
from docuhive.sdk.testing import Archive

pytestmark = pytest.mark.integration
PLUGIN = Path(__file__).resolve().parents[1]


def test_only_school_letters_are_tagged():
    with Archive(PLUGIN) as archive:
        parent = archive.user("parent")
        letter = archive.add(parent, title="Class trip", document_type="school_letter")
        bill = archive.add(parent, title="Electricity", document_type="invoice")
        archive.emit("document.classified", document_id=letter, document_type="school_letter")
        archive.emit("document.classified", document_id=bill, document_type="invoice")
        archive.run_jobs()
        assert archive.document(letter).tags == ["school"]
        assert archive.document(bill).tags == []


def test_a_person_can_remove_the_tag_and_it_stays_removed():
    from docuhive import documents
    from docuhive.contracts import MetadataPatch

    with Archive(PLUGIN) as archive:
        parent = archive.user("parent")
        letter = archive.add(parent, document_type="school_letter")
        documents.apply_metadata(
            letter, MetadataPatch(tags_remove=["school"]), actor=f"user:{parent.id}"
        )
        archive.emit("document.classified", document_id=letter, document_type="school_letter")
        archive.run_jobs()
        assert archive.document(letter).tags == []
