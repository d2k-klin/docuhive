# `services/docuhive/src/docuhive/jobs`

**Overview.** The durable job queue on PostgreSQL: registration, leases, retries and periodic schedules.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Durable PostgreSQL jobs and public registration contracts |
| [`runner.py`](runner.py) | Lease-based claiming, execution and recovery |
| [`scheduler.py`](scheduler.py) | Periodic scheduling with connection-scoped PostgreSQL leadership |

## Extending

Register handlers with `@handler`, keep payloads small, and make every job safe to run twice.
