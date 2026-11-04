"""Scanner persistence and library filesystem effects with real PostgreSQL."""

import pytest

from . import test_capture_operations as scenarios
from .test_archive_tools_integration import tools as postgres_tools

tools = postgres_tools
mounted = scenarios.mounted
pytestmark = pytest.mark.integration


def test_scanner_retention_on_postgres(mounted, tmp_path, monkeypatch):
    scenarios.test_scanner_stability_persistent_ledger_and_verified_release(
        mounted, tmp_path, monkeypatch
    )


def test_scanner_rejection_on_postgres(mounted, tmp_path, monkeypatch):
    scenarios.test_scanner_ignore_rejection_and_outage_preserve_inputs(
        mounted, tmp_path, monkeypatch
    )


def test_library_on_postgres(mounted, monkeypatch):
    scenarios.test_library_hardlinks_collision_privacy_metadata_changes_and_no_copy(
        mounted, monkeypatch
    )
