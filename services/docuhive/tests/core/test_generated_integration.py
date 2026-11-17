"""Documents a plugin generates: stored like an upload, never classified, private by default,
linked to what they were made from, and the same bytes never twice."""

import functools

import pytest
from docuhive import documents
from docuhive.agents import pipeline  # noqa: F401 - registers the AI track's handlers
from docuhive.api.app import create_app
from docuhive.db import session
from docuhive.db.models import Job
from docuhive.sdk.testing import Archive
from fastapi.testclient import TestClient
from fpdf import FPDF
from sqlalchemy import select

pytestmark = pytest.mark.integration
CSRF = {"X-DocuHive-CSRF": "1"}
PLUGIN = """id: writer
name: Writer
version: 0.1.0
requires_sdk: ">=1,<2"
capabilities: [documents:read, documents:write-metadata, documents:create]
"""
PLUGIN_PY = """
from docuhive.sdk import Registry, documents


def setup(registry: Registry) -> None:
    @registry.action("write")
    def write(user, params):
        return documents.create(
            user, params["pdf"], filename="Letter 1/../x.pdf", title="Letter to the landlord",
            document_type="letter", tags=["sent"], derived_from=params.get("from", []),
        )
"""


@functools.cache  # the same bytes every time: FPDF stamps the time in seconds
def pdf(text: str) -> bytes:
    page = FPDF()
    page.add_page()
    page.set_font("helvetica", size=12)
    page.cell(text=text)
    return bytes(page.output())


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUHIVE_OCR_LANGUAGES", "eng")  # the host may lack German OCR data
    folder = tmp_path / "plugins" / "writer"
    folder.mkdir(parents=True)
    (folder / "plugin.yaml").write_text(PLUGIN)
    (folder / "plugin.py").write_text(PLUGIN_PY)
    with Archive(folder) as made:
        yield made


def test_a_generated_letter(archive):
    alice, bob = archive.user("alice"), archive.user("bob")
    contract = archive.add(alice, title="Rental contract", shared=True)
    write = archive.registry("writer").actions["write"][0]
    letter = write(alice, {"pdf": pdf("Dear landlord"), "from": [contract]})
    assert write(alice, {"pdf": pdf("Dear landlord"), "from": [contract]}) == letter
    archive.run_jobs(queues=("default", "ocr", "ai"))

    view = archive.document(letter)
    assert view.status == "stored" and view.shared is False
    assert (view.title, view.document_type, view.tags) == (
        "Letter to the landlord",
        "letter",
        ["sent"],
    )
    assert view.source.kind == "plugin" and view.source.generator == "writer"
    assert view.source.derived_from == [contract]
    assert view.source.original_filename == "x.pdf"  # no folders from a plugin's file name
    with session() as s:
        kinds = set(s.scalars(select(Job.kind).where(Job.payload["document_id"].astext == letter)))
    assert "ai.classify" not in kinds and "index.embed" in kinds

    client = TestClient(create_app(), base_url="https://testserver")
    client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "a synthetic test password"},
        headers=CSRF,
    )
    detail = client.get(f"/api/documents/{contract}").json()
    assert detail["used_in"] == [letter]
    assert detail["related_titles"] == {letter: "Letter to the landlord"}
    with pytest.raises(documents.NotFound):  # not from a document bob cannot see
        write(bob, {"pdf": pdf("Other"), "from": [letter]})
