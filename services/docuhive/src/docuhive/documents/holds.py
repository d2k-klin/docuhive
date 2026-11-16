"""Holds: a document, or some of its fields, may not change while a hold is active.

An issued invoice, a filed return, a letter that was sent: the record must stay as it was. Every
route that changes metadata or trashes a document goes through `check` or `check_trash`, for
every actor, people included. Only an administrator lifts a hold, with a reason; nothing is
ever deleted. Holds stop the application, not someone with direct access to the files: a
changed original is caught by the vault's checksum scan.
"""

from datetime import UTC, date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from docuhive.db.models import AuditLog, DocumentHold

EVERYTHING = "*"


class Held(Exception):
    """The change touches a held field. The message is for people."""

    def __init__(self, document_id: str, hold: DocumentHold, fields: list[str]) -> None:
        until = f" until {hold.until:%d.%m.%Y}" if hold.until else ""
        super().__init__(f"This document is locked{until}: {hold.reason}.")
        self.document_id, self.reason, self.until, self.fields = (
            document_id,
            hold.reason,
            hold.until,
            fields,
        )


def active(session: Session, document_id: str) -> list[DocumentHold]:
    return list(
        session.scalars(
            select(DocumentHold)
            .where(
                DocumentHold.document_id == document_id,
                DocumentHold.lifted_at.is_(None),
                or_(DocumentHold.until.is_(None), DocumentHold.until >= date.today()),
            )
            .order_by(DocumentHold.id)
        )
    )


def covers(hold: DocumentHold, field: str) -> bool:
    return (
        EVERYTHING in hold.fields
        or field in hold.fields
        or (field.startswith("facts.") and "facts" in hold.fields)
    )


def check(session: Session, document_id: str, fields: list[str]) -> None:
    for hold in active(session, document_id):
        if blocked := [f for f in fields if covers(hold, f)]:
            raise Held(document_id, hold, blocked)


def check_trash(session: Session, document_id: str) -> None:
    holds = active(session, document_id)
    if holds:
        raise Held(document_id, holds[0], ["*"])


def place(
    session: Session,
    document_id: str,
    reason: str,
    *,
    placed_by: str,
    fields: list[str] | None = None,
    until: date | None = None,
) -> DocumentHold:
    if not reason.strip():
        raise ValueError("A hold needs a reason people can read")
    hold = DocumentHold(
        document_id=document_id,
        reason=reason.strip(),
        fields=fields or [EVERYTHING],
        until=until,
        placed_by=placed_by,
        placed_at=datetime.now(UTC),
    )
    session.add(hold)
    session.add(
        AuditLog(
            actor=placed_by,
            document_id=document_id,
            action="hold",
            after={"reason": hold.reason, "fields": hold.fields, "until": until and str(until)},
        )
    )
    session.flush()
    return hold


def lift(session: Session, hold_id: int, *, lifted_by: str, reason: str) -> DocumentHold:
    if not reason.strip():
        raise ValueError("Say why the hold is lifted")
    hold = session.get(DocumentHold, hold_id, with_for_update=True)
    if hold is None or hold.lifted_at is not None:
        raise LookupError(hold_id)
    hold.lifted_at, hold.lifted_by, hold.lift_reason = datetime.now(UTC), lifted_by, reason.strip()
    session.add(
        AuditLog(
            actor=lifted_by,
            document_id=hold.document_id,
            action="hold_lifted",
            before={"reason": hold.reason},
            after={"lift_reason": hold.lift_reason},
        )
    )
    return hold
