"""OAuth 2 authorization-code + PKCE for Gmail and Microsoft Graph, via plain httpx.

Refresh tokens are stored Fernet-encrypted in mail_accounts.enc_credentials. Access tokens
live only in memory (per account, until expiry - 60 s).
"""

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from sqlalchemy import select

from docuhive import db
from docuhive.mail.base import NeedsReauth
from docuhive.mail.models import MailAccount
from docuhive.mail.settings import fernet, get_mail_settings

STATE_TTL_S = 600


def _endpoints(name: str) -> dict:
    if name == "google":
        return {
            "auth": "https://accounts.google.com/o/oauth2/v2/auth",
            "token": "https://oauth2.googleapis.com/token",
            "provider": "gmail",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
            "modify": "https://www.googleapis.com/auth/gmail.modify",
            "extra": {"access_type": "offline", "prompt": "consent"},
        }
    tenant = get_mail_settings().ms_tenant
    base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
    return {
        "auth": f"{base}/authorize",
        "token": f"{base}/token",
        "provider": "graph",
        "scopes": ["Mail.Read", "offline_access", "User.Read"],
        "modify": "Mail.ReadWrite",
        "extra": {"prompt": "select_account"},
    }


def _client(name: str) -> tuple[str, str]:
    s = get_mail_settings()
    cid, secret = (
        (s.google_client_id, s.google_client_secret)
        if name == "google"
        else (s.ms_client_id, s.ms_client_secret)
    )
    if not cid or not secret:
        prefix = "GOOGLE" if name == "google" else "MS"
        raise LookupError(
            f"Set DOCUHIVE_MAIL_{prefix}_CLIENT_ID and _CLIENT_SECRET first "
            "(see docs/setup/mail-accounts.md)"
        )
    return cid, secret.get_secret_value()


def redirect_uri(name: str) -> str:
    from docuhive.config.settings import get_settings

    return f"{get_settings().public_url.rstrip('/')}/api/sources/oauth/{name}/callback"


@dataclass
class _State:
    user_id: int
    verifier: str
    label_on_import: bool
    expires: float


# ponytail: in-memory state store (one API process). Move to the DB if the API is scaled out.
_STATES: dict[str, _State] = {}


def start_url(name: str, user_id: int, label_on_import: bool = False) -> str:
    cid, _ = _client(name)
    ep = _endpoints(name)
    now = time.time()
    for k in [k for k, v in _STATES.items() if v.expires < now]:
        del _STATES[k]
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    _STATES[state] = _State(user_id, verifier, label_on_import, now + STATE_TTL_S)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    scopes = ep["scopes"] + ([ep["modify"]] if label_on_import else [])
    return (
        ep["auth"]
        + "?"
        + urlencode(
            {
                "client_id": cid,
                "redirect_uri": redirect_uri(name),
                "response_type": "code",
                "scope": " ".join(scopes),
                "state": state,
                "code_challenge": challenge.decode(),
                "code_challenge_method": "S256",
                **ep["extra"],
            }
        )
    )


def _post_token(name: str, data: dict, client: httpx.Client | None) -> dict:
    cid, secret = _client(name)
    c = client or httpx.Client(timeout=30)
    r = c.post(_endpoints(name)["token"], data=data | {"client_id": cid, "client_secret": secret})
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code >= 400:
        if body.get("error") == "invalid_grant":
            raise NeedsReauth(body.get("error_description", "invalid_grant"))
        raise RuntimeError(f"token endpoint HTTP {r.status_code}: {body.get('error', '')}")
    return body


def _address(name: str, access_token: str, client: httpx.Client | None) -> tuple[str, str | None]:
    c = client or httpx.Client(timeout=30)
    h = {"Authorization": f"Bearer {access_token}"}
    if name == "google":
        r = c.get("https://gmail.googleapis.com/gmail/v1/users/me/profile", headers=h)
        r.raise_for_status()
        return r.json()["emailAddress"], None
    r = c.get("https://graph.microsoft.com/v1.0/me", headers=h)
    r.raise_for_status()
    me = r.json()
    return me.get("mail") or me["userPrincipalName"], me.get("displayName")


def callback(
    name: str, code: str, state: str, user_id: int, client: httpx.Client | None = None
) -> int:
    """Verify state, exchange the code, store the encrypted refresh token. Returns account id."""
    st = _STATES.pop(state, None)
    if st is None or st.expires < time.time() or st.user_id != user_id:
        raise PermissionError("This sign-in link expired or belongs to someone else. Try again.")
    tokens = _post_token(
        name,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(name),
            "code_verifier": st.verifier,
        },
        client,
    )
    if not tokens.get("refresh_token"):
        raise RuntimeError("The provider returned no refresh token (offline access missing)")
    address, display = _address(name, tokens["access_token"], client)
    provider = _endpoints(name)["provider"]
    blob = fernet().encrypt(json.dumps({"refresh_token": tokens["refresh_token"]}).encode())
    with db.session() as s:
        acc = s.scalar(
            select(MailAccount).where(
                MailAccount.provider == provider, MailAccount.address == address.lower()
            )
        )
        if acc and acc.owner_id != user_id:
            raise PermissionError("This mailbox is already connected by another user")
        if acc is None:
            acc = MailAccount(
                owner_id=user_id, provider=provider, address=address.lower(), sync_cursor={}
            )
            s.add(acc)
        acc.display_name = acc.display_name or display
        acc.enc_credentials, acc.status = blob, "active"
        acc.label_on_import = st.label_on_import
        s.flush()
        _CACHE.pop(acc.id, None)
        return acc.id


_CACHE: dict[int, tuple[str, float]] = {}


def access_token(account_id: int, client: httpx.Client | None = None) -> str:
    """Cached access token; refreshes it. invalid_grant -> needs_reauth + notification."""
    hit = _CACHE.get(account_id)
    if hit and hit[1] > time.time():
        return hit[0]
    with db.session() as s:
        acc = s.get(MailAccount, account_id)
        if acc is None:
            raise LookupError(account_id)
        name = "google" if acc.provider == "gmail" else "microsoft"
        creds = json.loads(fernet().decrypt(acc.enc_credentials))
        owner, address = acc.owner_id, acc.address
    try:
        tokens = _post_token(
            name, {"grant_type": "refresh_token", "refresh_token": creds["refresh_token"]}, client
        )
    except NeedsReauth:
        mark_needs_reauth(account_id, owner, address)
        raise
    if tokens.get("refresh_token") and tokens["refresh_token"] != creds["refresh_token"]:
        with db.session() as s:  # Microsoft rotates refresh tokens
            s.get_one(MailAccount, account_id).enc_credentials = fernet().encrypt(
                json.dumps(creds | {"refresh_token": tokens["refresh_token"]}).encode()
            )
    _CACHE[account_id] = (
        tokens["access_token"],
        time.time() + int(tokens.get("expires_in", 3600)) - 60,
    )
    return tokens["access_token"]


def mark_needs_reauth(account_id: int, owner_id: int, address: str) -> None:
    from docuhive.notify import Notification, send

    with db.session() as s:
        s.get_one(MailAccount, account_id).status = "needs_reauth"
    send(
        Notification(
            kind="mail_reauth",
            title=f"Reconnect {address}",
            body="DocuHive can no longer read this mailbox. Reconnect it to resume "
            "importing documents.",
            url="/sources",
            priority="high",
            user_id=owner_id,
        )
    )
