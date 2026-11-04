"""Periodic scheduling with connection-scoped PostgreSQL leadership."""

from datetime import UTC, datetime

from sqlalchemy import Connection, select, text
from sqlalchemy.dialects.postgresql import insert

from docuhive.db import session
from docuhive.db.models import Setting
from docuhive.jobs import PERIODICS, enqueue

LOCK = "hashtext('docuhive-scheduler')"


def acquire(connection: Connection) -> bool:
    return bool(connection.scalar(text(f"SELECT pg_try_advisory_lock({LOCK})")))


def release(connection: Connection) -> None:
    connection.execute(text(f"SELECT pg_advisory_unlock({LOCK})"))
    connection.commit()


def tick() -> None:
    now = datetime.now(UTC)
    for kind, registration in list(PERIODICS.items()):
        key = f"periodic:{kind}"
        with session() as db:
            last = db.scalar(select(Setting.value).where(Setting.key == key))
            if last and now - datetime.fromisoformat(last) < registration.every:
                continue
            enqueue(kind, {}, queue=registration.queue, dedupe_key=key)
            db.execute(
                insert(Setting)
                .values(key=key, value=now.isoformat())
                .on_conflict_do_update(
                    index_elements=[Setting.key], set_={"value": now.isoformat()}
                )
            )
