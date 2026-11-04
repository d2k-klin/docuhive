# `services/docuhive/src/docuhive/db`

**Overview.** Database engine, sessions, the two metadata sets and the migration runner.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | SQLAlchemy bases and transactional sessions; intelligence metadata is separate |
| [`migrations.py`](migrations.py) | Run the independent core and intelligence Alembic environments in order |
| [`models.py`](models.py) | Platform relational schema, matching the shared read contracts |

## Extending

Define tables in the owning module's metadata only.
