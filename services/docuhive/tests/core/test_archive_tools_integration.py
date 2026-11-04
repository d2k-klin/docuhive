"""The archive-tool scenarios against the real migrated PostgreSQL schema."""

import pytest
from docuhive.api.app import create_app
from docuhive.auth import create_user
from docuhive.auth.rate_limit import LoginLimiter
from fastapi.testclient import TestClient

from . import test_archive_tools as scenarios
from .test_auth_integration import PASSWORD

pytestmark = pytest.mark.integration


@pytest.fixture
def tools(postgres, monkeypatch, tmp_path):
    monkeypatch.setattr("docuhive.api.app.start_intelligence", lambda: None)
    monkeypatch.setattr("docuhive.api.auth.limiter", LoginLimiter())
    create_user("owner", PASSWORD, admin=True)
    create_user("other", PASSWORD)
    with TestClient(create_app(), base_url="https://testserver") as client:
        yield scenarios.setup(client, monkeypatch, tmp_path)


@pytest.mark.parametrize(
    "scenario",
    [
        scenarios.test_vault_health_reports_every_problem_without_changing_files,
        scenarios.test_unmounted_vault_is_one_problem,
        scenarios.test_custom_fields_extend_extraction_and_stay_admin_only,
        scenarios.test_saved_views_share_filters_not_documents,
        scenarios.test_export_zip_csv_and_boundaries,
    ],
    ids=["vault-health", "vault-unmounted", "custom-fields", "saved-views", "export"],
)
def test_archive_tools_on_postgres(tools, scenario):
    scenario(tools)


def test_duplicates_on_postgres(tools, monkeypatch):
    scenarios.test_duplicate_scan_and_decisions(tools, monkeypatch)
