# `services/docuhive/tests/fakes`

**Overview.** Test doubles for the shared interfaces, used by unit tests on both sides.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Reusable contract fakes |
| [`core.py`](core.py) | Test doubles for the platform interfaces |
| [`intel.py`](intel.py) | SQLite stand-ins for the platform interfaces (db, jobs, documents, ingest, auth, search) plus helpers for routing and FakeModel |

## Extending

Keep fakes behaviourally identical to the real code; the contract tests check this.
