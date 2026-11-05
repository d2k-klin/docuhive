"""/api/sources: mail accounts, OAuth, backfills, the triage log. Owner-scoped throughout."""

import imaplib
import socket
import ssl
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select

from docuhive import config, db, jobs
from docuhive.agents.triage import triage_is_local
from docuhive.ai.http import User, fail, page
from docuhive.contracts import CurrentUser, SetupCheck
from docuhive.mail import accounts, oauth
from docuhive.mail.imap import Imap
from docuhive.mail.models import Backfill, MailAccount, MailAttachment, MailMessage
from docuhive.mail.settings import MissingKey, get_mail_settings

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _acc_out(a: MailAccount) -> dict:
    return {
        "id": a.id,
        "provider": a.provider,
        "address": a.address,
        "display_name": a.display_name,
        "status": a.status,
        "last_sync_at": a.last_sync_at,
        "label_on_import": a.label_on_import,
        "default_shared": a.default_shared,
        "created_at": a.created_at,
    }


def _own(s, account_id: int, user: CurrentUser) -> MailAccount:  # type: ignore[no-untyped-def]
    a = s.get(MailAccount, account_id)
    if a is None or a.owner_id != user.id:
        fail(404, "not_found", "Mail account not found")
    return a


@router.get("/accounts")
def list_accounts(user: User) -> dict:
    with db.session() as s:
        rows = s.scalars(
            select(MailAccount).where(MailAccount.owner_id == user.id).order_by(MailAccount.id)
        )
        items = [_acc_out(a) for a in rows]
    # Email snippets are sensitive: the UI warns at connect time if triage runs in the cloud.
    return {
        "items": items,
        "triage_local": triage_is_local(),
        # Which "Sign in with …" buttons can work; otherwise the UI asks for an app password.
        "oauth": {"google": oauth.configured("google"), "microsoft": oauth.configured("microsoft")},
        "connection": {
            "credentials_ready": get_mail_settings().token_key is not None,
            "sync_every_min": get_mail_settings().sync_every_min,
            "oauth_redirects": {name: oauth.redirect_uri(name) for name in ("google", "microsoft")},
        },
        "next_cursor": None,
    }


class ImapIn(BaseModel):
    provider: str = "imap"
    host: str = Field(min_length=1)
    port: int = Field(default=993, ge=1, le=65535)
    ssl: bool = True
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    address: str | None = None
    folders: list[str] = Field(default=["INBOX"], min_length=1)
    default_shared: bool = True


APP_PASSWORD_HOSTS = {"imap.gmail.com", "imap.mail.me.com", "imap.mail.yahoo.com"}


def login_problem(error: Exception, host: str) -> str:
    """What went wrong connecting to a mailbox, in words a person can act on."""
    if isinstance(error, socket.gaierror):
        return (
            f"The mail server {host} can't be found. "
            "Check the address, or set the server under Server settings."
        )
    if isinstance(error, TimeoutError | ConnectionError | ssl.SSLError):
        return (
            f"The mail server {host} didn't answer on that port. "
            "Check the server and port under Server settings."
        )
    if isinstance(error, imaplib.IMAP4.error):
        reply = str(error).removeprefix("b'").removeprefix('b"').rstrip("'\"")
        return (
            "The mail server refused the login. Check the address and password; Gmail, iCloud and "
            "Yahoo need an app password, and GMX and WEB.DE need IMAP turned on in their settings."
            + (f" The server said: {reply}" if reply else "")
        )
    if isinstance(error, LookupError):
        return "A selected mail folder wasn't found. Check the folder names under Server settings."
    return "The mailbox couldn't be connected. Check the server settings and try again."


@router.post("/accounts")
def create_imap(body: ImapIn, user: User) -> dict:
    if body.provider != "imap":
        fail(400, "use_oauth", "Gmail and Microsoft accounts connect through OAuth")
    if body.host.strip().lower() in APP_PASSWORD_HOSTS:
        # Shown as "abcd efgh ijkl mnop"; the spaces are not part of the password.
        body.password = "".join(body.password.split())
    try:
        blob = accounts.encrypt(
            {
                "host": body.host,
                "port": body.port,
                "ssl": body.ssl,
                "username": body.username,
                "password": body.password,
                "folders": body.folders,
            }
        )
    except MissingKey as e:
        fail(409, "missing_key", str(e))
    try:
        conn = Imap(
            body.host, body.port, body.username, body.password, ssl=body.ssl, folders=body.folders
        )
        conn.test_login()  # test before saving
    except Exception as e:  # noqa: BLE001 - mapped to actionable copy
        fail(400, "imap_login_failed", login_problem(e, body.host))
    with db.session() as s:
        address = (body.address or body.username).lower()
        if s.scalar(
            select(MailAccount.id).where(
                MailAccount.provider == "imap", MailAccount.address == address
            )
        ):
            fail(409, "exists", "This mailbox is already connected")
        a = MailAccount(
            owner_id=user.id,
            provider="imap",
            address=address,
            enc_credentials=blob,
            default_shared=body.default_shared,
            sync_cursor={},
        )
        s.add(a)
        s.flush()
        out = _acc_out(a) | {"triage_local": triage_is_local()}
    jobs.enqueue(
        "mail.sync", {"account_id": out["id"]}, queue="mail", dedupe_key=f"mail.sync:{out['id']}"
    )
    return out


