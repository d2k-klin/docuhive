"""Run the independent core and intelligence Alembic environments in order."""

from pathlib import Path

from alembic import command
from alembic.config import Config


def migration_config(track: str) -> Config:
    source = Path(__file__).resolve().parents[3] / "migrations"
    root = source if source.is_dir() else Path(__file__).resolve().parents[1] / "_migrations"
    config = Config()
    config.set_main_option("script_location", str(root / track))
    config.set_main_option("version_path_separator", "os")
    return config


def migrate(action: str, revision: str | None = None) -> None:
    if action not in {"upgrade", "downgrade", "current"}:
        raise ValueError("Unknown migration action")
    tracks = ("intel", "core") if action == "downgrade" else ("core", "intel")
    for track in tracks:
        config = migration_config(track)
        if action == "current":
            command.current(config)
        elif action == "upgrade":
            command.upgrade(config, revision or "head")
        else:
            command.downgrade(config, revision or "-1")
