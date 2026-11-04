"""Core baseline: extensions, unaccented FTS configurations and OA tables.

DDL is frozen here; future ORM changes require a new revision.
"""

from alembic import op

revision = "0001_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE EXTENSION IF NOT EXISTS unaccent
    """)
    op.execute("""
CREATE EXTENSION IF NOT EXISTS pg_trgm
    """)
    op.execute("""
CREATE EXTENSION IF NOT EXISTS vector
    """)
    op.execute("""
CREATE TEXT SEARCH CONFIGURATION dh_simple (COPY = simple)
    """)
    op.execute("""
ALTER TEXT SEARCH CONFIGURATION dh_simple ALTER MAPPING FOR hword, hword_part, word WITH
unaccent, simple
    """)
    op.execute("""
CREATE TEXT SEARCH CONFIGURATION dh_german (COPY = german)
    """)
    op.execute("""
ALTER TEXT SEARCH CONFIGURATION dh_german ALTER MAPPING FOR hword, hword_part, word WITH
unaccent, german_stem
    """)
    op.execute("""
CREATE TEXT SEARCH CONFIGURATION dh_english (COPY = english)
    """)
    op.execute("""
ALTER TEXT SEARCH CONFIGURATION dh_english ALTER MAPPING FOR hword, hword_part, word WITH
unaccent, english_stem
    """)
    op.execute("""
CREATE TABLE users (
        id BIGSERIAL NOT NULL, 
        username TEXT NOT NULL,
pw_hash TEXT NOT NULL, 
        role TEXT NOT NULL, 
        created_at TIMESTAMP WITH TIME ZONE
DEFAULT now() NOT NULL, 
        PRIMARY KEY (id), 
        CHECK (role IN ('admin','member')),
UNIQUE (username)
)
    """)
    op.execute("""
CREATE TABLE correspondents (
        id BIGSERIAL NOT NULL, 
        name TEXT NOT NULL,
norm_name TEXT NOT NULL, 
        merged_into BIGINT, 
        PRIMARY KEY (id), 
        UNIQUE
(norm_name)
)
    """)
    op.execute("""
CREATE INDEX correspondents_trgm ON correspondents USING gin (name gin_trgm_ops)
    """)
    op.execute("""
CREATE TABLE tags (
        id BIGSERIAL NOT NULL, 
        name TEXT NOT NULL, 
        slug
TEXT NOT NULL, 
        merged_into BIGINT, 
        PRIMARY KEY (id), 
        UNIQUE (slug)
)
    """)
    op.execute("""
CREATE TABLE audit_log (
        id BIGSERIAL NOT NULL, 
        at TIMESTAMP WITH TIME ZONE
DEFAULT now() NOT NULL, 
        actor TEXT NOT NULL, 
        document_id TEXT, 
        action
TEXT NOT NULL, 
        before JSONB, 
        after JSONB, 
        PRIMARY KEY (id)
)
    """)
    op.execute("""
CREATE TABLE jobs (
        id BIGSERIAL NOT NULL, 
        kind TEXT NOT NULL, 
        queue
TEXT DEFAULT 'default' NOT NULL, 
        payload JSONB DEFAULT '{}' NOT NULL, 
        status
TEXT DEFAULT 'pending' NOT NULL, 
        attempts INTEGER DEFAULT '0' NOT NULL,
max_attempts INTEGER DEFAULT '5' NOT NULL, 
        run_after TIMESTAMP WITH TIME ZONE DEFAULT
now() NOT NULL, 
        locked_at TIMESTAMP WITH TIME ZONE, 
        locked_by TEXT,
dedupe_key TEXT, 
        last_error TEXT, 
        note TEXT, 
        created_at TIMESTAMP
WITH TIME ZONE DEFAULT now() NOT NULL, 
        finished_at TIMESTAMP WITH TIME ZONE,
PRIMARY KEY (id)
)
    """)
    op.execute("""
CREATE UNIQUE INDEX jobs_dedupe ON jobs (dedupe_key) WHERE status IN ('pending','running')
    """)
    op.execute("""
CREATE INDEX jobs_pick ON jobs (queue, run_after) WHERE status = 'pending'
    """)
    op.execute("""
CREATE TABLE settings (
        key VARCHAR NOT NULL, 
        value JSONB NOT NULL,
PRIMARY KEY (key)
)
    """)
    op.execute("""
