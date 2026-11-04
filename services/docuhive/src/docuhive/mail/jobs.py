"""Mail jobs (queue "mail"): sync, backfill pages, per-message processing.

Idempotent by construction: the ledger's UNIQUE (account_id, provider_msg_id) makes re-listing
harmless, mail.process is a no-op unless the message is `new` (or forced), and ingest.submit
reports duplicates by (owner, sha256).
"""

import hashlib
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import httpx
from sqlalchemy import select, update
from ulid import ULID

from docuhive import db, ingest, jobs
from docuhive.agents.base import AIDisabled, AllRoutesFailed, InvalidOutput
from docuhive.agents.triage import accept_threshold, triage
from docuhive.ai.budgets import BudgetExceeded, next_month_start
from docuhive.ai.privacy import NoAllowedRoute
from docuhive.contracts import IngestRequest, SourceInfo, SourceKind
from docuhive.mail import accounts
from docuhive.mail.base import AttachmentMeta, MsgRef, NeedsReauth, RateLimited
from docuhive.mail.models import Backfill, MailAccount, MailAttachment, MailMessage
from docuhive.mail.prefilter import candidates, prefilter, rules_for
from docuhive.mail.settings import get_mail_settings

PAGE_PACING_S = 2


def _account(account_id: int) -> MailAccount | None:
    with db.session() as s:
        acc = s.get(MailAccount, account_id)
        if acc is not None:
            s.expunge(acc)
        return acc


def record(account_id: int, refs: list[MsgRef]) -> list[int]:
    """Insert ledger rows for refs not seen before; returns the new mail_messages ids."""
    if not refs:
        return []
    with db.session() as s:
        seen = set(
            s.scalars(
                select(MailMessage.provider_msg_id).where(
                    MailMessage.account_id == account_id,
                    MailMessage.provider_msg_id.in_([r.provider_msg_id for r in refs]),
                )
            )
        )
        rows = [
            MailMessage(
                account_id=account_id,
                provider_msg_id=r.provider_msg_id,
                received_at=r.received_at,
                status="new",
            )
            for r in dict((r.provider_msg_id, r) for r in refs).values()
            if r.provider_msg_id not in seen
        ]
        s.add_all(rows)
        s.flush()
        return [r.id for r in rows]


def _enqueue_process(ids: list[int], backfill_id: int | None = None) -> None:
    for mid in ids:
        jobs.enqueue(
            "mail.process",
            {"message_id": mid, "backfill_id": backfill_id},
            queue="mail",
            dedupe_key=f"mail.process:{mid}",
        )


@jobs.periodic(
    "mail.sync.all", every=timedelta(minutes=get_mail_settings().sync_every_min), queue="mail"
)
def sync_all(payload: dict, ctx: Any) -> None:
    with db.session() as s:
        ids = list(s.scalars(select(MailAccount.id).where(MailAccount.status == "active")))
    for aid in ids:
        jobs.enqueue("mail.sync", {"account_id": aid}, queue="mail", dedupe_key=f"mail.sync:{aid}")


@jobs.handler("mail.sync", queue="mail")
def sync(payload: dict, ctx: Any) -> None:
    acc = _account(payload["account_id"])
    if acc is None or acc.status != "active":
        return
    start = datetime.now(UTC)
    overlap = timedelta(minutes=get_mail_settings().overlap_min)
    since = (acc.last_sync_at or acc.created_at or start) - overlap
    conn = accounts.connector_for(acc)
    token: str | None = None
    try:
        while True:
            refs, token = conn.list_range(since, start, token)
            _enqueue_process(record(acc.id, refs))
            ctx.heartbeat()
            if not token:
                break
    except RateLimited as e:
        ctx.defer(datetime.now(UTC) + timedelta(seconds=e.retry_after_s), "rate limited")
    except NeedsReauth:
        return  # oauth marked the account needs_reauth and notified the owner
    with db.session() as s:
        s.get_one(MailAccount, acc.id).last_sync_at = start  # start of this run, not its end


def _day(d: date) -> datetime:
    return datetime.combine(d, time.min, UTC)


