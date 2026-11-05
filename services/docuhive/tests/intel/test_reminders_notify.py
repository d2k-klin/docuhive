import json
from datetime import date

import httpx
import pytest
from cryptography.fernet import Fernet
from docuhive import notify, reminders
from docuhive.contracts import CurrentUser
from docuhive.notify import Notification, send, send_once
from docuhive.notify.models import NotificationChannel

OWNER = CurrentUser(id=1, username="dev", role="admin")


def contract(core, end="2027-03-31", notice="90", title="Stromvertrag", **kw):
    return core.docs.add(
        "Mietvertrag",
        document_type="contract",
        title=title,
        facts={
            "end_date": {"type": "date", "value": end},
            "notice_period_days": {"type": "number", "value": notice},
        },
        **kw,
    )


def test_notice_deadline_acceptance(core):
    doc = contract(core)
    reminders.sync(doc, today=date(2026, 11, 3))
    rows = {(r["fact"], r["remind_on"]) for r in core.rows("reminders")}
    assert ("notice_deadline", date(2026, 12, 1)) in rows
    assert ("notice_deadline", date(2026, 12, 24)) in rows
    assert ("end_date", date(2026, 12, 31)) in rows  # 90 days before 2027-03-31
    assert core.rows("reminders", fact="notice_deadline")[0]["due_on"] == date(2026, 12, 31)


def test_past_dates_skipped_and_recompute_on_change(core):
    from sqlalchemy import update

    from tests.fakes.intel import doc_facts

    doc = contract(core, end="2026-12-01", notice="0")
    reminders.sync(doc, today=date(2026, 11, 3))
    # end_date reminders (Sep 2, Nov 1) and the 30-day notice reminder (Nov 1) are in the past
    assert {(r["fact"], r["remind_on"]) for r in core.rows("reminders")} == {
        ("notice_deadline", date(2026, 11, 24))
    }
    with core.session() as s:
        s.execute(
            update(doc_facts)
            .where(doc_facts.c.field == "end_date")
            .values(value_text="2027-06-30", value_date=date(2027, 6, 30))
        )
    reminders.sync(doc, today=date(2026, 11, 3))
    assert {r["due_on"] for r in core.rows("reminders", fact="end_date")} == {date(2027, 6, 30)}


def ntfy_channel(core, monkeypatch, kinds=None):
    from docuhive.mail.settings import get_mail_settings

    monkeypatch.setenv("DOCUHIVE_MAIL_TOKEN_KEY", Fernet.generate_key().decode())
    get_mail_settings.cache_clear()
    sent: list[httpx.Request] = []

    def post(url, content=None, headers=None, timeout=None):
        req = httpx.Request("POST", url, content=content, headers=headers)
        sent.append(req)
        return httpx.Response(200, request=req)

    monkeypatch.setattr(notify.httpx, "post", post)
    cfg = {"server": "https://ntfy.example", "topic": "dh-test", "token": "tk"}
    if kinds:
        cfg["kinds"] = kinds
    with core.session() as s:
        s.add(NotificationChannel(user_id=1, kind="ntfy", config_enc=notify.encrypt(cfg)))
    return sent


def test_scan_sends_once_and_skips_trashed(core, monkeypatch):
    sent = ntfy_channel(core, monkeypatch)
    doc = contract(core)
    trashed = contract(core, title="Old")
    reminders.sync(doc, today=date(2026, 11, 3))
    reminders.sync(trashed, today=date(2026, 11, 3))
    core.docs.trash(trashed)
    assert reminders.scan(date(2026, 12, 1)) == 1  # the 30-day notice reminder (trashed skipped)
    assert reminders.scan(date(2026, 12, 1)) == 0  # sent once
    assert all(r.url.path == "/dh-test" for r in sent)
    assert sent[0].headers["Title"] == "Notice deadline: Stromvertrag"
    assert sent[0].headers["Authorization"] == "Bearer tk"
    assert sent[0].headers["Click"].endswith(f"/documents/{doc}")


