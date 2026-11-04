"""Small HTTP helpers shared by CL routers (error format and auth deps per contracts §6)."""

from typing import Annotated, Any, NoReturn

from fastapi import Depends, HTTPException

from docuhive import auth
from docuhive.contracts import CurrentUser, DocumentView

User = Annotated[CurrentUser, Depends(auth.current_user)]
Admin = Annotated[CurrentUser, Depends(auth.require_admin)]


def fail(status: int, code: str, message: str, **details: Any) -> NoReturn:
    raise HTTPException(status, {"code": code, "message": message, "details": details})


def summary(v: DocumentView) -> dict:
    """The compact document shape CL lists use (review queue, similar documents, citations)."""
    return {
        "id": v.id,
        "title": v.title,
        "category": v.category,
        "document_type": v.document_type,
        "correspondent": v.correspondent,
        "document_date": v.document_date,
        "added_at": v.added_at,
        "owner_id": v.owner_id,
        "thumbnail_url": f"/api/documents/{v.id}/thumbnail",
    }


def page(items: list, limit: int, offset: int) -> dict:
    """Cursor pagination over an offset (the cursor is opaque to clients)."""
    more = len(items) > limit
    return {"items": items[:limit], "next_cursor": str(offset + limit) if more else None}
