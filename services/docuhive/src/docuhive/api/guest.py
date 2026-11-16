"""Guest links: made by a signed-in person; opened by anyone holding the link, read-only."""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from docuhive import db, guest_links, vault
from docuhive import documents as core
from docuhive.auth import current_user
from docuhive.auth.rate_limit import LoginLimiter
from docuhive.contracts import CurrentUser
from docuhive.db.models import Document

from .views import problem

router = APIRouter(tags=["guest links"])
UserDep = Annotated[CurrentUser, Depends(current_user)]
limiter = LoginLimiter()  # wrong tokens count like failed logins: 5 per address per 15 minutes


class NewLink(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    document_ids: list[str] = Field(min_length=1, max_length=200)
    days: int = Field(default=7, ge=1, le=guest_links.MAX_DAYS)
    include_private: bool = False


class LinkOut(BaseModel):
    id: int
    label: str
    documents: int
    expires_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None


class Created(LinkOut):
    path: str  # shown once: "/guest/<token>"


class GuestDocument(BaseModel):
    id: str
    title: str | None
    document_date: date | None
    pages: int | None


class GuestPage(BaseModel):
    label: str
    expires_at: datetime
    documents: list[GuestDocument]


def _out(link) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": link.id,
        "label": link.label,
        "documents": len(link.document_ids),
        "expires_at": link.expires_at,
        "revoked_at": link.revoked_at,
        "last_used_at": link.last_used_at,
    }


@router.post("/api/guest-links", response_model=Created, status_code=201)
def create_link(body: NewLink, user: UserDep) -> Created:
    try:
        link, token = guest_links.create(
            user, body.label, body.document_ids, body.days, include_private=body.include_private
        )
    except guest_links.Disabled as error:
        raise problem(403, "guest_links_off", "Guest links are switched off here.") from error
    except core.NotFound as error:
        raise problem(404, "document_not_found", "One of the documents is not yours.") from error
    except guest_links.NeedsConfirmation as error:
        raise problem(
            409,
            "confirm_private",
            "Some of these documents are private. Confirm to share them too.",
            {"document_ids": error.ids},
        ) from error
    return Created(**_out(link), path=f"/guest/{token}")


@router.get("/api/guest-links", response_model=list[LinkOut])
def list_links(user: UserDep) -> list[LinkOut]:
    return [LinkOut(**_out(link)) for link in guest_links.mine(user)]


@router.post("/api/guest-links/{link_id}/revoke", status_code=204)
def revoke_link(link_id: int, user: UserDep) -> None:
    try:
        guest_links.revoke(user, link_id)
    except LookupError as error:
        raise problem(404, "guest_link_not_found", "No such link.") from error


def _opened(token: str, request: Request):  # type: ignore[no-untyped-def]
    ip = request.client.host if request.client else "unknown"
    if not limiter.allowed(f"guest:{ip}", ip):
        raise problem(429, "rate_limited", "Try again in 15 minutes.")
    opened = guest_links.open_link(token)
    if opened is None:
        limiter.failed(f"guest:{ip}", ip)
        raise problem(404, "guest_link_not_found", "This link has expired or does not exist.")
    return opened


@router.get("/api/guest/{token}", response_model=GuestPage)
def guest_page(token: str, request: Request) -> GuestPage:
    link, docs = _opened(token, request)
    for doc in docs:
        guest_links.log_view(link, doc.id, "list")
    return GuestPage(
        label=link.label,
        expires_at=link.expires_at,
        documents=[
            GuestDocument(id=d.id, title=d.title, document_date=d.document_date, pages=d.pages)
            for d in docs
        ],
    )


@router.get("/api/guest/{token}/documents/{doc_id}/file")
def guest_file(token: str, doc_id: str, request: Request, download: bool = False) -> FileResponse:
    """The archive PDF only: originals can be HTML or mail, which must not open here."""
    link, docs = _opened(token, request)
    view = next((d for d in docs if d.id == doc_id), None)
    if view is None:
        raise problem(404, "document_not_found", "This document is not part of the link.")
    with db.session() as s:
        vault_path = s.scalar(select(Document.vault_path).where(Document.id == doc_id))
    root = vault.root().resolve()
    path = (root / vault_path / "archive.pdf").resolve() if vault_path else None
    if path is None or not path.is_relative_to(root) or not path.is_file():
        raise problem(404, "document_file_missing", "This file is not in the vault.")
    guest_links.log_view(link, doc_id, "download" if download else "view")
    name = Path(view.source.original_filename or "document").stem or "document"
    return FileResponse(
        path,
        filename=f"{name}.pdf",
        content_disposition_type="attachment" if download else "inline",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )
