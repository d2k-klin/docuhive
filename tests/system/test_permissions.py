"""Evaluate the real visibility predicates on SQL rows, including administrator isolation."""

import pytest
from docuhive.auth import visible_docs, visible_docs_incl_trash
from docuhive.contracts import CurrentUser
from docuhive.db.models import Document
from sqlalchemy import create_engine, select, text


@pytest.mark.req("AUTH-03", "QA-06")
@pytest.mark.parametrize("role", ["admin", "member"])
@pytest.mark.parametrize("owner", [True, False])
@pytest.mark.parametrize("shared", [True, False])
@pytest.mark.parametrize("trashed", [True, False])
def test_real_visibility_sql_applies_the_same_rule_to_admins(role, owner, shared, trashed):
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE documents "
                    "(id TEXT, owner_id INTEGER, shared BOOLEAN, deleted_at TEXT)"
                )
            )
            connection.execute(
                text("INSERT INTO documents VALUES ('qa-document', 1, :shared, :deleted)"),
                {"shared": shared, "deleted": "2026-11-04" if trashed else None},
            )
            user = CurrentUser(id=1 if owner else 2, username="qa", role=role)
            assert bool(connection.scalar(select(Document.id).where(visible_docs(user)))) is (
                (owner or shared) and not trashed
            )
            assert bool(
                connection.scalar(select(Document.id).where(visible_docs_incl_trash(user)))
            ) is (owner or shared)
    finally:
        engine.dispose()
