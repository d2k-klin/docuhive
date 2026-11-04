# `deploy`

**Overview.** Docker Compose stacks for development, integration tests and the QA end-to-end environment, plus helper scripts.

## What's here

| Path | What it is |
| --- | --- |
| [`scripts/`](scripts/) | Helper scripts used by the `Makefile` and CI |
| [`compose.dev.yml`](compose.dev.yml) | PostgreSQL and Gotenberg for local development |
| [`compose.e2e.yml`](compose.e2e.yml) | The full QA stack with mocks for AI and email providers |
| [`compose.test.yml`](compose.test.yml) | Disposable PostgreSQL and Gotenberg for integration tests |
| [`postgres-init.sql`](postgres-init.sql) | Database extensions created on first start |

## Extending

Keep services bound to `127.0.0.1`, pin images by digest, and mirror any new command in the `Makefile`.
