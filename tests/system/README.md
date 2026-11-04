# `tests/system`

**Overview.** Independent QA checks of real contracts, the running backend and the QA harness.

## What's here

| Path | Purpose |
| --- | --- |
| [tools](tools/README.md) | Collection, evidence, traceability and stack helpers |
| [conftest.py](conftest.py) | Loopback-only stack access; never resets an existing archive |

## Extending

Add `pytest.mark.req` with requirement IDs. Mark stack tests `integration` and `system`.
Use strict, exception-specific xfails with a link to the [defect register](../../docs/Developer-QA/bugs.md).
`make qa-check` runs offline checks; `make qa-system` requires `make qa-up` first.
