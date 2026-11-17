"""Backup options chosen in the app, written to the vault for the host's backup job."""

import json

import pytest
from docuhive import config, vault

from .test_auth_integration import CSRF
from .test_folders_integration import client, login  # noqa: F401

pytestmark = pytest.mark.integration


def test_backup_options_are_saved_for_the_host_job(client, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("DOCUHIVE_STORAGE_ROOT_LABEL", "/srv/docuhive/storage")
    config.reload()
    (tmp_path / "nas" / "papers").mkdir()
    login(client, "member")
    assert client.get("/api/system/backup/options").status_code == 403
    login(client, "owner")
    first = client.get("/api/system/backup/options").json()
    assert first["options"]["time"] == "03:00" and first["options"]["keep"]["daily"] == 7
    assert first["status"]["at"] is None and first["next_run"]
    assert first["allowed_age_hours"] == 48

    client.post("/api/folders", json={"path": "papers", "label": "Papers"}, headers=CSRF)
    chosen = first["options"] | {
        "time": "02:30",
        "days": [6],
        "keep": {"daily": 10, "weekly": 4, "monthly": 12, "dumps": 5},
        "check_percent": 0,
        "include": {"staging": True, "plugins": False, "linked_folders": True},
    }
    saved = client.put("/api/system/backup/options", json=chosen, headers=CSRF)
    assert saved.status_code == 200, saved.text
    assert saved.json()["allowed_age_hours"] == 8 * 24  # weekly: warn after 8 days
    written = json.loads((vault.root() / "_system" / "backup.json").read_text())
    assert written["time"] == "02:30" and written["days"] == [6]
    assert written["linked_paths"] == ["/srv/docuhive/storage/papers"]  # as the host sees it
    assert written["updated_by"] == "owner"

    bad = client.put("/api/system/backup/options", json=chosen | {"days": []}, headers=CSRF)
    assert bad.status_code == 422
    bad = client.put("/api/system/backup/options", json=chosen | {"time": "25:00"}, headers=CSRF)
    assert bad.status_code == 422

    asked = client.post("/api/system/backup/run", headers=CSRF)
    assert asked.status_code == 202 and asked.json()["request"]["by"] == "owner"
    assert (vault.root() / "_system" / "backup-request.json").is_file()

    # Stopping a linked folder takes it off the backup's list too.
    folder_id = client.get("/api/folders").json()[0]["id"]
    client.delete(f"/api/folders/{folder_id}", headers=CSRF)
    written = json.loads((vault.root() / "_system" / "backup.json").read_text())
    assert written["linked_paths"] == []