CREATE TABLE documents (
        id TEXT NOT NULL, 
        owner_id BIGINT NOT NULL,
shared BOOLEAN DEFAULT true NOT NULL, 
        status TEXT NOT NULL, 
        sha256 TEXT NOT
NULL, 
        mime TEXT NOT NULL, 
        pages INTEGER, 
        vault_path TEXT,
title TEXT, 
        document_date DATE, 
        language TEXT, 
        fts_config REGCONFIG
DEFAULT 'dh_simple'::regconfig NOT NULL, 
        category TEXT, 
        document_type TEXT,
correspondent_id BIGINT, 
        content TEXT, 
        content_tsv TSVECTOR,
manual_fields TEXT[] DEFAULT '{}' NOT NULL, 
        quarantine_reason TEXT, 
        added_at
TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        updated_at TIMESTAMP WITH TIME ZONE
DEFAULT now() NOT NULL, 
        deleted_at TIMESTAMP WITH TIME ZONE, 
        PRIMARY KEY (id),
CONSTRAINT documents_owner_sha256 UNIQUE (owner_id, sha256), 
        FOREIGN KEY(owner_id)
REFERENCES users (id), 
        FOREIGN KEY(correspondent_id) REFERENCES correspondents (id)
)
    """)
    op.execute("""
CREATE INDEX documents_owner ON documents (owner_id, deleted_at)
    """)
    op.execute("""
CREATE INDEX documents_date ON documents (document_date)
    """)
    op.execute("""
CREATE INDEX documents_tsv ON documents USING gin (content_tsv)
    """)
    op.execute("""
CREATE INDEX documents_title_trgm ON documents USING gin (title gin_trgm_ops)
    """)
    op.execute("""
CREATE TABLE sessions (
        token_hash TEXT NOT NULL, 
        user_id BIGINT NOT NULL,
created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        expires_at TIMESTAMP WITH
TIME ZONE NOT NULL, 
        last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
user_agent TEXT, 
        ip INET, 
        PRIMARY KEY (token_hash), 
        FOREIGN
KEY(user_id) REFERENCES users (id)
)
    """)
    op.execute("""
CREATE TABLE api_tokens (
        id BIGSERIAL NOT NULL, 
        user_id BIGINT NOT NULL,
name TEXT NOT NULL, 
        token_hash TEXT NOT NULL, 
        prefix TEXT NOT NULL,
scopes TEXT[] NOT NULL, 
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
last_used_at TIMESTAMP WITH TIME ZONE, 
        revoked_at TIMESTAMP WITH TIME ZONE,
PRIMARY KEY (id), 
        FOREIGN KEY(user_id) REFERENCES users (id), 
        UNIQUE
(token_hash)
)
    """)
    op.execute("""
CREATE TABLE document_tags (
        document_id TEXT NOT NULL, 
        tag_id BIGINT NOT NULL,
PRIMARY KEY (document_id, tag_id), 
        FOREIGN KEY(document_id) REFERENCES documents (id),
FOREIGN KEY(tag_id) REFERENCES tags (id)
)
    """)
    op.execute("""
CREATE TABLE doc_facts (
        document_id TEXT NOT NULL, 
        field TEXT NOT NULL,
type TEXT NOT NULL, 
        value_text TEXT NOT NULL, 
        value_num NUMERIC,
value_date DATE, 
        currency TEXT, 
        confidence DOUBLE PRECISION, 
        PRIMARY
KEY (document_id, field), 
        FOREIGN KEY(document_id) REFERENCES documents (id)
)
    """)
    op.execute("""
CREATE INDEX doc_facts_field ON doc_facts (field, value_date)
    """)
    op.execute("""
CREATE TABLE doc_sources (
        document_id TEXT NOT NULL, 
        kind TEXT NOT NULL,
original_filename TEXT NOT NULL, 
        account_id BIGINT, 
        message_id TEXT,
email_from TEXT, 
        subject TEXT, 
        received_at TIMESTAMP WITH TIME ZONE,
PRIMARY KEY (document_id), 
        FOREIGN KEY(document_id) REFERENCES documents (id)
)
    """)
    op.execute("""
CREATE TABLE notes (
        id BIGSERIAL NOT NULL, 
        document_id TEXT NOT NULL,
user_id BIGINT NOT NULL, 
        body TEXT NOT NULL, 
        created_at TIMESTAMP WITH TIME
ZONE DEFAULT now() NOT NULL, 
        PRIMARY KEY (id), 
        FOREIGN KEY(document_id)
REFERENCES documents (id), 
        FOREIGN KEY(user_id) REFERENCES users (id)
)
    """)


def downgrade() -> None:
    op.drop_table("notes")
    op.drop_table("document_tags")
    op.drop_table("doc_sources")
    op.drop_table("doc_facts")
    op.drop_table("sessions")
    op.drop_table("documents")
    op.drop_table("api_tokens")
    op.drop_table("users")
    op.drop_table("tags")
    op.drop_table("settings")
    op.drop_table("jobs")
    op.drop_table("correspondents")
    op.drop_table("audit_log")
    op.execute("DROP TEXT SEARCH CONFIGURATION dh_english")
    op.execute("DROP TEXT SEARCH CONFIGURATION dh_german")
    op.execute("DROP TEXT SEARCH CONFIGURATION dh_simple")
