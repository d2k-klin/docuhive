"""Find people by user name, to share a plugin's records with them. Only ids and user
names leave here: never roles, passwords or anything else about a person."""

from sqlalchemy import select

from docuhive.db import session
from docuhive.db.models import User

from ._plugin import current


def find(username: str) -> int | None:
    """The id of the person who signs in as `username`, or None (also when disabled)."""
    current().require("users:find")
    with session() as db:
        row = db.execute(
            select(User.id, User.pw_hash).where(User.username == username.strip())
        ).first()
    return row.id if row and not row.pw_hash.startswith("!") else None


def names(ids: list[int]) -> dict[int, str]:
    """User names for these ids; unknown ids are left out."""
    current().require("users:find")
    if not ids:
        return {}
    with session() as db:
        rows = db.execute(select(User.id, User.username).where(User.id.in_(ids))).all()
    return {r.id: r.username for r in rows}
