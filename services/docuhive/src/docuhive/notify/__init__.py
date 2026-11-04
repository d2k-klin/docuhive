"""Notifications (QA-05, AUTO-03): fan out to a user's channels. Never raises.

Built-in channels: ntfy (HTTP POST) and email (SMTP). Plugins add more through the entry point
hook `notify_channel`: a callable `fn(config: dict, n: Notification)` with an attribute `kind`.
Channel configs are encrypted with DOCUHIVE_AI_NOTIFY_KEY, or DOCUHIVE_MAIL_TOKEN_KEY if unset.
"""

import json
import logging
import smtplib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Literal

import httpx
from pydantic import BaseModel
from sqlalchemy import select

from docuhive import config, db
from docuhive.ai import coretables
from docuhive.ai.settings import get_ai_settings
from docuhive.mail.settings import fernet
from docuhive.notify.models import NotificationChannel, NotificationLog

log = logging.getLogger(__name__)
KINDS = ["reminder", "job_dead", "quarantine", "review_backlog", "mail_reauth", "budget", "backup"]


class Notification(BaseModel):
    kind: str
    title: str
    body: str  # plain text, no document content beyond the title (privacy)
    url: str | None = None  # app path ("/documents/<id>") or absolute URL
    priority: Literal["low", "default", "high"] = "default"
    user_id: int | None = None  # None = all admins


def _fernet():  # type: ignore[no-untyped-def]
    return fernet(get_ai_settings().notify_key)


def encrypt(cfg: dict) -> bytes:
    return _fernet().encrypt(json.dumps(cfg).encode())


def decrypt(blob: bytes) -> dict:
    return json.loads(_fernet().decrypt(blob))


def _absolute(url: str | None) -> str | None:
    if url and url.startswith("/"):
        from docuhive.config.settings import get_settings

        return get_settings().public_url.rstrip("/") + url
    return url


def send_ntfy(cfg: dict, n: Notification) -> None:
    headers = {"Title": n.title, "Priority": n.priority}
    if url := _absolute(n.url):
        headers["Click"] = url
    if cfg.get("token"):
        headers["Authorization"] = f"Bearer {cfg['token']}"
    server = cfg.get("server", "https://ntfy.sh").rstrip("/")
    httpx.post(
        f"{server}/{cfg['topic']}", content=n.body.encode(), headers=headers, timeout=10
    ).raise_for_status()


def send_email(cfg: dict, n: Notification) -> None:
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = n.title, cfg["from"], cfg["to"]
    url = _absolute(n.url)
    msg.set_content(n.body + (f"\n\n{url}" if url else ""))
    with smtplib.SMTP(cfg["host"], int(cfg.get("port", 587)), timeout=20) as smtp:
        if cfg.get("starttls", True):
            smtp.starttls()
        if cfg.get("username"):
            smtp.login(cfg["username"], cfg["password"])
        smtp.send_message(msg)


def senders() -> dict[str, Callable[[dict, Notification], None]]:
    out: dict[str, Callable[[dict, Notification], None]] = {"ntfy": send_ntfy, "email": send_email}
    for fn in config.plugins("notify_channel"):
        if kind := getattr(fn, "kind", None):
            out.setdefault(kind, fn)
    return out


def _recipients(n: Notification) -> list[int]:
    if n.user_id is not None:
        return [n.user_id]
    users = coretables.table("users")
    with db.session() as s:
        return list(s.scalars(select(users.c.id).where(users.c.role == "admin")))


def deliver(channel: NotificationChannel, n: Notification) -> str | None:
    """Send through one channel; returns the error text or None."""
    try:
        cfg = decrypt(channel.config_enc)
        if cfg.get("kinds") and n.kind not in cfg["kinds"]:
            return "kind disabled"
        send = senders().get(channel.kind)
        if send is None:
            return f"unknown channel kind {channel.kind}"
        send(cfg, n)
        return None
    except Exception as e:  # noqa: BLE001 - a broken channel must never break the caller
        return f"{type(e).__name__}: {e}"


def send(n: Notification, dedupe_key: str | None = None) -> None:
    try:
        for uid in _recipients(n):
            with db.session() as s:
                chans = list(
                    s.scalars(
                        select(NotificationChannel).where(
                            NotificationChannel.user_id == uid,
                            NotificationChannel.enabled.is_(True),
                        )
                    )
                )
                s.expunge_all()
            results: list[tuple[int | None, str | None]] = [(c.id, deliver(c, n)) for c in chans]
            results = results or [(None, "no enabled channel")]
            with db.session() as s:
                for cid, err in results:
                    if err == "kind disabled":
                        continue
                    if err:
                        log.warning("notification %s via channel %s failed: %s", n.kind, cid, err)
                    s.add(
                        NotificationLog(
                            user_id=uid,
                            kind=n.kind,
                            title=n.title,
                            channel_id=cid,
                            ok=err is None,
                            error=err,
                            dedupe_key=dedupe_key,
                        )
                    )
    except Exception:  # noqa: BLE001
        log.exception("notify.send failed for %s", n.kind)


def send_once(key: str, n: Notification, window: timedelta = timedelta(hours=24)) -> bool:
    """Rate limit: the same key is sent at most once per window. Returns True if sent."""
    since = datetime.now(UTC) - window
    with db.session() as s:
        seen = s.scalar(
            select(NotificationLog.id)
            .where(NotificationLog.dedupe_key == key, NotificationLog.at >= since)
            .limit(1)
        )
    if seen:
        return False
    send(n, dedupe_key=key)
    return True
