import json
from datetime import UTC, date, datetime
from email.message import EmailMessage
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet
from docuhive.mail import accounts, oauth
from docuhive.mail.base import AttachmentMeta, MailMessage, MsgRef, NeedsReauth
from docuhive.mail.gmail import Gmail
from docuhive.mail.graph import Graph
from docuhive.mail.imap import Imap
from docuhive.mail.models import Backfill, MailAccount
from docuhive.mail.prefilter import Rules, prefilter, rules_for

FIX = Path(__file__).parent / "fixtures"
SINCE, UNTIL = datetime(2025, 11, 1, tzinfo=UTC), datetime(2025, 11, 30, tzinfo=UTC)


def load(path: str) -> dict:
    return json.loads((FIX / path).read_text())


@pytest.fixture
def mailkey(monkeypatch):
    from docuhive.mail.settings import get_mail_settings

    monkeypatch.setenv("DOCUHIVE_MAIL_TOKEN_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("DOCUHIVE_MAIL_GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("DOCUHIVE_MAIL_GOOGLE_CLIENT_SECRET", "secret")
    get_mail_settings.cache_clear()
    yield
    get_mail_settings.cache_clear()


# ---- connectors with recorded-style fixtures ------------------------------------------------


def gmail_transport(request: httpx.Request) -> httpx.Response:
    path = request.url.path.removeprefix("/gmail/v1/users/me/")
    if path == "messages":
        page = "list_page2" if request.url.params.get("pageToken") == "p2" else "list_page1"
        return httpx.Response(200, json=load(f"gmail/{page}.json"))
    if path == "messages/m1":
        return httpx.Response(200, json=load("gmail/message_m1.json"))
    if path == "messages/m1/attachments/att-pdf":
        return httpx.Response(200, json=load("gmail/attachment_pdf.json"))
    if path == "messages/m9":
        return httpx.Response(429, headers={"Retry-After": "7"})
    return httpx.Response(404)


def test_gmail_paging_nested_multipart_inline(tmp_path):
    g = Gmail(lambda: "tok", httpx.Client(transport=httpx.MockTransport(gmail_transport)))
    refs, nxt = g.list_range(SINCE, UNTIL, None)
    assert [r.provider_msg_id for r in refs] == ["m1", "m2"] and nxt == "p2"
    assert [r.provider_msg_id for r in g.list_range(SINCE, UNTIL, nxt)[0]] == ["m3"]
    m = g.get_message(refs[0])
    assert m.subject == "Ihre Stromrechnung November" and "Rechnung" in m.text_snippet
    assert [(a.filename, a.inline) for a in m.attachments] == [
        ("logo.png", True),
        ("Rechnung-2025-11.pdf", False),
    ]
    assert m.labels == ["INBOX", "CATEGORY_UPDATES"] and m.ref.received_at.year == 2025
    g.download_attachment(m.ref, m.attachments[1], tmp_path / "a.pdf")
    assert (tmp_path / "a.pdf").read_bytes() == b"%PDF-1.7 fake"


def test_gmail_rate_limit():
    from docuhive.mail.base import RateLimited

    g = Gmail(lambda: "tok", httpx.Client(transport=httpx.MockTransport(gmail_transport)))
    with pytest.raises(RateLimited) as e:
        g.get_message(MsgRef("m9", SINCE))
    assert e.value.retry_after_s == 7


def graph_transport(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    path = request.url.path.removeprefix("/v1.0/me/")
    if path == "mailFolders/deleteditems":
        return httpx.Response(200, json={"id": "deleted-id"})
    if path == "mailFolders/junkemail":
        return httpx.Response(200, json={"id": "junk-id"})
    if path == "messages" and "skiptoken" in url:
        return httpx.Response(200, json=load("graph/list_page2.json"))
    if path == "messages":
        assert "receivedDateTime ge 2025-11-01T00:00:00Z" in request.url.params["$filter"]
        return httpx.Response(200, json=load("graph/list_page1.json"))
    if path == "messages/g1":
        return httpx.Response(200, json=load("graph/message_g1.json"))
    if path == "messages/g1/attachments":
        return httpx.Response(200, json=load("graph/attachments_g1.json"))
    if path == "messages/g1/attachments/ga1/$value":
        return httpx.Response(200, content=b"%PDF" + b"x" * 2_000_000)
    return httpx.Response(404)


def test_graph_paging_skips_deleted_item_attachment_and_large_value(tmp_path):
    g = Graph(lambda: "tok", httpx.Client(transport=httpx.MockTransport(graph_transport)))
    refs, nxt = g.list_range(SINCE, UNTIL, None)
    assert [r.provider_msg_id for r in refs] == ["g1"] and nxt.endswith("skiptoken=abc")
    assert [r.provider_msg_id for r in g.list_range(SINCE, UNTIL, nxt)[0]] == ["g3"]
    m = g.get_message(refs[0])
    assert m.email_from == "service@versicherung.example" and m.has_html_body
    assert [a.kind for a in m.attachments] == ["fileAttachment", "itemAttachment"]
    g.download_attachment(m.ref, m.attachments[0], tmp_path / "p.pdf")
    assert (tmp_path / "p.pdf").stat().st_size > 2_000_000
    # itemAttachment is never a candidate
    r = Rules(attachment_mime_allow=["application/pdf"], min_attachment_kb=1)
    assert [a.filename for a in prefilter(m, r).candidate_attachments] == ["Police-2026.pdf"]


def make_eml(subject="Rechnung", sender="shop@example.org", pdf=True) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, "me@example.org", subject
    msg["Message-ID"] = f"<{subject}@example.org>"
    msg["Date"] = "Sun, 02 Nov 2025 10:00:00 +0100"
    msg.set_content("Ihre Rechnung im Anhang.")
    if pdf:
        msg.add_attachment(
            b"%PDF-1.4 " + subject.encode() * 20000,
            maintype="application",
            subtype="pdf",
            filename=f"{subject}.pdf",
        )
    return msg.as_bytes()


class FakeIMAP:
    """Serves .eml bytes like imaplib.IMAP4_SSL; records every command."""

    def __init__(self, host, port, messages=None):
        self.messages = messages or {b"1": make_eml("A"), b"2": make_eml("B"), b"3": make_eml("C")}
        self.log = []

    def login(self, user, pw):
        self.log.append(("login", user))

    def select(self, folder, readonly=False):
        self.log.append(("select", folder, readonly))
        return "OK", [b"3"]

    def response(self, code):
        return code, [b"42"]

    def uid(self, cmd, *args):
        self.log.append((cmd, *args))
        if cmd == "SEARCH":
            return "OK", [b" ".join(self.messages)]
        uid = args[0].encode() if isinstance(args[0], str) else args[0]
        return "OK", [(b"1 (BODY[] {n})", self.messages[uid]), b")"]


def test_imap_peek_paging_and_parse(tmp_path):
    server = FakeIMAP("h", 993)
    imap = Imap("h", 993, "u", "p", factory=lambda h, p: server)
    refs, nxt = imap.list_range(SINCE, UNTIL, None, page_size=2)
    assert [r.provider_msg_id for r in refs] == ["INBOX:42:1", "INBOX:42:2"] and nxt == "0:2"
    assert imap.list_range(SINCE, UNTIL, nxt, page_size=2)[1] is None
    m = imap.get_message(refs[0])
    assert m.subject == "A" and m.attachments[0].filename == "A.pdf"
    assert all(c[2] == "(BODY.PEEK[])" for c in server.log if c[0] == "FETCH")  # never marks read
    assert all(c[2] is True for c in server.log if c[0] == "select")
    imap.download_attachment(refs[0], m.attachments[0], tmp_path / "a.pdf")
    assert (tmp_path / "a.pdf").read_bytes().startswith(b"%PDF-1.4")


def test_expired_token_sets_needs_reauth(core, mailkey):
    with core.session() as s:
        acc = MailAccount(
            owner_id=1,
            provider="gmail",
            address="me@gmail.example",
            enc_credentials=accounts.encrypt({"refresh_token": "old"}),
            sync_cursor={},
        )
        s.add(acc)
        s.flush()
        aid = acc.id
    oauth._CACHE.clear()
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(400, json={"error": "invalid_grant"})
        )
    )
    with pytest.raises(NeedsReauth):
        oauth.access_token(aid, client)
    assert core.rows("mail_accounts")[0]["status"] == "needs_reauth"
    assert core.rows("notification_log")[0]["kind"] == "mail_reauth"


