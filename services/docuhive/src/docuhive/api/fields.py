"""Custom fields. Everyone signed in can read them; only admins define them, because they shape
extraction for the whole household. Name and type are fixed once created: extracted values are
stored under the name.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from docuhive import db, taxonomy
from docuhive.auth import current_user, require_admin
from docuhive.contracts import CurrentUser, FactType
from docuhive.db.models import CustomField

router = APIRouter(prefix="/api/custom-fields", tags=["custom fields"])
UserDependency = Annotated[CurrentUser, Depends(current_user)]
Admin = Annotated[CurrentUser, Depends(require_admin)]


class CustomFieldPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    label: str = Field(default="", min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    document_types: list[str] = Field(default_factory=list, max_length=50)
    remind_days_before: list[Annotated[int, Field(ge=1, le=365)]] = Field(
        default_factory=list, max_length=5
    )


class CustomFieldInput(CustomFieldPatch):
    name: str = Field(min_length=1, max_length=60, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=100)
    type: FactType


class CustomFieldView(CustomFieldInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


def problem(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, "details": {}})


def check(session: Session, name: str, kind: str, body: CustomFieldPatch, own_id: int = 0) -> None:
    types = {t.id: t for t in taxonomy.load().document_types}
    if set(body.document_types) - types.keys():
        raise problem(422, "field_unknown_type", "Choose document types from the current list.")
    if body.remind_days_before and kind != "date":
        raise problem(422, "field_reminder_needs_date", "Only date fields can have reminders.")
    applies = [types[t] for t in body.document_types] or list(types.values())
    if any(name == f.name for t in applies for f in t.facts):
        raise problem(409, "field_name_builtin", "A built-in field already uses this name.")
    taken = session.scalar(select(CustomField.id).where(CustomField.name == name))
    if taken is not None and taken != own_id:
        raise problem(409, "field_name_taken", "Another custom field already uses this name.")


def find(session: Session, field_id: int) -> CustomField:
    row = session.get(CustomField, field_id, with_for_update=True)
    if row is None:
        raise problem(404, "field_not_found", "Custom field not found.")
    return row


@router.get("", response_model=list[CustomFieldView])
def list_fields(user: UserDependency) -> list[CustomFieldView]:
    with db.session() as session:
        rows = session.scalars(select(CustomField).order_by(CustomField.label))
        return [CustomFieldView.model_validate(row) for row in rows]


@router.post("", response_model=CustomFieldView, status_code=201)
def create_field(body: CustomFieldInput, user: Admin) -> CustomFieldView:
    with db.session() as session:
        check(session, body.name, body.type, body)
        row = CustomField(**body.model_dump())
        session.add(row)
        session.flush()
        return CustomFieldView.model_validate(row)


@router.patch("/{field_id}", response_model=CustomFieldView)
def edit_field(field_id: int, body: CustomFieldPatch, user: Admin) -> CustomFieldView:
    with db.session() as session:
        row = find(session, field_id)
        merged = CustomFieldPatch.model_validate(
            {
                "label": row.label,
                "description": row.description,
                "document_types": row.document_types,
                "remind_days_before": row.remind_days_before,
            }
            | body.model_dump(exclude_unset=True)
        )
        check(session, row.name, row.type, merged, own_id=row.id)
        for key, value in merged.model_dump().items():
            setattr(row, key, value)
        row.updated_at = datetime.now(UTC)
        session.flush()
        return CustomFieldView.model_validate(row)


@router.delete("/{field_id}", status_code=204)
def delete_field(field_id: int, user: Admin) -> None:
    # Values already extracted stay on their documents; only future extraction stops.
    with db.session() as session:
        session.delete(find(session, field_id))
