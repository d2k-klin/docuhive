"""Administrator user management; data visibility is never elevated by this role."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from docuhive.auth import create_user, hash_password, require_admin
from docuhive.contracts import CurrentUser
from docuhive.db import session
from docuhive.db.models import ApiToken, AuthSession, User

router = APIRouter(prefix="/api/users", tags=["users"])
Admin = Annotated[CurrentUser, Depends(require_admin)]


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=1024)
    role: Literal["admin", "member"] = "member"


class UserPatch(BaseModel):
    role: Literal["admin", "member"] | None = None
    disabled: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=1024)


@router.get("")
def users(
    user: Admin,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: int | None = Query(default=None, ge=0),
) -> dict:
    query = select(User).order_by(User.id).limit(limit + 1)
    if cursor is not None:
        query = query.where(User.id > cursor)
    with session() as db:
        rows = list(db.scalars(query))
        return {
            "items": [
                {
                    "id": row.id,
                    "username": row.username,
                    "role": row.role,
                    "disabled": row.pw_hash.startswith("!"),
                    "created_at": row.created_at,
                }
                for row in rows[:limit]
            ],
            "next_cursor": str(rows[limit - 1].id) if len(rows) > limit else None,
        }


@router.post("", status_code=201)
def add_user(body: UserCreate, user: Admin) -> dict:
    try:
        user_id = create_user(body.username, body.password, admin=body.role == "admin")
    except IntegrityError as error:
        raise HTTPException(409, "That username is already in use") from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {"id": user_id, "username": body.username.strip(), "role": body.role}


@router.patch("/{user_id}", status_code=204)
def edit_user(user_id: int, body: UserPatch, user: Admin) -> None:
    if body.disabled is False and body.password is None:
        raise HTTPException(422, "Set a new password to enable this user")
    with session() as db:
        row = db.scalar(select(User).where(User.id == user_id).with_for_update())
        if row is None:
            raise HTTPException(404, "User not found")
        if body.role:
            row.role = body.role
        if body.password:
            row.pw_hash = hash_password(body.password)
        if body.disabled:
            row.pw_hash = "!disabled"
        db.execute(delete(AuthSession).where(AuthSession.user_id == row.id))
        for token in db.scalars(select(ApiToken).where(ApiToken.user_id == row.id)):
            token.revoked_at = datetime.now(UTC)
