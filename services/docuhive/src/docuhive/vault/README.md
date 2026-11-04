# `services/docuhive/src/docuhive/vault`

**Overview.** The vault on your storage is the source of truth for every document: its layout, the availability check, verified atomic writes, each document's `meta.json`, and the read-only health check.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | `init`, the availability check (`check`, `require`), the folder layout and verified atomic writes |
| [`migrate.py`](migrate.py) | `meta.json` schema versions: ordered upgrades applied whenever a file is read |
| [`rebuild.py`](rebuild.py) | `docuhive vault rebuild [--dry-run]` recreates the database from the vault; `docuhive vault migrate` rewrites old `meta.json` files |
| [`meta.py`](meta.py) | `meta.json`, rendered from the database after every change, with a retried repair job when the vault is away |
| [`health.py`](health.py) | Checks that each stored document's files exist, parse and match the database, finds orphan folders, stores the last report and runs weekly |

## Extending

The health check only reads. Repairs belong in their own commands, with a dry run first.

If the database is lost, run `docuhive db upgrade`, then `docuhive vault rebuild --dry-run` and `docuhive vault rebuild`. Owners missing from the new database are created disabled; set their passwords with `docuhive user passwd`. The AI track re-indexes the documents without re-classifying them.

A change to `meta.json` adds a step to `MIGRATIONS` in `migrate.py` (never edit an old one), then `docuhive vault migrate` rewrites the files.
