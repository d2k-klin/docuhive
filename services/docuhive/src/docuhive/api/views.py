"""Saved views: named document filters pinned to the sidebar. Sharing shows the filter to the
household; each viewer still sees only the documents they may open.
"""

from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from docuhive import db, kb
from docuhive.auth import current_user
from docuhive.contracts import CurrentUser, SearchFilters
from docuhive.db.models import Correspondent, Document, DocumentTag, SavedView, Tag

from .knowledge import FilterScope

router = APIRouter(prefix="/api/views", tags=["saved views"])
UserDependency = Annotated[CurrentUser, Depends(current_user)]


class SavedViewInput(FilterScope):
    name: str = Field(min_length=1, max_length=100)
    pinned: bool = True
    shared: bool = False


class SavedViewPatch(FilterScope):
    name: str = Field(default="", min_length=1, max_length=100)
    pinned: bool = True
    shared: bool = False


class SavedViewView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    filters: SearchFilters
    owner_id: int
    pinned: bool
    shared: bool
    created_at: datetime
    updated_at: datetime


class DocumentRow(BaseModel):
    id: str
    title: str | None
    document_date: date | None
    category: str | None
    document_type: str | None
    correspondent: str | None
    tags: list[str]
    added_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentRow]
    total: int
    next_offset: int | None


def problem(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, "details": {}})


def visible(user: CurrentUser):  # type: ignore[no-untyped-def]
    return or_(SavedView.owner_id == user.id, SavedView.shared.is_(True))


def find(session: Session, user: CurrentUser, view_id: int, *, owner: bool = False) -> SavedView:
    statement = select(SavedView).where(SavedView.id == view_id, visible(user))
    row = session.scalar(statement.with_for_update() if owner else statement)
    if row is None:
        raise problem(404, "view_not_found", "Saved view not found.")
    if owner and row.owner_id != user.id:
        raise problem(403, "view_owner_required", "Only the owner can change this view.")
    return row


def document_page(
    user: CurrentUser, filters: SearchFilters, limit: int, offset: int
) -> DocumentPage:
    scope = kb.document_scope(user, filters).subquery()
    with db.session() as session:
        total = session.scalar(select(func.count()).select_from(scope)) or 0
        rows = session.execute(
            select(
                Document.id,
                Document.title,
                Document.document_date,
                Document.category,
                Document.document_type,
                Correspondent.name,
                Document.added_at,
            )
            .outerjoin(Correspondent, Correspondent.id == Document.correspondent_id)
            .where(Document.id.in_(select(scope.c.id)))
            .order_by(
                func.coalesce(Document.document_date, func.date(Document.added_at)).desc(),
                Document.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        ).all()
        tags: dict[str, list[str]] = {}
        for doc_id, name in session.execute(
            select(DocumentTag.document_id, Tag.name)
            .join(Tag, Tag.id == DocumentTag.tag_id)
            .where(DocumentTag.document_id.in_([r[0] for r in rows]))
            .order_by(Tag.name)
        ):
            tags.setdefault(doc_id, []).append(name)
    return DocumentPage(
        items=[
            DocumentRow(
                id=r[0],
                title=r[1],
                document_date=r[2],
                category=r[3],
                document_type=r[4],
                correspondent=r[5],
                tags=tags.get(r[0], []),
                added_at=r[6],
            )
            for r in rows
        ],
        total=total,
        next_offset=offset + limit if offset + limit < total else None,
    )


@router.get("", response_model=list[SavedViewView])
def list_views(user: UserDependency) -> list[SavedViewView]:
    with db.session() as session:
        rows = session.scalars(select(SavedView).where(visible(user)).order_by(SavedView.name))
        return [SavedViewView.model_validate(row) for row in rows]


@router.post("", response_model=SavedViewView, status_code=201)
def create_view(body: SavedViewInput, user: UserDependency) -> SavedViewView:
    with db.session() as session:
        kb.validate_filters(session, user, body.filters)
        row = SavedView(**body.model_dump(mode="json"), owner_id=user.id)
        session.add(row)
        session.flush()
        return SavedViewView.model_validate(row)


@router.get("/{view_id}", response_model=SavedViewView)
def get_view(view_id: int, user: UserDependency) -> SavedViewView:
    with db.session() as session:
        return SavedViewView.model_validate(find(session, user, view_id))


@router.patch("/{view_id}", response_model=SavedViewView)
def edit_view(view_id: int, body: SavedViewPatch, user: UserDependency) -> SavedViewView:
    with db.session() as session:
        row = find(session, user, view_id, owner=True)
        if "filters" in body.model_fields_set:
            kb.validate_filters(session, user, body.filters)
        for key, value in body.model_dump(mode="json", exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_at = datetime.now(UTC)
        session.flush()
        return SavedViewView.model_validate(row)


@router.delete("/{view_id}", status_code=204)
def delete_view(view_id: int, user: UserDependency) -> None:
    with db.session() as session:
        session.delete(find(session, user, view_id, owner=True))


@router.get("/{view_id}/documents", response_model=DocumentPage)
def view_documents(
    view_id: int,
    user: UserDependency,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100_000),
) -> DocumentPage:
    with db.session() as session:
        filters = SearchFilters.model_validate(find(session, user, view_id).filters)
    return document_page(user, filters, limit, offset)
