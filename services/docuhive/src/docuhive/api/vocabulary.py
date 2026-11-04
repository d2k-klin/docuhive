"""Tags and senders: list with typeahead for everyone; rename and merge for administrators,
because both change documents that other members own.
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from docuhive import auth, db
from docuhive.auth import current_user, require_admin
from docuhive.contracts import CurrentUser
from docuhive.db.models import Correspondent, Document, DocumentTag, Tag
from docuhive.documents import vocabulary

from .views import problem

router = APIRouter(prefix="/api/vocabulary", tags=["vocabulary"])
UserDependency = Annotated[CurrentUser, Depends(current_user)]
AdminDependency = Annotated[CurrentUser, Depends(require_admin)]
KindPath = Literal["tags", "correspondents"]


class VocabularyItem(BaseModel):
    id: int
    name: str
    documents: int  # documents you can see


class Rename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class Merge(BaseModel):
    source_ids: list[int] = Field(min_length=1, max_length=100)
    target_id: int


class Changed(BaseModel):
    documents: int


def singular(kind: KindPath) -> vocabulary.Kind:
    return "tag" if kind == "tags" else "correspondent"


@router.get("/{kind}", response_model=list[VocabularyItem])
def list_items(
    kind: KindPath,
    user: UserDependency,
    q: str = Query("", max_length=100),
    limit: int = Query(200, ge=1, le=1000),
) -> list[VocabularyItem]:
    model = Tag if kind == "tags" else Correspondent
    visible = select(Document.id).where(auth.visible_docs(user)).scalar_subquery()
    counts: Any
    if kind == "tags":
        counts = (
            select(DocumentTag.tag_id.label("item"), func.count().label("n"))
            .where(DocumentTag.document_id.in_(visible))
            .group_by(DocumentTag.tag_id)
        )
    else:
        counts = (
            select(Document.correspondent_id.label("item"), func.count().label("n"))
            .where(Document.id.in_(visible))
            .group_by(Document.correspondent_id)
        )
    sub = counts.subquery()
    query = (
        select(model.id, model.name, func.coalesce(sub.c.n, 0))
        .outerjoin(sub, sub.c.item == model.id)
        .where(model.merged_into.is_(None))
        .order_by(func.coalesce(sub.c.n, 0).desc(), model.name)
        .limit(limit)
    )
    if q.strip():
        query = query.where(model.name.ilike(f"%{q.strip()}%"))
    with db.session() as session:
        rows = session.execute(query).all()
    return [VocabularyItem(id=r[0], name=r[1], documents=r[2]) for r in rows]


@router.patch("/{kind}/{item_id}", response_model=Changed)
def rename_item(kind: KindPath, item_id: int, body: Rename, user: AdminDependency) -> Changed:
    try:
        ids = vocabulary.rename(singular(kind), item_id, body.name, actor=f"user:{user.id}")
    except vocabulary.VocabularyError as error:
        raise problem(409, "vocabulary_conflict", str(error)) from error
    return Changed(documents=len(ids))


@router.post("/{kind}/merge", response_model=Changed)
def merge_items(kind: KindPath, body: Merge, user: AdminDependency) -> Changed:
    try:
        ids = vocabulary.merge(
            singular(kind), body.source_ids, body.target_id, actor=f"user:{user.id}"
        )
    except vocabulary.VocabularyError as error:
        raise problem(409, "vocabulary_conflict", str(error)) from error
    return Changed(documents=len(ids))
