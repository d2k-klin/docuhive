"""Release schema upgrade on disposable PostgreSQL; no target-hardware claim."""

import pytest
from alembic import command
from docuhive import db
from docuhive.db.migrations import migrate, migration_config
from sqlalchemy import text


@pytest.mark.integration
@pytest.mark.req("NFR-03")
def test_release_010_to_current_preserves_documents_and_credentials(postgres):
    # v0.1.0 shipped core 0001 + intel 0008. This database is disposable (_test only).
    command.downgrade(migration_config("intel"), "0008_reminders")
    command.downgrade(migration_config("core"), "0001_core")
    with db.session() as session:
        session.execute(
            text(
                "INSERT INTO users (id, username, pw_hash, role) "
                "VALUES (10, 'synthetic', 'synthetic-hash', 'member')"
            )
        )
        session.execute(
            text(
                "INSERT INTO documents (id, owner_id, status, sha256, mime, title, manual_fields) "
                "VALUES ('upgrade-document', 10, 'stored', 'synthetic-sha', 'application/pdf', "
                "'Preserved title', ARRAY['title'])"
            )
        )
        session.execute(
            text(
                "INSERT INTO doc_sources (document_id, kind, original_filename) "
                "VALUES ('upgrade-document', 'upload', 'synthetic.pdf')"
            )
        )
        session.execute(
            text(
                "INSERT INTO doc_facts (document_id, field, type, value_text, value_num, currency) "
                "VALUES ('upgrade-document', 'amount_total', 'money', '84.20', 84.20, 'EUR')"
            )
        )
        session.execute(
            text(
                "INSERT INTO api_tokens (user_id, name, token_hash, prefix, scopes) "
                "VALUES (10, 'scanner', 'synthetic-token-hash', 'synthetic', ARRAY['upload'])"
            )
        )
    migrate("upgrade")
    migrate("upgrade")  # The deployment can safely rerun migrations.
    with db.session() as session:
        assert session.execute(
            text("SELECT title, manual_fields FROM documents WHERE id='upgrade-document'")
        ).one() == ("Preserved title", ["title"])
        assert session.scalar(text("SELECT pw_hash FROM users WHERE id=10")) == "synthetic-hash"
        assert (
            session.scalar(
                text("SELECT value_text FROM doc_facts WHERE document_id='upgrade-document'")
            )
            == "84.20"
        )
        assert session.execute(
            text("SELECT scopes, local_consumer FROM api_tokens WHERE user_id=10")
        ).one() == (["upload"], False)
        assert (
            session.scalar(text("SELECT version_num FROM alembic_version_core"))
            == "0003_archive_tools"
        )
