"""/api/notifications: channels (encrypted config), test send, log, setup status."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import delete, select

from docuhive import db
from docuhive.ai.http import User, fail
from docuhive.contracts import SetupCheck
from docuhive.mail.settings import MissingKey
from docuhive.notify import KINDS, Notification, decrypt, deliver, encrypt, senders
from docuhive.notify.models import NotificationChannel, NotificationLog

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
SECRET_KEYS = {"password", "token"}


class ChannelIn(BaseModel):
    kind: str  # ntfy | email | plugin kind
    # ntfy: {server, topic, token?}; email: {host, port, starttls, username, password, from, to}
    config: dict
    kinds: list[str] | None = None  # per-kind toggles; None = all
    enabled: bool = True


def _out(c: NotificationChannel) -> dict:
    try:
        cfg = decrypt(c.config_enc)
    except Exception:  # noqa: BLE001 - wrong key: show the channel, not the config
        cfg = {"error": "cannot decrypt (key changed?)"}
    safe = {k: ("••••" if k in SECRET_KEYS and v else v) for k, v in cfg.items()}
    return {
        "id": c.id,
        "kind": c.kind,
        "enabled": c.enabled,
        "config": safe,
        "created_at": c.created_at,
    }


@router.get("/channels")
def channels(user: User) -> dict:
    with db.session() as s:
        rows = s.scalars(
            select(NotificationChannel)
            .where(NotificationChannel.user_id == user.id)
            .order_by(NotificationChannel.id)
        )
        return {
            "items": [_out(c) for c in rows],
            "kinds": KINDS,
            "channel_kinds": sorted(senders()),
        }


@router.post("/channels")
def create_channel(body: ChannelIn, user: User) -> dict:
    if body.kind not in senders():
        fail(400, "unknown_kind", f"Unknown channel kind {body.kind!r}")
    required = {"ntfy": ["topic"], "email": ["host", "from", "to"]}.get(body.kind, [])
    if missing := [k for k in required if not body.config.get(k)]:
        fail(400, "missing_fields", f"Fill in: {', '.join(missing)}", fields=missing)
    cfg = body.config | ({"kinds": body.kinds} if body.kinds is not None else {})
    try:
        blob = encrypt(cfg)
    except MissingKey as e:
        fail(409, "missing_key", str(e))
    with db.session() as s:
        c = NotificationChannel(
            user_id=user.id, kind=body.kind, config_enc=blob, enabled=body.enabled
        )
        s.add(c)
        s.flush()
        return _out(c)


class ChannelPatch(BaseModel):
    enabled: bool | None = None
    kinds: list[str] | None = None


@router.patch("/channels/{cid}")
def patch_channel(cid: int, body: ChannelPatch, user: User) -> dict:
    with db.session() as s:
        c = s.get(NotificationChannel, cid)
        if c is None or c.user_id != user.id:
            fail(404, "not_found", "Channel not found")
        if body.enabled is not None:
            c.enabled = body.enabled
        if body.kinds is not None:
            c.config_enc = encrypt(decrypt(c.config_enc) | {"kinds": body.kinds})
        return _out(c)


@router.delete("/channels/{cid}")
def delete_channel(cid: int, user: User) -> dict:
    with db.session() as s:
        n = s.execute(
            delete(NotificationChannel).where(
                NotificationChannel.id == cid, NotificationChannel.user_id == user.id
            )
        ).rowcount  # type: ignore[attr-defined]
    if not n:
        fail(404, "not_found", "Channel not found")
    return {"ok": True}


@router.post("/channels/{cid}/test")
def test_channel(cid: int, user: User) -> dict:
    with db.session() as s:
        c = s.get(NotificationChannel, cid)
        if c is None or c.user_id != user.id:
            fail(404, "not_found", "Channel not found")
        s.expunge(c)
    err = deliver(
        c,
        Notification(
            kind="test",
            title="DocuHive test notification",
            body="If you can read this, notifications work.",
            url="/settings/notifications",
            user_id=user.id,
        ),
    )
    with db.session() as s:
        s.add(
            NotificationLog(
                user_id=user.id,
                kind="test",
                title="Test",
                channel_id=cid,
                ok=err is None,
                error=err,
            )
        )
    return {"ok": err is None, "error": err}


@router.get("/log")
def log(user: User, limit: int = 50) -> dict:
    with db.session() as s:
        rows = s.scalars(
            select(NotificationLog)
            .where(NotificationLog.user_id == user.id)
            .order_by(NotificationLog.id.desc())
            .limit(min(limit, 200))
        )
        return {
            "items": [
                {
                    "id": r.id,
                    "at": r.at,
                    "kind": r.kind,
                    "title": r.title,
                    "channel_id": r.channel_id,
                    "ok": r.ok,
                    "error": r.error,
                }
                for r in rows
            ],
            "next_cursor": None,
        }


@router.get("/setup-status")
def setup_status(user: User) -> list[SetupCheck]:
    with db.session() as s:
        n = len(
            list(
                s.scalars(
                    select(NotificationChannel.id).where(
                        NotificationChannel.user_id == user.id,
                        NotificationChannel.enabled.is_(True),
                    )
                )
            )
        )
    status: Literal["ok", "optional"] = "ok" if n else "optional"
    return [
        SetupCheck(
            id="notifications.channel",
            area="notifications",
            title="Notifications",
            status=status,
            message=f"{n} channel(s) enabled."
            if n
            else "Get deadline reminders and problem alerts on your phone (ntfy) or by email.",
            action_label=None if n else "Add a channel",
            action_href="/settings/notifications",
            help_doc="docs/setup/notifications.md",
        )
    ]
