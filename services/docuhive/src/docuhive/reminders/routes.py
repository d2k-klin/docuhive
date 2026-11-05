"""/api/reminders: upcoming deadlines, dismiss/done, and an iCalendar feed."""

import hashlib
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import select

from docuhive import db, documents, reminders
from docuhive.ai import coretables
from docuhive.ai.http import User, fail
from docuhive.contracts import CurrentUser

router = APIRouter(prefix="/api", tags=["reminders"])


@router.get("/reminders")
def upcoming(
    user: User,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> dict:
    return {
        "items": reminders.upcoming(user, date_from or date.today(), date_to),
        "next_cursor": None,
    }


def _resolve(reminder_id: int, user: CurrentUser, status: str) -> dict:
    try:
        reminders.resolve(reminder_id, user, status)
    except (LookupError, documents.NotFound):
        fail(404, "not_found", "Reminder not found")
    except PermissionError as e:
        fail(403, "forbidden", str(e))
    return {"ok": True}


@router.post("/reminders/{reminder_id}/dismiss")
def dismiss(reminder_id: int, user: User) -> dict:
    return _resolve(reminder_id, user, "dismissed")


@router.post("/reminders/{reminder_id}/done")
def done(reminder_id: int, user: User) -> dict:
    return _resolve(reminder_id, user, "done")


def _token_user(raw: str) -> CurrentUser | None:
    """Read-only lookup of a personal API token with the calendar scope. Calendar apps cannot
    send headers, so the token sits in a URL they store and may log: it must open nothing else.
    ponytail: mirrors OA's sha256 token hash; switch to an OA helper once exposed."""
    t, u = coretables.table("api_tokens"), coretables.table("users")
    with db.session() as s:
        row = s.execute(
            select(u.c.id, u.c.username, u.c.role, t.c.scopes)
            .join(u, u.c.id == t.c.user_id)
            .where(
                t.c.token_hash == hashlib.sha256(raw.encode()).hexdigest(), t.c.revoked_at.is_(None)
            )
        ).first()
    # Exactly calendar: a mixed token would carry its broader scopes everywhere else.
    if row is None or set(row.scopes) != {"calendar"}:
        return None
    return CurrentUser(id=row.id, username=row.username, role=row.role)


@router.get("/reminders.ics")
def calendar(token: str) -> Response:
    user = _token_user(token)
    if user is None:
        fail(401, "invalid_token", "Use a personal API token with the calendar scope")
    body = reminders.ics(reminders.upcoming(user, date.today()))
    return Response(body, media_type="text/calendar; charset=utf-8")
