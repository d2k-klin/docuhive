"""Each plugin keeps its tables in a database schema of its own, created by numbered SQL files
in `migrations/`, and (with `snapshot: true`) copied into the vault every night so a database
rebuilt from the vault gets them back."""

import gzip
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from docuhive import db
from docuhive.db.models import PluginState

FILE = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")
KEEP = 14


class MigrationError(RuntimeError):
    pass


def schema(plugin_id: str) -> str:
    return "plugin_" + plugin_id.replace("-", "_")


def migrations(path: Path) -> list[tuple[int, Path]]:
    folder = path / "migrations"
    if not folder.is_dir():
        return []
    found = []
    for file in sorted(folder.iterdir()):
        match = FILE.match(file.name)
        if match:
            found.append((int(match[1]), file))
    return found


def check(path: Path) -> list[str]:
    """Problems with migration files, for `docuhive plugins check`."""
    problems = []
    folder = path / "migrations"
    if not folder.is_dir():
        return []
    numbers: list[int] = []
    for file in sorted(folder.iterdir()):
        rel = f"migrations/{file.name}"
        if file.suffix != ".sql":
            continue
        if not FILE.match(file.name):
            problems.append(f"{rel}: name it like 001_create_items.sql")
            continue
        numbers.append(int(file.name[:3]))
        sql = file.read_text(encoding="utf-8")
        body = re.sub(r"--[^\n]*", "", sql)
        for qualified in re.findall(r"\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\s*\(", body, re.I):
            if qualified[0].lower() == "public" and qualified[1].lower() in {"documents", "users"}:
                continue
            if qualified[0].lower() in {"public", "pg_catalog", "information_schema"} or (
                qualified[0].lower().startswith("plugin_")
            ):
                problems.append(
                    f"{rel}: refers to {'.'.join(qualified)}; plugins use their own tables"
                )
        if re.search(r"\b(set\s+search_path|create\s+schema|drop\s+schema)\b", body, re.I):
            problems.append(f"{rel}: must not change schemas or the search path")
        if re.search(r"\bdrop\s+(table|column)\b", body, re.I) and "-- destructive:" not in sql:
            problems.append(f"{rel}: drops data; add a '-- destructive: <reason>' comment")
        for table, columns in re.findall(
            r"create\s+table\s+(?:if\s+not\s+exists\s+)?([a-z_][a-z0-9_]*)\s*\((.*?)\);",
            body,
            re.I | re.S,
        ):
            if not re.search(r"\b(owner_id|document_id|[a-z_]+_id)\b", columns) and (
                f"-- shared: {table}" not in sql
            ):
                problems.append(
                    f"{rel}: table {table} has no owner_id or link to an owned row; "
                    f"add one or a '-- shared: {table}' comment explaining why"
                )
    if numbers != list(range(1, len(numbers) + 1)):
        problems.append("migrations: number the files 001, 002, … without gaps")
    return problems


def migrate(plugin_id: str, path: Path) -> int:
    """Apply the plugin's migrations it has not applied yet, each in its own transaction.
    Returns the number reached. Several processes starting at once take turns."""
    files = migrations(path)
    name = schema(plugin_id)
    with db.session() as s:
        s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"plugin:{plugin_id}"})
        s.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{name}"'))
        row = s.get(PluginState, plugin_id)
        done = row.migration if row else 0
    for number, file in files:
        if number <= done:
            continue
        with db.session() as s:
            s.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"plugin:{plugin_id}"}
            )
            row = s.get(PluginState, plugin_id)
            if row and row.migration >= number:
                continue
            s.execute(text(f'SET LOCAL search_path TO "{name}", public'))
            try:
                s.connection().exec_driver_sql(file.read_text(encoding="utf-8"))
            except Exception as error:
                raise MigrationError(f"migrations/{file.name}: {error}") from None
            if row is not None:
                row.migration = number
            done = number
    return done


def drop(plugin_id: str) -> None:
    with db.session() as s:
        s.execute(text(f'DROP SCHEMA IF EXISTS "{schema(plugin_id)}" CASCADE'))
        row = s.get(PluginState, plugin_id)
        if row is not None:
            row.migration = 0


