"""Rendering through the real converter: a letter fits the envelope window, a template cannot
reach the network or escape its sandbox, and an e-invoice can be embedded."""

import io
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pikepdf
import pypdfium2
import pytest
from docuhive.sdk.testing import Archive
from jinja2.exceptions import SecurityError, UndefinedError

pytestmark = pytest.mark.integration
MM = 72 / 25.4
PLUGIN = """id: letters
name: Letters
version: 0.1.0
requires_sdk: ">=1,<2"
capabilities: [documents:read]
"""
PLUGIN_PY = """
from docuhive.sdk import Registry, render


def setup(registry: Registry) -> None:
    @registry.action("pdf")
    def pdf(user, params):
        return render.pdf(params["template"], params["context"])

    @registry.action("text")
    def text(user, params):
        return render.text(params["template"], params["context"])

    @registry.action("attach")
    def attach(user, params):
        return render.attach(params["pdf"], "factur-x.xml", b"<Invoice/>")
"""
LETTER = """{% extends "_letter.html" %}
{% block body %}<p>Sehr geehrte Damen und Herren,</p><p>{{ text }}</p>{% endblock %}
"""
PROBE = """<!doctype html><html><head></head><body>
<img src="http://127.0.0.1:{port}/pixel.png"><p>Probe</p></body></html>"""


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "DOCUHIVE_GOTENBERG_URL",
        os.environ.get("DOCUHIVE_TEST_GOTENBERG_URL", "http://127.0.0.1:53001"),
    )
    folder = tmp_path / "plugins" / "letters"
    (folder / "templates").mkdir(parents=True)
    (folder / "plugin.yaml").write_text(PLUGIN)
    (folder / "plugin.py").write_text(PLUGIN_PY)
    (folder / "templates" / "letter.html").write_text(LETTER)
    (folder / "templates" / "greeting.txt").write_text("Hello {{ name }}")
    (folder / "templates" / "escape.txt").write_text(
        "{{ ''.__class__.__mro__[1].__subclasses__() }}"
    )
    with Archive(folder) as made:
        yield made, folder


def act(archive, name, **params):
    return archive.registry("letters").actions[name][0](archive.user("alice"), params)


def test_a_letter_fits_the_window_envelope(archive):
    archive, _ = archive
    data = act(
        archive,
        "pdf",
        template="letter.html",
        context={
            "sender_line": "Muster GmbH · Beispielweg 1 · 12345 Musterstadt",
            "recipient": ["Finanzamt Musterstadt", "Postfach 10 20 30", "12345 Musterstadt"],
            "place": "Musterstadt",
            "date": "16.11.2026",
            "subject": "Antrag auf Fristverlängerung",
            "text": "hiermit beantrage ich …",
        },
    )
    page = pypdfium2.PdfDocument(data)[0]
    width, height = page.get_size()
    assert round(width / MM) == 210 and round(height / MM) == 297
    textpage = page.get_textpage()
    first = textpage.search("Finanzamt").get_next()
    assert first is not None
    left, bottom, right, top = textpage.get_charbox(first[0])
    # The DIN 5008 form B address field: 25 mm from the left, 50.7–78 mm from the top.
    assert 24 <= left / MM <= 27
    assert 50 <= (height - top) / MM <= 78


def test_the_sandbox_and_missing_values(archive):
    archive, _ = archive
    assert act(archive, "text", template="greeting.txt", context={"name": "Alice"}) == "Hello Alice"
    with pytest.raises(UndefinedError):
        act(archive, "text", template="greeting.txt", context={})
    with pytest.raises(SecurityError):
        act(archive, "text", template="escape.txt", context={})


def test_a_template_cannot_reach_the_network(archive):
    archive, folder = archive
    hits: list[str] = []

    class Spy(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            hits.append(self.path)
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("0.0.0.0", 0), Spy)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        (folder / "templates" / "probe.html").write_text(
            PROBE.replace("{port}", str(server.server_port))
        )
        data = act(archive, "pdf", template="probe.html", context={})
        assert data.startswith(b"%PDF")
    finally:
        server.shutdown()
    assert hits == []


def test_an_embedded_invoice(archive):
    archive, _ = archive
    data = act(
        archive,
        "pdf",
        template="letter.html",
        context={
            "sender_line": "",
            "recipient": [],
            "place": "",
            "date": "",
            "subject": "",
            "text": "",
        },
    )
    with_xml = act(archive, "attach", pdf=data)
    with pikepdf.open(io.BytesIO(with_xml)) as document:
        assert document.attachments["factur-x.xml"].get_file().read_bytes() == b"<Invoice/>"
        assert str(document.Root.AF[0].AFRelationship) == "/Alternative"
