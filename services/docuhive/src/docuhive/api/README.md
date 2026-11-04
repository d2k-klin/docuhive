# `services/docuhive/src/docuhive/api`

**Overview.** The FastAPI application factory and the platform's HTTP routes: sign-in, users, tokens and system status.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | HTTP application |
| [`app.py`](app.py) | FastAPI factory with fail-fast settings and optional intelligence startup |
| [`auth.py`](auth.py) | Browser login, sessions and personal access tokens |
| [`routers.py`](routers.py) | Shared touchpoint: append routers without removing existing registrations |
| [`system.py`](system.py) | Public health and protected platform operations |
| [`users.py`](users.py) | Administrator user management; data visibility is never elevated by this role |

## Extending

Register a new router by appending it to `routers.py`; follow the error and pagination conventions in the contracts.
