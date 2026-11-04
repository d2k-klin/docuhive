"""The single document visibility rule, including for administrators."""

from sqlalchemy import ColumnElement, and_, or_

from docuhive.contracts import CurrentUser
from docuhive.db.models import Document


def visible_docs_incl_trash(user: CurrentUser) -> ColumnElement[bool]:
    return or_(Document.owner_id == user.id, Document.shared.is_(True))


def visible_docs(user: CurrentUser) -> ColumnElement[bool]:
    return and_(visible_docs_incl_trash(user), Document.deleted_at.is_(None))