def tables(plugin_id: str) -> list[str]:
    with db.session() as s:
        return list(
            s.scalars(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :s AND table_type = 'BASE TABLE' ORDER BY table_name"
                ),
                {"s": schema(plugin_id)},
            )
        )


def _json(value: object) -> object:
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    raise TypeError(f"cannot snapshot a {type(value).__name__}")


def _value(value: object) -> object:
    if isinstance(value, dict) and len(value) == 1:
        ((key, raw),) = value.items()
        if key == "$decimal":
            return Decimal(raw)
        if key == "$datetime":
            return datetime.fromisoformat(raw)
        if key == "$date":
            return date.fromisoformat(raw)
    return value


def snapshot_dir(plugin_id: str) -> Path:
    from docuhive import vault

    return vault.root() / "_system" / "plugins" / plugin_id


def snapshot(plugin_id: str) -> Path | None:
    """Write every table of the plugin as one gzip'd JSON line per row into the vault."""
    from docuhive import vault

    names = tables(plugin_id)
    if not names:
        return None
    lines = []
    with db.session() as s:
        s.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        for table in names:
            result = s.execute(text(f'SELECT * FROM "{schema(plugin_id)}"."{table}"'))
            for row in result.mappings():
                lines.append(json.dumps({"table": table, "row": dict(row)}, default=_json))
    folder = snapshot_dir(plugin_id)
    target = folder / f"snapshot-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.ndjson.gz"
    vault.write_atomic(target, gzip.compress(("\n".join(lines) + "\n").encode()))
    for old in sorted(folder.glob("snapshot-*.ndjson.gz"))[:-KEEP]:
        old.unlink()
    return target


def _dependency_order(plugin_id: str, names: list[str]) -> list[str]:
    """Tables ordered so that a referenced table comes before the tables pointing at it."""
    with db.session() as s:
        edges = s.execute(
            text(
                "SELECT c.conrelid::regclass::text, c.confrelid::regclass::text "
                "FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace "
                "WHERE c.contype = 'f' AND n.nspname = :s"
            ),
            {"s": schema(plugin_id)},
        ).all()
    needs: dict[str, set[str]] = {n: set() for n in names}
    for child, parent in edges:
        child, parent = child.split(".")[-1].strip('"'), parent.split(".")[-1].strip('"')
        if child in needs and parent in needs and child != parent:
            needs[child].add(parent)
    ordered: list[str] = []
    while needs:
        ready = sorted(n for n, deps in needs.items() if deps <= set(ordered))
        if not ready:  # a cycle: fall back to name order; the insert will say what is wrong
            ready = sorted(needs)
        for n in ready:
            ordered.append(n)
            needs.pop(n)
    return ordered


def restore(plugin_id: str) -> int:
    """Replace the plugin's rows with the newest snapshot (after `vault rebuild`)."""
    files = sorted(snapshot_dir(plugin_id).glob("snapshot-*.ndjson.gz"))
    if not files:
        return 0
    items = [json.loads(line) for line in gzip.decompress(files[-1].read_bytes()).splitlines()]
    name = schema(plugin_id)
    order = _dependency_order(plugin_id, tables(plugin_id))
    with db.session() as s:
        if order:
            s.execute(text("TRUNCATE " + ", ".join(f'"{name}"."{t}"' for t in order)))
        for table in order:
            for item in (i for i in items if i["table"] == table):
                row = {k: _value(v) for k, v in item["row"].items()}
                columns = ", ".join(f'"{c}"' for c in row)
                values = ", ".join(f":{c}" for c in row)
                s.execute(
                    text(f'INSERT INTO "{name}"."{table}" ({columns}) VALUES ({values})'), row
                )
            sequence = (
                s.scalar(
                    text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": f'"{name}"."{table}"'}
                )
                if _has_id(s, name, table)
                else None
            )
            if sequence:  # new rows continue after the restored ids
                s.execute(
                    text(
                        "SELECT setval(:q, COALESCE((SELECT MAX(id) FROM "
                        f'"{name}"."{table}"), 0) + 1, false)'
                    ),
                    {"q": sequence},
                )
    return len(items)


def _has_id(s: object, name: str, table: str) -> bool:
    return bool(
        s.scalar(  # type: ignore[attr-defined]
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = :t AND column_name = 'id'"
            ),
            {"s": name, "t": table},
        )
    )
