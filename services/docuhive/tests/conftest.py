"""Shared synthetic fixtures; integration tests opt into an isolated PostgreSQL URL."""

import os
from datetime import UTC, datetime

import pytest
from docuhive import config
from docuhive.contracts import DocStatus, DocumentView, SourceInfo, SourceKind
from docuhive.db import get_engine

from .fakes.core import install_fake_core


@pytest.fixture(autouse=True)
def reset_core_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCUHIVE_ENV", "test")
    monkeypatch.setenv("DOCUHIVE_AUTH_DISABLED", "false")
    # Never the repository's data/ folder: every test gets its own vault and staging.
    monkeypatch.setenv("DOCUHIVE_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("DOCUHIVE_STAGING_DIR", str(tmp_path / "staging"))
    config.reload()
    yield
    config.reload()


@pytest.fixture
def document():
    return DocumentView(
        id="01JCAAAAAAAAAAAAAAAAAAAAAA",
        owner_id=1,
        shared=False,
        status=DocStatus.stored,
        mime="application/pdf",
        pages=1,
        added_at=datetime.now(UTC),
        title="Synthetic invoice",
        document_date=None,
        language=None,
        category=None,
        document_type=None,
        correspondent=None,
        tags=[],
        facts={},
        manual_fields=[],
        source=SourceInfo(kind=SourceKind.upload, original_filename="synthetic.pdf"),
        deleted_at=None,
    )


@pytest.fixture
def fake_core(monkeypatch, tmp_path):
    return install_fake_core(monkeypatch, tmp_path / "fake-vault")


@pytest.fixture
def postgres(monkeypatch, request):
    from docuhive.db import (
        CoreBase,
        models,  # noqa: F401
        session,
    )
    from docuhive.db.migrations import migrate
    from sqlalchemy import text

    url = os.environ.get("DOCUHIVE_TEST_DATABASE_URL")
    if not url:
        reason = "Set DOCUHIVE_TEST_DATABASE_URL to the disposable integration database"
        # Asked for by name (-m integration): a missing database is a failure, not a quiet skip.
        selected = request.config.getoption("markexpr", "").replace("not integration", "")
        (pytest.fail if "integration" in selected else pytest.skip)(reason)
    from sqlalchemy.engine import make_url

    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail("Integration database name must end in _test")
    monkeypatch.setenv("DOCUHIVE_DATABASE_URL", url)
    config.reload()
    get_engine.cache_clear()
    migrate("upgrade")
    names = ", ".join(f'"{table}"' for table in CoreBase.metadata.tables)
    with session() as db:
        db.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    yield get_engine()
    get_engine().dispose()
    get_engine.cache_clear()