def test_oauth_state_is_bound_to_user(core, mailkey):
    url = oauth.start_url("google", user_id=1)
    assert "code_challenge_method=S256" in url and "gmail.readonly" in url
    state = httpx.URL(url).params["state"]
    with pytest.raises(PermissionError):
        oauth.callback("google", "code", state, user_id=2)


# ---- prefilter --------------------------------------------------------------------------------


def msg(**kw) -> MailMessage:
    base = {
        "ref": MsgRef("x", SINCE),
        "email_from": "Shop <billing@shop.example>",
        "attachments": [
            AttachmentMeta(
                provider_att_id="a", filename="r.pdf", mime="application/pdf", size=50_000
            )
        ],
    }
    return MailMessage(**(base | kw))


RULES = Rules(
    attachment_mime_allow=["application/pdf", "image/png"],
    min_attachment_kb=15,
    skip_labels=["CATEGORY_PROMOTIONS", "SPAM"],
    deny_senders=["*@*.newsletter.*"],
    allow_senders=["*@bank.example"],
    body_archive_senders=["*@amazon.example"],
)


@pytest.mark.parametrize(
    ("message", "decision", "reason"),
    [
        (msg(email_from="x@info.newsletter.shop"), "skip", "prefilter:deny_sender"),
        (msg(email_from="konto@bank.example"), "import", "prefilter:allow_sender"),
        (msg(labels=["CATEGORY_PROMOTIONS"]), "skip", "prefilter:promotions"),
        (
            msg(attachments=[], headers={"List-Unsubscribe": "<mailto:x>"}),
            "skip",
            "prefilter:newsletter",
        ),
        (
            msg(
                attachments=[
                    AttachmentMeta(
                        provider_att_id="l", filename="logo.png", mime="image/png", size=4000
                    )
                ]
            ),
            "skip",
            "prefilter:no_attachment",
        ),
        (
            msg(
                attachments=[
                    AttachmentMeta(
                        provider_att_id="l",
                        filename="sig.png",
                        mime="image/png",
                        size=40000,
                        inline=True,
                    )
                ]
            ),
            "skip",
            "prefilter:no_attachment",
        ),
        (msg(attachments=[], email_from="auto@amazon.example"), "triage", "prefilter:candidate"),
        (msg(), "triage", "prefilter:candidate"),
    ],
)
def test_prefilter_rules(message, decision, reason):
    res = prefilter(message, RULES)
    assert (res.decision, res.reason) == (decision, reason)


