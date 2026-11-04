# `services/docuhive/src/docuhive/vault`

**Overview.** The vault on your storage is the source of truth for every document. Writing to it arrives with document intake; this folder already holds the read-only health check.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Package marker |
| [`health.py`](health.py) | Checks that each stored document's files exist, parse and match the database, finds orphan folders, stores the last report and runs weekly |

## Extending

The health check only reads. Repairs belong in their own commands, with a dry run first.
