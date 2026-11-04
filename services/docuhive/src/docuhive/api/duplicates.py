"""Possible duplicates: open pairs where the user can see both documents. Deciding never deletes
anything; trashing one of the two stays the user's own action.
"""

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Select, select

from docuhive import auth, db
from docuhive.auth import current_user
from docuhive.contracts import CurrentUser
from docuhive.db.models import Correspondent, Document, DuplicatePair

router = APIRouter(prefix="/api/duplicates", tags=["duplicates"])
UserDependency = Annotated[CurrentUser, Depends(current_user)]
Reason = Literal["same_sender", "same_amount", "close_date", "similar_content"]


class DuplicateSide(BaseModel):
    id: str
    title: str | None
    document_date: date | None
    correspondent: str | None


class DuplicateView(BaseModel):
    id: int
    score: float
    reasons: list[Reason]
    document: DuplicateSide
    other: DuplicateSide
    created_at: datetime


class DuplicateDecision(BaseModel):
    status: Literal["dismissed", "confirmed"]


def visible_pairs(user: CurrentUser) -> Select:
    ids = select(Document.id).where(auth.visible_docs(user), Document.status == "stored")
    return select(DuplicatePair).where(
        DuplicatePair.document_id.in_(ids), DuplicatePair.other_id.in_(ids)
    )


@router.get("", response_model=list[DuplicateView])
def list_duplicates(
    user: UserDependency, limit: int = Query(50, ge=1, le=200)
) -> list[DuplicateView]:
    with db.session() as session:
        pairs = list(
            session.scalars(
                visible_pairs(user)
                .where(DuplicatePair.status == "open")
                .order_by(DuplicatePair.score.desc(), DuplicatePair.id.desc())
                .limit(limit)
            )
        )
        ids = {p.document_id for p in pairs} | {p.other_id for p in pairs}
        sides = {
            r[0]: DuplicateSide(id=r[0], title=r[1], document_date=r[2], correspondent=r[3])
            for r in session.execute(
                select(Document.id, Document.title, Document.document_date, Correspondent.name)
                .outerjoin(Correspondent, Correspondent.id == Document.correspondent_id)
                .where(Document.id.in_(ids))
            )
        }
        return [
            DuplicateView(
                id=p.id,
                score=p.score,
                reasons=p.reasons,
                document=sides[p.document_id],
                other=sides[p.other_id],
                created_at=p.created_at,
            )
            for p in pairs
        ]


@router.post("/{pair_id}", status_code=204)
def decide(pair_id: int, body: DuplicateDecision, user: UserDependency) -> None:
    with db.session() as session:
        pair = session.scalar(
            visible_pairs(user).where(DuplicatePair.id == pair_id).with_for_update()
        )
        if pair is None:
            raise HTTPException(
                404,
                detail={
                    "code": "duplicate_not_found",
                    "message": "This pair is no longer waiting for a decision.",
                    "details": {},
                },
            )
        pair.status = body.status
        pair.resolved_at = datetime.now(UTC)
        pair.resolved_by = user.id
