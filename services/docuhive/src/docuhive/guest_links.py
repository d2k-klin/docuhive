"""Guest links: a person shares a fixed list of documents, read-only, for up to 30 days.

The token in the link is the credential: it is shown once, stored only as a hash, never set as a
cookie, and stops working when it expires or is revoked. The list is fixed when the link is made,
so a link never grows. Every view is written to each document's history. Off unless
DOCUHIVE_GUEST_LINKS=true: on a home network an outside advisor cannot reach the host anyway.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from docuhive import db
from docuhive import documents as core
from docuhive.contracts import CurrentUser, DocumentView
from docuhive.db.models import AuditLog, GuestLink

MAX_DAYS = 30


class Disabled(PermissionError):
    pass


class NeedsConfirmation(ValueError):
    """Private documents are in the list: the person must confirm once more."""

    def __init__(self, ids: list[str]) -> None:
        super().__init__("Some documents are private; confirm to include them")
        self.ids = ids


def enabled() -> bool:
    from docuhive.config import get_settings

    return bool(get_settings().guest_links)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create(
    user: CurrentUser,
    label: str,
    document_ids: list[str],
    days: int = 7,
    *,
    include_private: bool = False,
) -> tuple[GuestLink, str]:
    """(link, token). Only documents this person may see; private ones need `include_private`."""
    from docuhive import taxonomy
    from docuhive.ai.privacy import is_restricted

    if not enabled():
        raise Disabled("Guest links are switched off on this installation")
    if not label.strip() or not document_ids or not 1 <= days <= MAX_DAYS:
        raise ValueError(f"A label, at least one document and 1 to {MAX_DAYS} days are needed")
    views = [core.get_for_user(d, user) for d in dict.fromkeys(document_ids)]  # NotFound
    tax = taxonomy.load()
    private = [v.id for v in views if is_restricted(v, tax)]
    if private and not include_private:
        raise NeedsConfirmation(private)
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    with db.session() as s:
        link = GuestLink(
            token_hash=_hash(token),
            created_by=user.id,
            label=label.strip()[:200],
            document_ids=[v.id for v in views],
            expires_at=now + timedelta(days=days),
            created_at=now,
        )
        s.add(link)
        s.flush()
        s.expunge(link)
    return link, token


def mine(user: CurrentUser) -> list[GuestLink]:
    with db.session() as s:
        rows = list(
            s.scalars(
                select(GuestLink)
                .where(GuestLink.created_by == user.id)
                .order_by(GuestLink.id.desc())
            )
        )
        for row in rows:
            s.expunge(row)
        return rows


def revoke(user: CurrentUser, link_id: int) -> None:
    with db.session() as s:
        link = s.scalar(
            select(GuestLink).where(GuestLink.id == link_id, GuestLink.created_by == user.id)
        )
        if link is None:
            raise LookupError(link_id)
        link.revoked_at = link.revoked_at or datetime.now(UTC)


def open_link(token: str) -> tuple[GuestLink, list[DocumentView]] | None:
    """The link and its documents still in the archive, or None (unknown, expired, revoked)."""
    if not enabled() or not token or len(token) > 100:
        return None
    now = datetime.now(UTC)
    with db.session() as s:
        link = s.scalar(select(GuestLink).where(GuestLink.token_hash == _hash(token)))
        if link is None or link.revoked_at is not None or link.expires_at <= now:
            return None
        link.last_used_at = now
        s.flush()
        s.expunge(link)
    docs = []
    for doc_id in link.document_ids:
        try:
            view = core.get(doc_id)
        except core.NotFound:
            continue
        if view.deleted_at is None and view.status == "stored":
            docs.append(view)
    return link, docs


def log_view(link: GuestLink, document_id: str, what: str) -> None:
    with db.session() as s:
        s.add(
            AuditLog(
                actor=f"guest:{link.id}",
                document_id=document_id,
                action="guest_view",
                after={"label": link.label, "what": what},
            )
        )