@jobs.handler("mail.backfill.page", queue="mail")
def backfill_page(payload: dict, ctx: Any) -> None:
    with db.session() as s:
        bf = s.get(Backfill, payload["backfill_id"])
        if bf is None or bf.status != "running":  # pause / cancel take effect here
            return
        s.expunge(bf)
    acc = _account(bf.account_id)
    if acc is None or acc.status not in ("active", "paused"):
        return
    try:
        refs, nxt = accounts.connector_for(acc).list_range(
            _day(bf.date_from), _day(bf.date_to + timedelta(days=1)), bf.page_token
        )
    except RateLimited as e:
        ctx.defer(datetime.now(UTC) + timedelta(seconds=e.retry_after_s), "rate limited")
    except NeedsReauth:
        _set_backfill(bf.id, status="paused", last_error="needs_reauth")
        return
    new = record(acc.id, refs)
    with db.session() as s:  # page token and counters move together with the ledger rows
        row = s.get_one(Backfill, bf.id)
        row.scanned += len(refs)
        row.candidates += len(new)
        row.page_token = nxt
        if nxt is None:
            row.status, row.finished_at = "done", datetime.now(UTC)
        scanned = row.scanned
    _enqueue_process(new, bf.id)
    if nxt is not None:
        jobs.enqueue(
            "mail.backfill.page",
            {"backfill_id": bf.id},
            queue="mail",
            run_after=datetime.now(UTC) + timedelta(seconds=PAGE_PACING_S),
            dedupe_key=f"backfill:{bf.id}:{scanned}",
        )


def _set_backfill(backfill_id: int | None, **values: Any) -> None:
    if backfill_id is None:
        return
    with db.session() as s:
        row = s.get(Backfill, backfill_id)
        if row is None:
            return
        for k, v in values.items():
            setattr(row, k, getattr(row, k) + v if k in ("imported", "duplicates", "errors") else v)


def _finish(mid: int, status: str, reason: str | None = None, **extra: Any) -> None:
    with db.session() as s:
        s.execute(
            update(MailMessage)
            .where(MailMessage.id == mid)
            .values(status=status, reason=reason, processed_at=datetime.now(UTC), **extra)
        )


def _safe(name: str) -> str:
    return re.sub(r"[^\w.\- ]+", "_", name).strip(" .")[:120] or "attachment"


@jobs.handler("mail.process", queue="mail", timeout_s=900)
def process(payload: dict, ctx: Any) -> None:
    mid, force, bf_id = (
        payload["message_id"],
        payload.get("force", False),
        payload.get("backfill_id"),
    )
    with db.session() as s:
        row = s.get(MailMessage, mid)
        if row is None or (row.status != "new" and not force):
            return
        ref = MsgRef(row.provider_msg_id, row.received_at)
        account_id = row.account_id
    acc = _account(account_id)
    if acc is None:
        return
    conn = accounts.connector_for(acc)
    try:
        m = conn.get_message(ref)
        with db.session() as s:
            row = s.get_one(MailMessage, mid)
            row.received_at, row.rfc_message_id = m.ref.received_at, m.rfc_message_id
            row.email_from, row.subject = m.email_from[:500], m.subject[:500]
            dup = m.rfc_message_id and s.scalar(
                select(MailMessage.id).where(
                    MailMessage.account_id == account_id,
                    MailMessage.id != mid,
                    MailMessage.rfc_message_id == m.rfc_message_id,
                    MailMessage.status.in_(("imported", "partial")),
                )
            )
        if dup and not force:  # e.g. after an IMAP UIDVALIDITY change
            _finish(mid, "prefiltered_out", "prefilter:duplicate_message")
            _set_backfill(bf_id, duplicates=1)
            return
        rules = rules_for(acc.address)
        pre = prefilter(m, rules)
        selected: list[AttachmentMeta] = pre.candidate_attachments
        archive_body, doc_hint = pre.archive_body, None
        if force:  # "Import anyway": no triage; every reasonable attachment, else the body
            selected = candidates(m, rules) or [
                a for a in m.attachments if not a.inline and a.kind != "itemAttachment"
            ]
            archive_body = archive_body or not selected
        elif pre.decision == "skip":
            _finish(mid, "prefiltered_out", pre.reason)
            return
        elif pre.decision == "triage":
            try:
                res = triage(m, selected)
            except AIDisabled:
                res = None  # rules only
            except (NoAllowedRoute, InvalidOutput) as e:
                _finish(mid, "triage_rejected", f"triage skipped: {e}")
                return
            except BudgetExceeded as e:
                _set_backfill(bf_id, status="paused", last_error="budget")
                ctx.defer(next_month_start(), f"budget: {e}")
            if res is not None:
                out = res.value
                if not (out.archive and out.confidence >= accept_threshold()):
                    _finish(
                        mid,
                        "triage_rejected",
                        out.reason or "not a document",
                        triage_confidence=out.confidence,
                        ai_run_id=res.ai_run_id,
                    )
                    return
                selected = [a for a in selected if a.filename in out.attachments] or selected
                archive_body = archive_body or out.archive_body
                doc_hint = out.doc_hint
                with db.session() as s:
                    r = s.get_one(MailMessage, mid)
                    r.triage_confidence, r.ai_run_id = out.confidence, res.ai_run_id
        results = [_import(acc, mid, m, ref, conn, a, doc_hint) for a in selected]
        if archive_body:
            results.append(_import(acc, mid, m, ref, conn, None, doc_hint))
        if "submitted" in results:
            conn.mark_imported(ref)
        ok = [r for r in results if r in ("submitted", "duplicate", "skipped")]
        status = "imported" if len(ok) == len(results) else "partial" if ok else "error"
        _finish(mid, status, None if status == "imported" else "some attachments failed")
        _set_backfill(
            bf_id,
            imported=results.count("submitted"),
            duplicates=results.count("duplicate"),
            errors=results.count("error"),
        )
    except RateLimited as e:
        ctx.defer(datetime.now(UTC) + timedelta(seconds=e.retry_after_s), "rate limited")
    except NeedsReauth:
        return
    except (httpx.HTTPError, AllRoutesFailed) as e:
        raise jobs.RetryLater(str(e)) from e


