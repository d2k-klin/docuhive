"""Seed only the compose QA database; no resets, no writes to any existing archive."""

from docuhive.auth import create_user
from docuhive.config.settings import get_settings
from docuhive.db import session
from docuhive.db.migrations import migrate
from docuhive.db.models import User
from sqlalchemy import select
from sqlalchemy.engine import make_url

PASSWORD = "synthetic qa password 2026"


def main() -> None:
    settings = get_settings()
    url = make_url(settings.database_url)
    if settings.env != "test" or url.database != "docuhive_test" or url.host != "postgres":
        raise ValueError("QA seed is restricted to the isolated compose database")
    import psycopg

    with psycopg.connect(
        host="postgres",
        user="docuhive_test",
        password="docuhive_test",
        dbname="postgres",
        autocommit=True,
    ) as connection:
        if not connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", ("docuhive_contract_test",)
        ).fetchone():
            connection.execute("CREATE DATABASE docuhive_contract_test")
    migrate("upgrade")
    from docuhive import vault

    vault.init()  # the isolated e2e volume; refuses any folder that is not empty and not a vault
    for name, admin in (("alice", True), ("bob", False)):
        with session() as db:
            exists = db.scalar(select(User.id).where(User.username == name))
        if exists is None:
            create_user(name, PASSWORD, admin=admin)


if __name__ == "__main__":
    main()