class AccountPatch(BaseModel):
    paused: bool | None = None
    label_on_import: bool | None = None
    default_shared: bool | None = None
    display_name: str | None = None


@router.patch("/accounts/{account_id}")
def patch_account(account_id: int, body: AccountPatch, user: User) -> dict:
    with db.session() as s:
        a = _own(s, account_id, user)
        if body.paused is not None and a.status in ("active", "paused"):
            a.status = "paused" if body.paused else "active"
        for k in ("label_on_import", "default_shared", "display_name"):
            if getattr(body, k) is not None:
                setattr(a, k, getattr(body, k))
        return _acc_out(a)


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, user: User) -> dict:
    """Removes credentials and the ledger. Imported documents stay in the archive."""
    with db.session() as s:
        _own(s, account_id, user)
        msg_ids = select(MailMessage.id).where(MailMessage.account_id == account_id)
        s.execute(delete(MailAttachment).where(MailAttachment.message_id.in_(msg_ids)))
        s.execute(delete(MailMessage).where(MailMessage.account_id == account_id))
        s.execute(delete(Backfill).where(Backfill.account_id == account_id))
        s.execute(delete(MailAccount).where(MailAccount.id == account_id))
    return {"ok": True}


@router.get("/oauth/{provider}/start")
def oauth_start(provider: str, user: User, label_on_import: bool = False) -> RedirectResponse:
    if provider not in ("google", "microsoft"):
        fail(404, "not_found", "Unknown provider")
    try:
        url = oauth.start_url(provider, user.id, label_on_import)
    except LookupError:
        # A full-page link, not an API call: send the person back with a readable reason.
        name = "Gmail" if provider == "google" else "Outlook"
        message = (
            f"{name} isn't set up on this server yet: an administrator first registers a "
            "sign-in app (docs/setup/mail-accounts.md)."
        )
        if provider == "google":  # Outlook.com no longer accepts IMAP passwords
            message += " You can connect Gmail with Other (IMAP) and an app password instead."

        query = urlencode({"error": "not_configured", "message": message})
        return RedirectResponse(f"/sources?{query}", status_code=302)
    return RedirectResponse(url, status_code=302)


@router.get("/oauth/{provider}/callback")
def oauth_callback(
    provider: str, user: User, code: str | None = None, state: str = "", error: str | None = None
) -> RedirectResponse:
    if error or not code:
        return RedirectResponse(f"/sources?error={error or 'cancelled'}", status_code=302)
    try:
        account_id = oauth.callback(provider, code, state, user.id)
    except (PermissionError, LookupError, MissingKey) as e:
        query = urlencode({"error": type(e).__name__, "message": str(e)})
        return RedirectResponse(f"/sources?{query}", status_code=302)
    jobs.enqueue(
        "mail.sync", {"account_id": account_id}, queue="mail", dedupe_key=f"mail.sync:{account_id}"
    )
    return RedirectResponse(f"/sources?connected={account_id}", status_code=302)


@router.post("/accounts/{account_id}/sync")
def sync_now(account_id: int, user: User) -> dict:
    with db.session() as s:
        _own(s, account_id, user)
    return {
        "job_id": jobs.enqueue(
            "mail.sync",
            {"account_id": account_id},
            queue="mail",
            dedupe_key=f"mail.sync:{account_id}",
        )
    }


class BackfillIn(BaseModel):
    date_from: date
    date_to: date


def _bf_out(b: Backfill) -> dict:
    return {
        k: getattr(b, k)
        for k in (
            "id",
            "account_id",
            "date_from",
            "date_to",
            "status",
            "scanned",
            "candidates",
            "imported",
            "duplicates",
            "errors",
            "created_at",
            "finished_at",
            "last_error",
        )
    }


@router.post("/accounts/{account_id}/backfills")
def create_backfill(account_id: int, body: BackfillIn, user: User) -> dict:
    if body.date_from > body.date_to:
        fail(400, "invalid_range", "The start date must be before the end date")
    with db.session() as s:
        _own(s, account_id, user)
        b = Backfill(
            account_id=account_id, date_from=body.date_from, date_to=body.date_to, status="running"
        )
        s.add(b)
        s.flush()
        out = _bf_out(b)
    jobs.enqueue(
        "mail.backfill.page",
        {"backfill_id": out["id"]},
        queue="mail",
        dedupe_key=f"backfill:{out['id']}:0",
    )
    return out


@router.get("/backfills")
def list_backfills(user: User, account_id: int | None = None) -> dict:
    with db.session() as s:
        q = (
            select(Backfill)
            .join(MailAccount, MailAccount.id == Backfill.account_id)
            .where(MailAccount.owner_id == user.id)
            .order_by(Backfill.id.desc())
        )
        if account_id:
            q = q.where(Backfill.account_id == account_id)
        return {"items": [_bf_out(b) for b in s.scalars(q)], "next_cursor": None}


