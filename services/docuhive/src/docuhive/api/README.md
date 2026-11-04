# `services/docuhive/src/docuhive/api`

**Overview.** The FastAPI application factory and the platform's HTTP routes: sign-in, users, tokens, system status, knowledge bases and the archive tools.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | HTTP application |
| [`app.py`](app.py) | FastAPI factory with fail-fast settings and optional intelligence startup |
| [`auth.py`](auth.py) | Browser login, sessions and personal access tokens |
| [`duplicates.py`](duplicates.py) | Possible duplicate pairs the caller can see both sides of, and decisions on them |
| [`documents.py`](documents.py) | Documents: list, detail, files, history, edit, bulk edit, trash, upload and quarantine retry |
| [`export.py`](export.py) | ZIP export of archive PDFs plus a CSV of details, for a filter, saved view or knowledge base |
| [`fields.py`](fields.py) | Custom fields: everyone reads them, administrators define them |
| [`knowledge.py`](knowledge.py) | Knowledge-base CRUD, filter choices, suggestions and caller-visible indexing status |
| [`routers.py`](routers.py) | Shared touchpoint: append routers without removing existing registrations |
| [`system.py`](system.py) | Public health and protected platform operations, including the vault health report |
| [`users.py`](users.py) | Administrator user management; data visibility is never elevated by this role |
| [`vocabulary.py`](vocabulary.py) | Tags and senders: typeahead lists for everyone, rename and merge for administrators |
| [`views.py`](views.py) | Saved views: named filters, pinning, sharing and the documents they match |

## Extending

Register a new router by appending it to `routers.py`; follow the error and pagination conventions in the contracts.
