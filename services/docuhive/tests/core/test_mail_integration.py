"""Sending mail as an identity, against a small SMTP server on this machine."""

import socketserver
import threading
from email import message_from_bytes, policy

import pytest
from cryptography.fernet import Fernet
from docuhive import documents, outgoing, vault
from docuhive.contracts import MetadataPatch
from docuhive.documents.holds import Held
from docuhive.mail.settings import get_mail_settings
from docuhive.profiles import ProfileIn, save
from docuhive.sdk._plugin import NotInteractive
from docuhive.sdk.testing import Archive

pytestmark = pytest.mark.integration
PLUGIN = """id: mailer
name: Mailer
version: 0.1.0
requires_sdk: ">=1,<2"
capabilities: [documents:read, mail:send]
"""
PLUGIN_PY = """
from docuhive.sdk import Registry, mail


def setup(registry: Registry) -> None:
    @registry.action("send", outgoing=True)
    def send(user, params):
        return mail.send(user, params["profile"], ["kunde@example.org"], "Rechnung 7", "Anbei.",
                         [params["doc"]])["document_id"]
"""


class Smtp(socketserver.StreamRequestHandler):
    """Just enough SMTP to receive one message: no TLS, no login."""

    received: list[tuple[list[str], bytes]] = []
    refuse = False

    def write(self, line: str) -> None:
        self.wfile.write(f"{line}\r\n".encode())

    def handle(self) -> None:
        self.write("220 test")
        rcpt: list[str] = []
        while line := self.rfile.readline().decode().strip():
            verb = line.split(" ")[0].upper()
            if verb in ("EHLO", "HELO"):
                self.write("250 test")
            elif verb == "MAIL":
                self.write("550 nope" if Smtp.refuse else "250 ok")
            elif verb == "RCPT":
                rcpt.append(line.split(":", 1)[1].strip("<> "))
                self.write("250 ok")
            elif verb == "DATA":
                self.write("354 go")
                data = b""
                while (chunk := self.rfile.readline()) != b".\r\n":
                    data += chunk
                Smtp.received.append((rcpt, data))
                self.write("250 queued")
            elif verb in ("QUIT", "RSET", "NOOP"):
                self.write("221 bye" if verb == "QUIT" else "250 ok")
                if verb == "QUIT":
                    return
            else:
                self.write("502 no")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUHIVE_MAIL_TOKEN_KEY", Fernet.generate_key().decode())
    get_mail_settings.cache_clear()
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Smtp)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    folder = tmp_path / "plugins" / "mailer"
    folder.mkdir(parents=True)
    (folder / "plugin.yaml").write_text(PLUGIN)
    (folder / "plugin.py").write_text(PLUGIN_PY)
    Smtp.received.clear()
    Smtp.refuse = False
    outgoing.limiter.sent.clear()
    try:
        with Archive(folder) as archive:
            yield archive, server.server_address[1]
    finally:
        server.shutdown()
        get_mail_settings.cache_clear()


def test_send_store_and_lock(setup):
    archive, port = setup
    alice = archive.user("alice")
    identity = save(
        alice,
        ProfileIn(
            kind="business",
            name="Muster Design",
            smtp={"host": "127.0.0.1", "port": port, "from_address": "post@example.org"},
        ),
    )
    invoice = archive.add(alice, title="Rechnung 7", original=("r7.pdf", b"%PDF-1.4 x"))
    (vault.root() / "2026" / invoice / "archive.pdf").write_bytes(b"%PDF-1.4 archive")

    with pytest.raises(NotInteractive):  # never from a job or event handler
        archive.registry("mailer").actions["send"][0](
            alice, {"profile": identity.id, "doc": invoice}
        )

    sent = outgoing.send(
        alice, identity.id, ["kunde@example.org"], "Rechnung 7", "Anbei.", [invoice]
    )
    ((rcpt, data),) = Smtp.received
    assert rcpt == ["kunde@example.org", "post@example.org"]  # a copy to the sender
    message = message_from_bytes(data, policy=policy.default)
    assert "post@example.org" not in message["To"] and message["Bcc"] is None
    assert [p.get_filename() for p in message.iter_attachments()] == ["Rechnung 7.pdf"]

    stored = documents.get(sent.document_id)
    assert stored.source.derived_from == [invoice] and stored.shared is False
    for doc_id in (invoice, sent.document_id):  # what was sent cannot change any more
        with pytest.raises(Held, match="Sent by mail to kunde@example.org"):
            documents.apply_metadata(
                doc_id, MetadataPatch(title="changed"), actor=f"user:{alice.id}"
            )

    Smtp.refuse = True
    with pytest.raises(outgoing.Refused, match="refused"):
        outgoing.send(alice, identity.id, ["kunde@example.org"], "Again", "x")
    with pytest.raises(outgoing.Refused, match="between 1 and 20"):
        outgoing.send(alice, identity.id, [f"a{n}@example.org" for n in range(21)], "Many", "x")
    with pytest.raises(outgoing.Refused, match="Not a mail address"):
        outgoing.send(alice, identity.id, ["not an address"], "Bad", "x")


def test_no_password_over_a_plain_connection(setup):
    archive, port = setup
    alice = archive.user("alice")
    identity = save(
        alice,
        ProfileIn(
            kind="business",
            name="Muster Design",
            smtp={
                "host": "127.0.0.1",
                "port": port,
                "username": "post",
                "from_address": "post@example.org",
                "password": "s3cret",
            },
        ),
    )
    with pytest.raises(outgoing.Refused, match="no encryption"):
        outgoing.send(alice, identity.id, ["kunde@example.org"], "Hi", "x")
    assert Smtp.received == []
