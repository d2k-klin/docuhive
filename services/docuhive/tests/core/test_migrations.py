"""Migration ordering is independent of each track's current head revision."""

import pytest
from docuhive.db import migrations


@pytest.mark.parametrize(
    "action,order",
    [
        ("upgrade", ["core", "intel"]),
        ("downgrade", ["intel", "core"]),
        ("current", ["core", "intel"]),
    ],
)
def test_migration_order(monkeypatch, action, order):
    calls = []
    monkeypatch.setattr(migrations, "migration_config", lambda track: track)
    monkeypatch.setattr(migrations.command, action, lambda *args: calls.append(args))
    migrations.migrate(action)
    assert [call[0] for call in calls] == order


def test_environments_are_packaged_and_unknown_action_is_rejected():
    from pathlib import Path

    for track in ("core", "intel"):
        assert (
            Path(migrations.migration_config(track).get_main_option("script_location")) / "env.py"
        ).is_file()
    with pytest.raises(ValueError):
        migrations.migrate("invalid")
