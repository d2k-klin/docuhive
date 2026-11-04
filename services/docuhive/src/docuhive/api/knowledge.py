"""Knowledge-base management; retrieval and answer routes are registered separately."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from docuhive import db, kb, taxonomy
from docuhive.auth import current_user
from docuhive.contracts import CurrentUser, KnowledgeBaseView, SearchFilters, Taxonomy
from docuhive.db.models import KnowledgeBase

router = APIRouter(prefix="/api/kb", tags=["knowledge bases"])
UserDependency = Annotated[CurrentUser, Depends(current_user)]


class KnowledgeBaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    shared: bool = False
    local_only: bool = True

    @field_validator("filters", mode="before")
    @classmethod
    def bounded_filters(cls, value: Any) -> Any:
        if isinstance(value, dict):
            if value.keys() - SearchFilters.model_fields.keys():
                raise ValueError("Unknown document filter")
            for entry in value.values():
                if isinstance(entry, list) and (
                    len(entry) > 500
                    or any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in entry)
                ):
                    raise ValueError("Choose at most 500 non-empty values per filter")
        return value


class KnowledgeBasePatch(KnowledgeBaseInput):
    # PATCH preserves omitted fields. Explicit nulls are rejected by the inherited types.
    name: str = Field(default="", max_length=100)

    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value: str) -> str:
        if not value:
            raise ValueError("Enter a name")
        return value


class KnowledgeBaseList(BaseModel):
    items: list[KnowledgeBaseView]
    next_cursor: str | None


class KnowledgeBaseSuggestion(BaseModel):
    name: str
    filters: SearchFilters


@router.get("", response_model=KnowledgeBaseList)
def list_bases(
    user: UserDependency,
    limit: int = Query(50, ge=1, le=100),
    cursor: int | None = Query(None, ge=1),
) -> KnowledgeBaseList:
    with db.session() as session:
        statement = (
            select(KnowledgeBase)
            .where(kb.visible(user))
            .order_by(KnowledgeBase.id)
            .limit(limit + 1)
        )
        if cursor is not None:
            statement = statement.where(KnowledgeBase.id > cursor)
        rows = list(session.scalars(statement))
        return KnowledgeBaseList(
            items=[kb.view(row) for row in rows[:limit]],
            next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
        )


@router.get("/suggestions", response_model=list[KnowledgeBaseSuggestion])
def suggest_bases(user: UserDependency) -> list[dict]:
    return kb.suggestions(user)


@router.post("", response_model=KnowledgeBaseView, status_code=201)
def create_base(body: KnowledgeBaseInput, user: UserDependency) -> KnowledgeBaseView:
    with db.session() as session:
        kb.validate_filters(session, user, body.filters)
        row = KnowledgeBase(**body.model_dump(mode="json"), owner_id=user.id)
        session.add(row)
        session.flush()
        return kb.view(row)


@router.get("/options", response_model=Taxonomy)
def filter_options(user: UserDependency) -> Taxonomy:
    with db.session() as session:
        return taxonomy.load().model_copy(update={"tags": sorted(kb.known_tags(session, user))})


@router.get("/{kb_id}", response_model=KnowledgeBaseView)
def get_base(kb_id: int, user: UserDependency) -> KnowledgeBaseView:
    return kb.get(user, kb_id)


@router.get("/{kb_id}/status", response_model=kb.KnowledgeBaseStatus)
def base_status(kb_id: int, user: UserDependency) -> kb.KnowledgeBaseStatus:
    return kb.status(user, kb_id)


def owned(session: Session, user: CurrentUser, kb_id: int) -> KnowledgeBase:
    row = session.scalar(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, kb.visible(user)).with_for_update()
    )
    if row is None:
        raise HTTPException(
            404,
            detail={"code": "kb_not_found", "message": "Knowledge base not found", "details": {}},
        )
    if row.owner_id != user.id:
        raise HTTPException(
            403,
            detail={
                "code": "kb_owner_required",
                "message": "Only the owner can change this knowledge base",
                "details": {},
            },
        )
    return row


@router.patch("/{kb_id}", response_model=KnowledgeBaseView)
def edit_base(kb_id: int, body: KnowledgeBasePatch, user: UserDependency) -> KnowledgeBaseView:
    with db.session() as session:
        row = owned(session, user, kb_id)
        if "filters" in body.model_fields_set:
            kb.validate_filters(session, user, body.filters)
        for field, value in body.model_dump(mode="json", exclude_unset=True).items():
            setattr(row, field, value)
        row.updated_at = datetime.now(UTC)
        session.flush()
        return kb.view(row)


@router.delete("/{kb_id}", status_code=204)
def delete_base(kb_id: int, user: UserDependency) -> None:
    with db.session() as session:
        session.delete(owned(session, user, kb_id))
