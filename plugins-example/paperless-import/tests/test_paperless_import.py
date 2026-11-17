"""Import from a small stand-in for the Paperless-ngx API, served on this machine."""

import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pikepdf
import pytest
from docuhive.documents import get as get_document
from docuhive.sdk import ActionError
from docuhive.sdk.testing import Archive

pytestmark = pytest.mark.integration
PLUGIN = Path(__file__).resolve().parents[1]
TOKEN = "a-synthetic-token"


def pdf(text: str) -> bytes:
    out = io.BytesIO()
    doc = pikepdf.new()
    doc.add_blank_page()
    doc.docinfo["/Title"] = text  # different bytes per document
    doc.save(out)
    return out.getvalue()


DOCS = [
    {
        "id": 1,
        "title": "Stromrechnung März",
        "created": "2025-03-04T00:00:00+01:00",
        "correspondent": 7,
        "document_type": 3,
        "tags": [11, 12],
        "original_file_name": "strom.pdf",
    },
    {
        "id": 2,
        "title": "Mietvertrag",
        "created": "2019-08-01",
        "correspondent": None,
        "document_type": None,
        "tags": [],
        "original_file_name": "miete.pdf",
    },
    {
        "id": 3,
        "title": "Stromrechnung (Kopie)",
        "created": "2025-03-04",
        "correspondent": 7,
        "document_type": 3,
        "tags": [],
        "original_file_name": "strom-kopie.pdf",
    },
    {
        "id": 4,
        "title": "Kaputt",
        "created": "2024-01-01",
        "correspondent": None,
        "document_type": None,
        "tags": [],
        "original_file_name": "kaputt.pdf",
    },
]
FILES = {1: pdf("strom"), 2: pdf("miete"), 3: pdf("strom"), 4: None}  # 3 is the same file as 1
NAMES = {
    "/api/tags/": [{"id": 11, "name": "Energie"}, {"id": 12, "name": "Wohnung"}],
    "/api/correspondents/": [{"id": 7, "name": "Stadtwerke Musterstadt"}],
    "/api/document_types/": [{"id": 3, "name": "Rechnung"}],
}


class Paperless(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # quiet
        pass

    def reply(self, status: int, body: bytes, kind: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - the http.server interface
        if self.headers.get("Authorization") != f"Token {TOKEN}":
            return self.reply(401, b'{"detail": "Invalid token."}')
        url = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path in NAMES:
            data = {"count": len(NAMES[url.path]), "next": None, "results": NAMES[url.path]}
            return self.reply(200, json.dumps(data).encode())
        if url.path == "/api/documents/":
            size, page = int(query.get("page_size", 25)), int(query.get("page", 1))
            if size == 1:
                return self.reply(200, json.dumps({"count": len(DOCS), "results": []}).encode())
            size = 2  # two per page, so the import takes more than one step
            chunk = DOCS[(page - 1) * size : page * size]
            more = page * size < len(DOCS)
            body = {"count": len(DOCS), "next": "more" if more else None, "results": chunk}
            return self.reply(200, json.dumps(body).encode())
        if url.path.endswith("/download/"):
            content = FILES[int(url.path.split("/")[3])]
            if content is None:
                return self.reply(500, b"broken")
            return self.reply(200, content, "application/pdf")
        return self.reply(404, b"{}")


@pytest.fixture
def paperless():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Paperless)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def act(archive, name, user, /, **params):
    return archive.registry("paperless-import").actions[name][0](user, params)


def data(archive, name, user, /, **params):
    return archive.registry("paperless-import").data_sources[name](user, params)


def configure(archive, **values):
    from docuhive.plugins import state

    manifest = archive.registry("paperless-import").manifest
    assert state.save(manifest, values, actor="test") == {}


def test_import_keeps_paperless_values_skips_doubles_and_reports_problems(paperless, monkeypatch):
    monkeypatch.setenv("DOCUHIVE_SECRET_KEY", "a synthetic secret key for the test")
    from docuhive.config.settings import get_settings

    get_settings.cache_clear()
    with Archive(PLUGIN) as archive:
        admin, member = archive.user("admin", admin=True), archive.user("member")
        with pytest.raises(ActionError, match="address"):
            act(archive, "check", admin)
        configure(archive, url=paperless, token="wrong", analyse=False, type_as_tag=True)
        with pytest.raises(ActionError, match="refused the token"):
            act(archive, "check", admin)
        configure(archive, url=paperless, token=TOKEN, analyse=False, type_as_tag=True)
        with pytest.raises(ActionError, match="administrator"):
            act(archive, "start", member)
        assert "Paperless has 4 documents; 0" in act(archive, "check", admin)

        assert "Importing 4" in act(archive, "start", admin)
        with pytest.raises(ActionError, match="already running"):
            act(archive, "start", admin)
        archive.run_jobs()

        progress = {r["label"]: r["value"] for r in data(archive, "progress", admin)}
        assert progress == {
            "Import": "Finished",
            "In Paperless": 4,
            "Imported": 2,
            "Already here": 1,
            "Problems": 1,
        }
        [problem] = data(archive, "problems", admin)
        assert problem["title"] == "Kaputt" and "500" in problem["error"]

        rows = {r["title"]: r for r in data(archive, "imported_documents", admin)}
        power = get_document(rows["Stromrechnung März"]["document_id"])
        assert power.owner_id == admin.id and not power.shared
        assert power.correspondent == "Stadtwerke Musterstadt"
        assert str(power.document_date) == "2025-03-04"
        assert sorted(power.tags) == ["Energie", "Wohnung", "paperless:Rechnung"]
        # Paperless values are the person's: the AI will not overwrite them.
        assert {"title", "correspondent", "document_date", "tags"} <= set(power.manual_fields)
        assert rows["Stromrechnung (Kopie)"]["document_id"] == power.id  # the same file

        # Again: nothing new, and the failed one is tried once more.
        FILES[4] = pdf("repariert")
        act(archive, "start", admin)
        archive.run_jobs()
        progress = {r["label"]: r["value"] for r in data(archive, "progress", admin)}
        assert (progress["Imported"], progress["Problems"]) == (3, 0)

        # A stopped import does nothing more.
        act(archive, "start", admin)
        act(archive, "stop", admin)
        archive.run_jobs()
        assert data(archive, "progress", admin)[0]["value"] == "Stopped"


def test_only_the_address_in_the_settings_is_reachable(paperless, monkeypatch):
    monkeypatch.setenv("DOCUHIVE_SECRET_KEY", "a synthetic secret key for the test")
    from docuhive.config.settings import get_settings
    from docuhive.sdk import http

    get_settings.cache_clear()
    with Archive(PLUGIN) as archive:
        registry = archive.registry("paperless-import")
        configure(archive, url=paperless, token=TOKEN)
        with http.client(registry) as c, pytest.raises(http.HostNotAllowed):
            c.get("http://example.org/")
        configure(archive, url="http://10.0.0.9:8000", token=TOKEN)  # another address
        with http.client(registry) as c, pytest.raises(http.HostNotAllowed):
            c.get(f"{paperless}/api/tags/")
