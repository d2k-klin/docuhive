"""Synthetic parsing, conversion and OCR policy checks; no private corpus or external tools."""

import importlib.util
import time
import zipfile
from pathlib import Path

import httpx
import pikepdf
import pytest
from docuhive.ingest.convert import to_pdf
from docuhive.ingest.detect import Detected, detect
from docuhive.ingest.errors import Quarantine
from docuhive.ingest.html import render_email, sanitize
from docuhive.ingest.ocr import ocr
from docuhive.ingest.safety import isolated
from docuhive.ingest.text import extract_text, page_count
from docuhive.ingest.thumbs import thumbnail
from ocrmypdf.exceptions import EncryptedPdfError, ExitCode, PriorOcrFoundError
from PIL import Image


def make_pdf(path: Path, *, encrypted: bool = False, pages: int = 1) -> Path:
    with pikepdf.new() as pdf:
        for _ in range(pages):
            page = pdf.add_blank_page(page_size=(612, 792))
            font = pdf.make_indirect(
                pikepdf.Dictionary(
                    Type=pikepdf.Name.Font,
                    Subtype=pikepdf.Name.Type1,
                    BaseFont=pikepdf.Name.Helvetica,
                )
            )
            page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
            page.Contents = pdf.make_stream(
                b"BT /F1 14 Tf 72 700 Td (Synthetic invoice 84.20 EUR) Tj ET"
            )
        kwargs = (
            {"encryption": pikepdf.Encryption(owner="synthetic-owner", user="synthetic")}
            if encrypted
            else {}
        )
        pdf.save(path, **kwargs)
    return path


def test_detection_ignores_extensions_and_catches_text_formats(tmp_path):
    pdf = make_pdf(tmp_path / "wrong.jpg")
    assert detect(pdf) == Detected("application/pdf", "pdf", "pdf")
    path = tmp_path / "no-extension"
    path.write_bytes(b"From: sender@example.invalid\nSubject: synthetic\n\nHello")
    assert detect(path).kind == "email"
    path.write_text("<!doctype html><html><p>Receipt</p></html>")
    assert detect(path).kind == "html"
    path.write_text("Synthetic UTF-8 text: ü")
    assert detect(path).kind == "text"
    path.write_bytes(b"hello\x00world")
    with pytest.raises(Quarantine):
        detect(path)
    path.write_bytes(b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1")
    assert detect(path).kind == "image"


def test_office_detection_and_decompression_guard(tmp_path):
    path = tmp_path / "wrong.pdf"
    with zipfile.ZipFile(path, "w") as office:
        office.writestr("[Content_Types].xml", "<Types/>")
        office.writestr("word/document.xml", "<document/>")
    assert detect(path).ext == "docx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bomb", b"0" * 10_000_000)
    with pytest.raises(Quarantine, match="expansion"):
        detect(path)


def test_pdf_conversion_text_and_thumbnail(tmp_path):
    source = make_pdf(tmp_path / "synthetic.pdf")
    output = to_pdf(source, detect(source))
    assert page_count(output) == 1
    assert extract_text(output) == "Synthetic invoice 84.20 EUR"
    preview = tmp_path / "thumb.webp"
    thumbnail(output, preview)
    with Image.open(preview) as image:
        assert image.width == 480
    assert source.exists()


def test_encrypted_and_too_many_pages_are_quarantined(tmp_path):
    source = make_pdf(tmp_path / "encrypted.pdf", encrypted=True)
    with pytest.raises(Quarantine, match="encrypted"):
        to_pdf(source, detect(source))
    source = make_pdf(tmp_path / "huge.pdf", pages=501)
    with pytest.raises(Quarantine, match="too_many_pages"):
        to_pdf(source, detect(source))


def test_images_exif_and_multipage_tiff(tmp_path):
    source = tmp_path / "multi.tiff"
    Image.new("RGB", (100, 200), "white").save(
        source, save_all=True, append_images=[Image.new("RGB", (200, 100), "white")], dpi=(300, 300)
    )
    assert page_count(to_pdf(source, detect(source))) == 2
    assert not list(tmp_path.glob("*.frame-*.jpg"))


def test_html_and_email_remove_active_and_remote_content(tmp_path):
    cleaned = sanitize(
        '<script>bad()</script><iframe src="http://host"></iframe><p onclick="bad()">Safe</p>'
        '<img src="http://beacon"><a href="file:///etc/passwd">Link</a>'
    )
    assert cleaned == "<p>Safe</p>Link"
    source = tmp_path / "synthetic.eml"
    source.write_text(
        "From: sender@example.invalid\nTo: archive@example.invalid\nSubject: <script>\n"
        "MIME-Version: 1.0\nContent-Type: text/html; charset=utf-8\n\n"
        '<p>Receipt</p><img src="http://beacon"><script>bad()</script>'
    )
    rendered = render_email(source)
    assert "Receipt" in rendered and "&lt;script&gt;" in rendered
    assert "http://beacon" not in rendered and "bad()" not in rendered