def test_rate_limit_dedupe_and_kind_toggle(core, monkeypatch):
    sent = ntfy_channel(core, monkeypatch, kinds=["review_backlog"])
    n = Notification(kind="review_backlog", title="30 waiting", body="b", user_id=1)
    assert send_once("review_backlog:1", n) and not send_once("review_backlog:1", n)
    send(Notification(kind="budget", title="ignored by toggle", body="b", user_id=1))
    assert len(sent) == 1


def test_email_channel(core, monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            sent.append("tls")

        def login(self, u, p):
            sent.append(("login", u))

        def send_message(self, msg):
            sent.append(msg)

    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    notify.send_email(
        {"host": "smtp.example", "from": "dh@x", "to": "me@x", "username": "u", "password": "p"},
        Notification(kind="t", title="Hello", body="Body", url="/review"),
    )
    assert sent[0] == "tls" and sent[2]["Subject"] == "Hello"
    assert "/review" in sent[2].get_content()


def test_plugin_channel_from_entry_point(core, monkeypatch):
    from docuhive import config

    got = []

    def telegram(cfg, n):
        got.append((cfg["chat"], n.title))

    telegram.kind = "telegram"
    monkeypatch.setattr(
        config, "plugins", lambda hook: [telegram] if hook == "notify_channel" else []
    )
    ntfy_channel(core, monkeypatch)
    with core.session() as s:
        s.add(
            NotificationChannel(
                user_id=1, kind="telegram", config_enc=notify.encrypt({"chat": "42"})
            )
        )
    send(Notification(kind="quarantine", title="Q", body="b", user_id=1))
    assert got == [("42", "Q")]


def test_failing_channel_never_raises(core, monkeypatch):
    ntfy_channel(core, monkeypatch)
    monkeypatch.setattr(notify, "send_ntfy", lambda c, n: (_ for _ in ()).throw(OSError("down")))
    send(Notification(kind="quarantine", title="Q", body="b", user_id=1))
    assert core.rows("notification_log")[0]["ok"] is False


def test_ics_feed_parses_back(core):
    doc = contract(core)
    reminders.sync(doc, today=date(2026, 11, 3))
    body = reminders.ics(reminders.upcoming(OWNER, date(2026, 11, 3)))
    lines = body.split("\r\n")
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-2] == "END:VCALENDAR"
    assert lines.count("BEGIN:VEVENT") == lines.count("END:VEVENT") == 2
    assert "DTSTART;VALUE=DATE:20261231" in lines


@pytest.mark.parametrize("status", ["dismissed", "done"])
def test_resolve_by_owner_only(core, status):
    doc = contract(core)
    reminders.sync(doc, today=date(2026, 11, 3))
    rid = core.rows("reminders")[0]["id"]
    with pytest.raises(PermissionError):
        reminders.resolve(rid, CurrentUser(id=2, username="m", role="member"), status)
    reminders.resolve(rid, OWNER, status)
    fact = core.rows("reminders", id=rid)[0]["fact"]
    assert {r["status"] for r in core.rows("reminders", fact=fact)} == {status}


def test_dead_jobs_and_backup_checks(core, monkeypatch, tmp_path):
    from datetime import UTC, datetime

    from docuhive.notify import jobs as njobs
    from sqlalchemy import insert

    from tests.fakes.intel import jobs_table

    with core.session() as s:
        s.execute(
            insert(jobs_table).values(
                id=7,
                kind="ai.classify",
                status="dead",
                last_error="boom",
                finished_at=datetime.now(UTC),
            )
        )
    njobs.scan_dead_jobs({}, None)
    njobs.scan_dead_jobs({}, None)
    assert [r["dedupe_key"] for r in core.rows("notification_log")] == ["job_dead:7"]
    monkeypatch.setattr(njobs, "vault_root", lambda: tmp_path)
    (tmp_path / "_system").mkdir()
    (tmp_path / "_system" / "backup-status.json").write_text(
        json.dumps({"at": "2020-01-01T00:00:00+00:00", "ok": True})
    )
    njobs.backup_check({}, None)
    assert core.rows("notification_log")[-1]["kind"] == "backup"