@router.post("/backfills/{backfill_id}/{action}")
def backfill_action(backfill_id: int, action: str, user: User) -> dict:
    target = {"pause": "paused", "resume": "running", "cancel": "cancelled"}.get(action)
    if target is None:
        fail(404, "not_found", "Unknown action")
    with db.session() as s:
        b = s.get(Backfill, backfill_id)
        if b is None:
            fail(404, "not_found", "Backfill not found")
        _own(s, b.account_id, user)
        if b.status in ("done", "cancelled"):
            fail(409, "finished", "This backfill has finished")
        b.status = target
        if target == "running":
            b.last_error = None
        out = _bf_out(b)
    if target == "running":  # continue from the stored page token
        jobs.enqueue(
            "mail.backfill.page",
            {"backfill_id": backfill_id},
            queue="mail",
            dedupe_key=f"backfill:{backfill_id}:{out['scanned']}",
        )
    return out


@router.get("/messages")
def messages(
    user: User,
    account_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
) -> dict:
    """The triage log, newest first, with attachment outcomes and document links."""
    offset = int(cursor or 0)
    with db.session() as s:
        query = (
            select(MailMessage)
            .join(MailAccount, MailAccount.id == MailMessage.account_id)
            .where(MailAccount.owner_id == user.id)
            .order_by(MailMessage.received_at.desc(), MailMessage.id.desc())
            .offset(offset)
            .limit(limit + 1)
        )
        if account_id:
            query = query.where(MailMessage.account_id == account_id)
        if status:
            query = query.where(MailMessage.status == status)
        if q:
            like = f"%{q}%"
            query = query.where(
                or_(MailMessage.subject.ilike(like), MailMessage.email_from.ilike(like))
            )
        msgs = list(s.scalars(query))
        atts: dict[int, list[dict]] = {}
        for a in s.scalars(
            select(MailAttachment).where(MailAttachment.message_id.in_([m.id for m in msgs]))
        ):
            atts.setdefault(a.message_id, []).append(
                {
                    "filename": a.filename,
                    "status": a.status,
                    "reason": a.reason,
                    "document_id": a.document_id,
                }
            )
        items = [
            {
                "id": m.id,
                "account_id": m.account_id,
                "received_at": m.received_at,
                "email_from": m.email_from,
                "subject": m.subject,
                "status": m.status,
                "reason": m.reason,
                "triage_confidence": m.triage_confidence,
                "ai_run_id": m.ai_run_id,
                "attachments": atts.get(m.id, []),
            }
            for m in msgs
        ]
    return page(items, limit, offset)


@router.post("/messages/{message_id}/import")
def import_anyway(message_id: int, user: User) -> dict:
    with db.session() as s:
        m = s.get(MailMessage, message_id)
        if m is None:
            fail(404, "not_found", "Message not found")
        _own(s, m.account_id, user)
    return {
        "job_id": jobs.enqueue(
            "mail.process",
            {"message_id": message_id, "force": True},
            queue="mail",
            dedupe_key=f"mail.process:{message_id}:force",
        )
    }


@router.get("/rules")
def rules(user: User) -> dict:
    return config.load_yaml("mail-rules.yaml")


@router.get("/setup-status")
def setup_status(user: User) -> list[SetupCheck]:
    s = get_mail_settings()
    with db.session() as ses:
        accs = list(ses.scalars(select(MailAccount).where(MailAccount.owner_id == user.id)))
        imported = ses.scalar(
            select(func.count())
            .select_from(MailAttachment)
            .join(MailMessage, MailMessage.id == MailAttachment.message_id)
            .join(MailAccount, MailAccount.id == MailMessage.account_id)
            .where(
                MailAccount.owner_id == user.id, MailAttachment.status.in_(("submitted", "stored"))
            )
        )
    reauth = [a.address for a in accs if a.status == "needs_reauth"]
    checks = [
        SetupCheck(
            id="mail.key",
            area="mail",
            title="Encryption key for mail credentials",
            status="ok" if s.token_key else "todo",
            message="Set."
            if s.token_key
            else "Set DOCUHIVE_MAIL_TOKEN_KEY before connecting a mailbox "
            "(`docuhive mail gen-key`).",
            help_doc="docs/setup/mail-accounts.md",
        )
    ]
    if reauth:
        checks.append(
            SetupCheck(
                id="mail.reauth",
                area="mail",
                title="Reconnect mailbox",
                status="error",
                message=f"Reconnect: {', '.join(reauth)}.",
                action_label="Reconnect",
                action_href="/sources",
            )
        )
    checks.append(
        SetupCheck(
            id="mail.accounts",
            area="mail",
            title="Email accounts",
            status="ok" if accs else "optional",
            message=f"{len(accs)} connected, {imported or 0} documents imported."
            if accs
            else "Connect Gmail, Outlook or an IMAP mailbox to import attachments automatically.",
            action_label=None if accs else "Connect a mailbox",
            action_href="/sources",
            help_doc="docs/setup/mail-accounts.md",
        )
    )
    return checks