@pytest.mark.parametrize(
    "first,expected_pdfa",
    [
        (ExitCode.pdfa_conversion_failed, False),
        (PriorOcrFoundError(), True),
        (RuntimeError("deskew failed"), True),
    ],
)
def test_ocr_fallback_policy(monkeypatch, tmp_path, first, expected_pdfa):
    calls = []

    def fake_ocr(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            if isinstance(first, Exception):
                raise first
            return first
        return ExitCode.ok

    monkeypatch.setattr("docuhive.ingest.ocr.ocrmypdf.ocr", fake_ocr)
    assert ocr(tmp_path / "in.pdf", tmp_path / "out.pdf", "deu+eng") is expected_pdfa
    assert calls[0]["skip_text"] is True
    assert calls[0]["language"] == ["deu", "eng"]
    if isinstance(first, RuntimeError):
        assert calls[1]["deskew"] is False


def test_ocr_encryption_is_explicit(monkeypatch, tmp_path):
    def encrypted(*args, **kwargs):
        raise EncryptedPdfError()

    monkeypatch.setattr("docuhive.ingest.ocr.ocrmypdf.ocr", encrypted)
    with pytest.raises(Quarantine, match="encrypted"):
        ocr(tmp_path / "in", tmp_path / "out", "eng")


def slow_step():
    time.sleep(30)


def test_isolation_timeout_and_success():
    assert isolated(sum, [1, 2, 3], timeout_s=10) == 6
    started = time.monotonic()
    with pytest.raises(Quarantine, match="step_timeout"):
        isolated(slow_step, timeout_s=0.2)
    assert time.monotonic() - started < 5


def test_cer_normalization_and_errors():
    path = Path(__file__).resolve().parents[4] / "evals/ocr/cer.py"
    spec = importlib.util.spec_from_file_location("ocr_cer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.character_error_rate("MÜLLER\n Hello", "müller hello") == 0
    assert module.character_error_rate("abc", "axc") == pytest.approx(1 / 3)
    assert module.character_error_rate("abc", "") == 1
    with pytest.raises(ValueError):
        module.character_error_rate("", "unexpected")


@pytest.mark.parametrize(
    "kind,endpoint",
    [
        ("text", "chromium/convert/html"),
        ("html", "chromium/convert/html"),
        ("email", "chromium/convert/html"),
        ("office", "libreoffice/convert"),
    ],
)
def test_conversion_routes_send_self_contained_content(monkeypatch, tmp_path, kind, endpoint):
    from docuhive.ingest import convert

    pdf = make_pdf(tmp_path / "response.pdf").read_bytes()
    source = tmp_path / "synthetic"
    body = "Synthetic receipt"
    if kind == "html":
        body = '<html><p>Safe</p><img src="http://beacon"><script>bad()</script></html>'
    elif kind == "email":
        body = "From: sender@example.invalid\nSubject: Synthetic\n\nSafe"
    source.write_text(body)
    requests = []

    class Converter:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            requests.append((url, kwargs))
            return httpx.Response(200, content=pdf, request=httpx.Request("POST", url))

    monkeypatch.setattr(convert.httpx, "Client", lambda **kwargs: Converter())
    output = to_pdf(source, Detected("synthetic", "docx" if kind == "office" else "txt", kind))
    assert extract_text(output) == "Synthetic invoice 84.20 EUR"
    url, request = requests[0]
    assert url.endswith(endpoint)
    if kind != "office":
        filename, data = request["files"]["files"]
        assert filename == "index.html"
        assert b"http://beacon" not in data and b"bad()" not in data
    assert source.exists()


@pytest.mark.parametrize(
    "error,reason",
    [
        (httpx.ConnectError("offline"), "converter_unavailable"),
        (httpx.ReadTimeout("slow"), "converter_timeout"),
        (
            httpx.HTTPStatusError(
                "invalid input",
                request=httpx.Request("POST", "http://local"),
                response=httpx.Response(400),
            ),
            "conversion_http_400",
        ),
    ],
)
def test_converter_failures_preserve_specific_reasons_and_input(
    monkeypatch, tmp_path, error, reason
):
    from docuhive.ingest import convert

    source = tmp_path / "synthetic.txt"
    source.write_text("Synthetic")

    class BrokenConverter:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            raise error

    monkeypatch.setattr(convert.httpx, "Client", lambda **kwargs: BrokenConverter())
    with pytest.raises(Quarantine, match=reason):
        to_pdf(source, detect(source))
    assert source.read_text() == "Synthetic"


@pytest.mark.parametrize(
    "mime,extension",
    [
        ("application/vnd.oasis.opendocument.text", "odt"),
        ("application/vnd.oasis.opendocument.spreadsheet", "ods"),
    ],
)
def test_open_document_detection(tmp_path, mime, extension):
    path = tmp_path / "unknown"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", mime)
    assert detect(path).ext == extension


@pytest.mark.parametrize("data", [b"", b"PK\x03\x04broken", b"\xff\xfe", b"GIF89a\x00"])
def test_rejected_inputs_have_explicit_quarantine(tmp_path, data):
    path = tmp_path / "unknown"
    path.write_bytes(data)
    with pytest.raises(Quarantine):
        detect(path)
