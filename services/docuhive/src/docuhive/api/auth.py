"""Browser login, sessions and personal access tokens."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from docuhive.auth import (
    _dummy_hash,
    check_csrf,
    current_user,
    hash_password,
    password_hasher,
    token_hash,
    verify_password,
)
from docuhive.auth.rate_limit import LoginLimiter
from docuhive.config.settings import get_settings
from docuhive.contracts import CurrentUser
from docuhive.db import session
from docuhive.db.models import ApiToken, AuthSession, User

router = APIRouter(tags=["auth"])
UserDependency = Annotated[CurrentUser, Depends(current_user)]
limiter = LoginLimiter()


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[Literal["upload", "read", "write", "admin"]] = Field(min_length=1)


@router.post("/api/auth/login", status_code=204)
def login(body: Login, request: Request, response: Response) -> None:
    check_csrf(request)
    ip = request.client.host if request.client else "unknown"
    if not limiter.allowed(body.username, ip):
        raise HTTPException(
            429,
            {"code": "rate_limited", "message": "Try again in 15 minutes.", "details": {}},
            headers={"Retry-After": "900"},
        )
    with session() as db:
        user = db.scalar(select(User).where(User.username == body.username))
        stored = user.pw_hash if user and not user.pw_hash.startswith("!") else _dummy_hash
        valid = verify_password(stored, body.password)
        if user is None or user.pw_hash.startswith("!") or not valid:
            limiter.failed(body.username, ip)
            raise HTTPException(401, "Username or password is incorrect")
        if password_hasher.check_needs_rehash(user.pw_hash):
            user.pw_hash = password_hasher.hash(body.password)
        raw = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        db.add(
            AuthSession(
                token_hash=token_hash(raw),
                user_id=user.id,
                expires_at=now + timedelta(days=30),
                user_agent=request.headers.get("user-agent", "")[:512],
            )
        )
    response.set_cookie(
        "dh_session",
        raw,
        httponly=True,
        secure=get_settings().env != "dev",
        samesite="lax",
        max_age=30 * 86400,
        path="/",
    )


@router.get("/api/auth/me", response_model=CurrentUser)
def me(user: UserDependency) -> CurrentUser:
    return user


@router.post("/api/auth/logout", status_code=204)
def logout(request: Request, response: Response, user: UserDependency) -> None:
    raw = request.cookies.get("dh_session")
    if raw:
        with session() as db:
            db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(raw)))
    response.delete_cookie("dh_session", path="/")


@router.post("/api/auth/logout-everywhere", status_code=204)
def logout_everywhere(response: Response, user: UserDependency) -> None:
    with session() as db:
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    response.delete_cookie("dh_session", path="/")


@router.post("/api/auth/password", status_code=204)
def password(body: PasswordChange, response: Response, user: UserDependency) -> None:
    with session() as db:
        row = db.get(User, user.id)
        if not row or not verify_password(row.pw_hash, body.current_password):
            raise HTTPException(401, "Current password is incorrect")
        row.pw_hash = hash_password(body.new_password)
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        for token in db.scalars(select(ApiToken).where(ApiToken.user_id == user.id)):
            token.revoked_at = datetime.now(UTC)
    response.delete_cookie("dh_session", path="/")


@router.get("/api/auth/sessions")
def sessions(user: UserDependency) -> dict:
    with session() as db:
        rows = db.scalars(
            select(AuthSession)
            .where(AuthSession.user_id == user.id, AuthSession.expires_at > datetime.now(UTC))
            .order_by(AuthSession.created_at.desc())
        )
        return {
            "items": [
                {
                    "created_at": s.created_at,
                    "expires_at": s.expires_at,
                    "last_seen_at": s.last_seen_at,
                    "user_agent": s.user_agent,
                }
                for s in rows
            ],
            "next_cursor": None,
        }


@router.post("/api/tokens", status_code=201)
def create_token(body: TokenCreate, user: UserDependency) -> dict:
    if "admin" in body.scopes and user.role != "admin":
        raise HTTPException(403, "Only administrators can create admin tokens")
    prefix = secrets.token_hex(4)
    raw = f"dh_{prefix}_{secrets.token_urlsafe(32)}"
    with session() as db:
        row = ApiToken(
            user_id=user.id,
            name=body.name,
            scopes=sorted(set(body.scopes)),
            prefix=prefix,
            token_hash=token_hash(raw),
        )
        db.add(row)
        db.flush()
        return {
            "id": row.id,
            "token": raw,
            "prefix": prefix,
            "name": row.name,
            "scopes": row.scopes,
        }


@router.get("/api/tokens")
def tokens(user: UserDependency) -> dict:
    with session() as db:
        rows = db.scalars(
            select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.id.desc())
        )
        return {
            "items": [
                {
                    "id": t.id,
                    "name": t.name,
                    "prefix": t.prefix,
                    "scopes": t.scopes,
                    "created_at": t.created_at,
                    "last_used_at": t.last_used_at,
                    "revoked_at": t.revoked_at,
                }
                for t in rows
            ],
            "next_cursor": None,
        }


@router.delete("/api/tokens/{token_id}", status_code=204)
def revoke_token(token_id: int, user: UserDependency) -> None:
    with session() as db:
        row = db.scalar(
            select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user.id)
        )
        if row is None:
            raise HTTPException(404, "Token not found")
        row.revoked_at = datetime.now(UTC)