def test_per_account_override(core, monkeypatch):
    from docuhive import config

    monkeypatch.setattr(
        config,
        "load_yaml",
        lambda name: {
            "defaults": {"min_attachment_kb": 15},
            "accounts": {"me@x.org": {"min_attachment_kb": 1}},
        },
    )
    assert rules_for("ME@x.org").min_attachment_kb == 1
    assert rules_for("other@x.org").min_attachment_kb == 15


# ---- jobs: triage, ledger, backfill -----------------------------------------------------------


class FakeConnector:
    def __init__(self, messages: dict[str, bytes]):
        self.messages = messages
        self.marked: list[str] = []
        self.listed = 0

    def list_range(self, since, until, page_token, page_size=2):
        ids = sorted(self.messages)
        start = int(page_token or 0)
        self.listed += 1
        nxt = str(start + page_size) if start + page_size < len(ids) else None
        return [MsgRef(i, since) for i in ids[start : start + page_size]], nxt

    def get_message(self, ref):
        from docuhive.mail.imap import parse

        return parse(self.messages[ref.provider_msg_id], ref, ["INBOX"])[0]

    def download_attachment(self, ref, att, dest):
        from docuhive.mail.imap import parse

        parts = parse(self.messages[ref.provider_msg_id], ref)[1]
        dest.write_bytes(parts[int(att.provider_att_id)].get_payload(decode=True))

    def download_raw(self, ref, dest):
        dest.write_bytes(self.messages[ref.provider_msg_id])

    def mark_imported(self, ref):
        self.marked.append(ref.provider_msg_id)


@pytest.fixture
def mailbox(core, mailkey, monkeypatch, fake):
    conn = FakeConnector({"1": make_eml("A"), "2": make_eml("B"), "3": make_eml("C")})
    monkeypatch.setattr(accounts, "connector_for", lambda acc: conn)
    with core.session() as s:
        acc = MailAccount(
            owner_id=1,
            provider="imap",
            address="me@example.org",
            enc_credentials=b"x",
            sync_cursor={},
            created_at=datetime(2025, 11, 1, tzinfo=UTC),
        )
        s.add(acc)
        s.flush()
        conn.account_id = acc.id
    fake(
        outputs={
            "*": {
                "archive": True,
                "attachments": ["A.pdf", "B.pdf", "C.pdf"],
                "doc_hint": "invoice",
                "reason": "invoice",
                "confidence": 0.9,
            }
        }
    )
    return conn


def test_sync_twice_creates_no_new_process_jobs(core, mailbox):
    core.jobs.enqueue("mail.sync", {"account_id": mailbox.account_id})
    core.jobs.run({"mail.sync"})
    assert len(core.jobs.pending("mail.process")) == 3
    core.jobs.enqueue("mail.sync", {"account_id": mailbox.account_id})
    core.jobs.run({"mail.sync"})
    assert len(core.jobs.pending("mail.process")) == 3


