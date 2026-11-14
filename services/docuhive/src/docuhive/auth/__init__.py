"""Sessions, scoped API tokens and FastAPI authorization dependencies."""

import hashlib
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select

from docuhive.config.settings import get_settings
from docuhive.contracts import CurrentUser
from docuhive.db import session
from docuhive.db.models import ApiToken, AuthSession, User

from .permissions import visible_docs, visible_docs_incl_trash  # noqa: F401

password_hasher = PasswordHasher()
_dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))
# "calendar" opens only the reminders feed, whose token travels in the URL.
SESSION_MAX_AGE = timedelta(days=90)
SCOPES = {"upload", "read", "write", "admin", "kb:read", "kb:ask", "calendar"}


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Use a password with at least 12 characters")
    return password_hasher.hash(password)


def verify_password(stored: str, password: str) -> bool:
    try:
        return password_hasher.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False


def check_csrf(request: Request) -> None:
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("x-docuhive-csrf") != "1":
            raise HTTPException(
                403, {"code": "csrf_required", "message": "Reload and try again.", "details": {}}
            )


def current_user(request: Request) -> CurrentUser:
    settings = get_settings()
    authorization = request.headers.get("authorization", "")
    now = datetime.now(UTC)
    request.state.token_id = None
    request.state.token_local_consumer = False
    if settings.env == "dev" and settings.auth_disabled:
        check_csrf(request)
        request.state.token_scopes = None
        return CurrentUser(id=1, username="dev", role="admin")
    with session() as db:
        user = None
        if authorization:
            scheme, _, raw = authorization.partition(" ")
            if scheme.lower() != "bearer" or not raw:
                raise HTTPException(401, "A valid Bearer token is required")
            token = db.scalar(
                select(ApiToken).where(
                    ApiToken.token_hash == token_hash(raw), ApiToken.revoked_at.is_(None)
                )
            )
            if token:
                user = db.get(User, token.user_id)
                request.state.token_scopes = set(token.scopes)
                request.state.token_id = token.id
                request.state.token_local_consumer = token.local_consumer
                if token.last_used_at is None or now - token.last_used_at >= timedelta(minutes=1):
                    token.last_used_at = now
        else:
            raw = request.cookies.get("dh_session", "")
            auth_session = db.get(AuthSession, token_hash(raw)) if raw else None
            if auth_session and auth_session.expires_at > now:
                user = db.get(User, auth_session.user_id)
                auth_session.last_seen_at = now
                if auth_session.expires_at - now < timedelta(days=15):
                    # Renewed while in use, but a stolen cookie cannot be kept alive for ever.
                    auth_session.expires_at = min(
                        now + timedelta(days=30), auth_session.created_at + SESSION_MAX_AGE
                    )
            check_csrf(request)
            request.state.token_scopes = None
        if user is None or user.pw_hash.startswith("!"):
            raise HTTPException(401, "Log in to continue")
        result = CurrentUser(id=user.id, username=user.username, role=user.role)
    # Default-deny routes that did not explicitly opt into token access.
    scopes = request.state.token_scopes
    if scopes is not None:
        path = request.url.path
        read = request.method in {"GET", "HEAD"} and (
            path.startswith("/api/documents") or path == "/api/search" or path == "/api/auth/me"
        )
        upload = request.method == "POST" and path == "/api/upload"
        write = path.startswith("/api/documents")
        kb_path = path == "/api/kb" or path.startswith("/api/kb/")
        kb_read = kb_path and request.method in {"GET", "HEAD"}
        kb_retrieve = kb_path and path.endswith("/retrieve") and request.method == "POST"
        kb_ask = kb_path and path.endswith("/ask") and request.method == "POST"
        allowed = (
            "admin" in scopes
            or (upload and "upload" in scopes)
            or (read and bool(scopes & {"read", "write"}))
            or (write and "write" in scopes)
            or (kb_read and bool(scopes & {"read", "write", "kb:read", "kb:ask"}))
            or (kb_retrieve and "kb:read" in scopes)
            or (kb_ask and "kb:ask" in scopes)
        )
        if not allowed:
            raise HTTPException(403, "This token does not permit this action")
    return result


def require_admin(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    if user.role != "admin":
        raise HTTPException(403, "Administrator access is required")
    return user


def scope(required: str) -> Callable:
    def dependency(
        request: Request, user: Annotated[CurrentUser, Depends(current_user)]
    ) -> CurrentUser:
        scopes = request.state.token_scopes
        accepted = {required, "admin"} | ({"write"} if required == "read" else set())
        if scopes is not None and not scopes & accepted:
            raise HTTPException(403, "This token does not permit this action")
        return user

    return dependency


def create_user(username: str, password: str, *, admin: bool = False) -> int:
    username = username.strip()
    if (
        not username
        or len(username) > 100
        or username in {".", ".."}
        or any(c.isspace() or not c.isprintable() or c in "/\\" for c in username)
    ):
        raise ValueError("Username must contain 1–100 characters without spaces or path separators")
    hashed = hash_password(password)
    with session() as db:
        user = User(username=username, pw_hash=hashed, role="admin" if admin else "member")
        db.add(user)
        db.flush()
        return user.id


def change_password(username: str, password: str | None) -> None:
    hashed = hash_password(password) if password is not None else "!disabled"
    with session() as db:
        user = db.scalar(select(User).where(User.username == username).with_for_update())
        if user is None:
            raise ValueError("User does not exist")
        user.pw_hash = hashed
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        for token in db.scalars(select(ApiToken).where(ApiToken.user_id == user.id)):
            token.revoked_at = datetime.now(UTC)