def _import(
    acc: MailAccount,
    mid: int,
    m: Any,
    ref: MsgRef,
    conn: Any,
    att: AttachmentMeta | None,
    doc_hint: str | None,
) -> str:
    """Download one attachment (or the raw .eml for att=None) and submit it to ingest."""
    name = _safe(att.filename) if att else _safe(f"{m.subject or 'email'}.eml")
    if att is None and not name.endswith(".eml"):
        name += ".eml"
    row = MailAttachment(
        message_id=mid,
        provider_att_id=att.provider_att_id if att else None,
        filename=name,
        mime=att.mime if att else "message/rfc822",
        size=att.size if att else None,
        status="error",
    )
    dest = ingest.incoming_dir() / f"{ULID()}-{name}"
    try:
        if att and att.size and att.size > get_mail_settings().max_attachment_mb * 1024 * 1024:
            row.status, row.reason = "skipped", "too_large"
            return row.status
        (conn.download_attachment(ref, att, dest) if att else conn.download_raw(ref, dest))
        data = dest.read_bytes()
        if len(data) > get_mail_settings().max_attachment_mb * 1024 * 1024:
            dest.unlink()
            row.status, row.reason = "skipped", "too_large"
            return row.status
        row.sha256, row.size = hashlib.sha256(data).hexdigest(), len(data)
        with db.session() as s:
            prior = s.scalar(
                select(MailAttachment.document_id)
                .join(MailMessage, MailMessage.id == MailAttachment.message_id)
                .where(
                    MailMessage.account_id == acc.id,
                    MailAttachment.sha256 == row.sha256,
                    MailAttachment.status.in_(("submitted", "stored", "duplicate")),
                )
            )
        if prior:
            dest.unlink()
            row.status, row.document_id, row.reason = "duplicate", prior, "same file seen before"
            return row.status
        req = IngestRequest(
            owner_id=acc.owner_id,
            shared=acc.default_shared,
            hints={"doc_hint": doc_hint} if doc_hint else {},
            source=SourceInfo(
                kind=SourceKind.email,
                original_filename=name,
                account_id=acc.id,
                message_id=ref.provider_msg_id,
                email_from=m.email_from,
                subject=m.subject,
                received_at=m.ref.received_at,
            ),
        )
        try:
            res = ingest.submit([dest], req)
        except ingest.IngestRejected as e:
            row.status, row.reason = "skipped", f"rejected: {type(e).__name__}"
            return row.status
        row.document_id = res.document_id
        row.status = "duplicate" if res.status == "duplicate" else "submitted"
        return row.status
    except (OSError, LookupError) as e:
        row.reason = f"{type(e).__name__}: {e}"[:300]
        return "error"
    finally:
        dest.unlink(missing_ok=True)
        with db.session() as s:
            s.add(row)
