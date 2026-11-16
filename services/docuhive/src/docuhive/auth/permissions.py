"""The single document visibility rule, including for administrators."""

from sqlalchemy import ColumnElement, and_, or_

from docuhive.contracts import CurrentUser
from docuhive.db.models import Document

BOOKKEEPER_CATEGORIES = "roles.bookkeeper.categories"


def visible_docs_incl_trash(user: CurrentUser) -> ColumnElement[bool]:
    """Your own and the household's shared documents. A bookkeeper also sees the categories an
    administrator assigned to the role (off until assigned: then a bookkeeper is a member)."""
    rule = or_(Document.owner_id == user.id, Document.shared.is_(True))
    if user.role != "bookkeeper":
        return rule
    from docuhive.config import get_setting

    categories = [str(c) for c in get_setting(BOOKKEEPER_CATEGORIES) or [] if c]
    if not categories:
        return rule
    return or_(
        rule,
        Document.category.in_(categories),
        *(Document.category.startswith(f"{c}/") for c in categories),
    )


def visible_docs(user: CurrentUser) -> ColumnElement[bool]:
    return and_(visible_docs_incl_trash(user), Document.deleted_at.is_(None))
