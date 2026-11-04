# `services/docuhive/migrations/core`

**Overview.** Migrations for the platform tables (users, documents, jobs).

## What's here

| Path | What it is |
| --- | --- |
| [`versions/`](versions/) | Platform schema revisions, applied in order |
| [`env.py`](env.py) | Core metadata only; intelligence tables are excluded from autogeneration |
| [`script.py.mako`](script.py.mako) | Template for new revisions |

## Extending

Add a new revision; never change one that has been merged.
