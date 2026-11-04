"""The conversion service receives only synthetic, self-contained document bodies."""

import os
import zipfile

import httpx
import pytest
from docuhive import config
from docuhive.ingest.convert import to_pdf
from docuhive.ingest.detect import detect
from docuhive.ingest.text import extract_text, page_count

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def conversion_service(monkeypatch):
    monkeypatch.setenv(
        "DOCUHIVE_GOTENBERG_URL",
        os.environ.get("DOCUHIVE_TEST_GOTENBERG_URL", "http://127.0.0.1:53001"),
    )
    config.reload()


@pytest.mark.parametrize("kind", ["txt", "html", "eml"])
def test_text_like_conversion(tmp_path, kind):
    path = tmp_path / f"synthetic.{kind}"
    if kind == "eml":
        content = "From: sender@example.invalid\nSubject: Synthetic receipt\n\nSynthetic 84.20 EUR"
    elif kind == "html":
        content = "<!doctype html><html><body><p>Synthetic 84.20 EUR</p></body></html>"
    else:
        content = "Synthetic 84.20 EUR"
    path.write_text(content)
    output = to_pdf(path, detect(path))
    assert page_count(output) == 1
    assert "84.20 EUR" in extract_text(output)


def test_office_conversion(tmp_path):
    path = tmp_path / "synthetic.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml"
 ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
 Target="word/document.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body><w:p><w:r><w:t>Synthetic invoice 84.20 EUR</w:t></w:r></w:p></w:body>
</w:document>""",
        )
    output = to_pdf(path, detect(path))
    assert "84.20 EUR" in extract_text(output)


def test_converter_cannot_fetch_network_urls():
    from docuhive.config.settings import get_settings

    with httpx.Client(timeout=15, trust_env=False) as client:
        response = client.post(
            f"{get_settings().gotenberg_url}/forms/chromium/convert/url",
            files={"url": (None, "http://localhost:3000/health")},  # Gotenberg needs multipart
        )
    assert response.status_code == 403
