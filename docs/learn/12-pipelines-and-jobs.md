# Pipelines and jobs

**In one sentence.** A durable job records work before a worker attempts it, so
process crashes and temporarily unavailable services do not lose the task.

**Why DocuHive needs it.** OCR, email and AI work can outlive an HTTP request.
They need independent retry policies while the user continues using the app.

## How it works

A producer inserts a pending job into PostgreSQL. A worker claims it with
`FOR UPDATE SKIP LOCKED`, records a unique lease and commits before doing work.
Only the holder of that lease may finalize the job. A missed heartbeat lets
the reaper make it available again. Work must be idempotent because a crash
can occur after a side effect but before the success record.

Transient failures back off from 30 seconds to one hour. Permanent failures
become dead immediately. A handler can defer without spending an attempt.
Missing CL handlers remain pending with a visible `no handler` note.

Periodic jobs are scheduled by the worker holding a PostgreSQL advisory lock.
The lock stays on one connection and is released when that connection closes.
Periodic deduplication prevents an already-running task from being enqueued twice.

Phone capture stores pending files in a device-local queue; browser uploads and scoped API
tokens reach the same `ingest.submit` contract as email. The scanner source polls every
30 seconds, remembers stable files in PostgreSQL, and keeps its source copy until the
stored vault original passes checksum verification. A NAS outage pauses pickup. These
source adapters are implemented; complete document-core acceptance remains separate.

## In the code

- [Public job contract](../../services/docuhive/src/docuhive/jobs/__init__.py)
- [Claim, run and reap](../../services/docuhive/src/docuhive/jobs/runner.py)
- [Scanner source](../../services/docuhive/src/docuhive/ingest/consume.py)
- [Upload source](../../services/docuhive/src/docuhive/api/upload.py)
- [Scheduler leadership](../../services/docuhive/src/docuhive/jobs/scheduler.py)
- [PostgreSQL regression checks](../../services/docuhive/tests/core/test_jobs_integration.py)

## Run it

`make learn EX=12` runs a fake producer and worker without a database or keys.
`make test-integration` exercises the actual PostgreSQL implementation.

## See it in the app

The admin API exposes `/api/system/jobs`. The web System page is still pending
OA-M5; it must display attempts, deferred reasons and retry actions.

## Try it yourself

Raise `RetryLater` from a test handler, then compare it with `ctx.defer`.
Terminate a worker after claiming a job and verify recovery after its lease expires.

## Pitfalls we hit

A previous worker must not finalize a reclaimed job. Final updates include the
unique lease in their WHERE condition. A connection-scoped advisory lock also
must not be released back into a pool while the scheduler is running.

## Further reading

[PostgreSQL row locking](https://www.postgresql.org/docs/16/sql-select.html#SQL-FOR-UPDATE-SHARE)
and [advisory locks](https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS).

## Visible AI progress

The [progress endpoint](../../services/docuhive/src/docuhive/ai/progress.py) combines the latest document jobs with AI runs and pending review items. A new queued re-run takes precedence over an older successful run. The UI polls while work is active, then slows down after completion. Status responses are scoped to documents the caller can see; they exclude job payloads and internal error strings.

A completed model run is not proof that its category was applied. Progress shows an unapplied suggestion separately and keeps the result in review until the existing approval policy applies it.
