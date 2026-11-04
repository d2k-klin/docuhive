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

## In the code

- [Public job contract](../../services/docuhive/src/docuhive/jobs/__init__.py)
- [Claim, run and reap](../../services/docuhive/src/docuhive/jobs/runner.py)
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