def test_process_imports_with_provenance_and_hint(core, mailbox):
    core.jobs.enqueue("mail.sync", {"account_id": mailbox.account_id})
    core.jobs.run({"mail.sync", "mail.process"})
    assert [r["status"] for r in core.rows("mail_messages")] == ["imported"] * 3
    doc_id, req, names = core.ingest.submitted[0]
    assert req.source.kind == "email" and req.source.subject == "A"
    assert req.hints == {"doc_hint": "invoice"} and names[0].endswith("A.pdf")
    assert mailbox.marked == ["1", "2", "3"]


def test_triage_reject_and_import_anyway(core, mailbox, fake):
    fake(outputs={"*": {"archive": True, "attachments": [], "reason": "maybe", "confidence": 0.3}})
    core.jobs.enqueue("mail.sync", {"account_id": mailbox.account_id})
    core.jobs.run({"mail.sync", "mail.process"})
    rows = core.rows("mail_messages")
    assert {r["status"] for r in rows} == {"triage_rejected"} and rows[0]["reason"] == "maybe"
    core.jobs.enqueue("mail.process", {"message_id": rows[0]["id"], "force": True})
    core.jobs.run({"mail.process"})
    assert core.rows("mail_messages", id=rows[0]["id"])[0]["status"] == "imported"


def test_partial_attachment_selection(core, mailbox, fake):
    two = EmailMessage()
    two["From"], two["Subject"], two["Message-ID"] = "a@b.example", "Two", "<two@x>"
    two.set_content("two files")
    for name in ("invoice.pdf", "agb.pdf"):
        two.add_attachment(
            b"%PDF " + name.encode() * 5000, maintype="application", subtype="pdf", filename=name
        )
    mailbox.messages = {"9": two.as_bytes()}
    fake(
        outputs={
            "*": {
                "archive": True,
                "attachments": ["invoice.pdf"],
                "reason": "invoice",
                "confidence": 0.9,
            }
        }
    )
    core.jobs.enqueue("mail.sync", {"account_id": mailbox.account_id})
    core.jobs.run({"mail.sync", "mail.process"})
    assert [r["filename"] for r in core.rows("mail_attachments")] == ["invoice.pdf"]


def test_same_attachment_in_two_messages_imported_once(core, mailbox):
    same = make_eml("A")
    mailbox.messages = {"1": same, "2": same.replace(b"<A@example.org>", b"<A2@example.org>")}
    core.jobs.enqueue("mail.sync", {"account_id": mailbox.account_id})
    core.jobs.run({"mail.sync", "mail.process"})
    assert len(core.ingest.submitted) == 1
    assert sorted(r["status"] for r in core.rows("mail_attachments")) == ["duplicate", "submitted"]


def test_backfill_resumes_after_crash_and_pause_cancel(core, mailbox, monkeypatch):
    with core.session() as s:
        bf = Backfill(
            account_id=mailbox.account_id,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 12, 31),
            status="running",
        )
        s.add(bf)
        s.flush()
        bid = bf.id
    core.jobs.enqueue("mail.backfill.page", {"backfill_id": bid})
    core.jobs.run({"mail.backfill.page"}, max_jobs=1)  # page 1, then the worker "crashes"
    assert core.rows("backfills")[0]["page_token"] == "2"
    with core.session() as s:
        s.get(Backfill, bid).status = "paused"
    core.jobs.run({"mail.backfill.page"})  # paused: the queued page is a no-op
    assert core.rows("backfills")[0]["scanned"] == 2
    with core.session() as s:
        s.get(Backfill, bid).status = "running"
    core.jobs.enqueue("mail.backfill.page", {"backfill_id": bid})
    core.jobs.run({"mail.backfill.page", "mail.process"})
    b = core.rows("backfills")[0]
    assert (b["status"], b["scanned"], b["imported"]) == ("done", 3, 3)
    assert len(core.ingest.submitted) == 3
    # the same backfill again: nothing new
    with core.session() as s:
        again = Backfill(
            account_id=mailbox.account_id,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 12, 31),
            status="running",
        )
        s.add(again)
        s.flush()
        bid2 = again.id
    core.jobs.enqueue("mail.backfill.page", {"backfill_id": bid2})
    core.jobs.run({"mail.backfill.page", "mail.process"})
    b2 = core.rows("backfills", id=bid2)[0]
    assert (b2["status"], b2["imported"], b2["candidates"]) == ("done", 0, 0)


def test_stored_event_updates_attachment_status(core, mailbox):
    core.jobs.enqueue("mail.sync", {"account_id": mailbox.account_id})
    core.jobs.run({"mail.sync", "mail.process"})
    doc_id = core.ingest.submitted[0][0]
    from docuhive.mail import ledger

    ledger.on_document(doc_id, "stored")
    assert core.rows("mail_attachments", document_id=doc_id)[0]["status"] == "stored"
