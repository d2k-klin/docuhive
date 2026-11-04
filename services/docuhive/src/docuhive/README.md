# `services/docuhive/src/docuhive`

**Overview.** The `docuhive` package. Platform modules handle settings, storage, jobs, sign-in and search; the AI modules handle routing, agents, review, email, chat and reminders. They meet only through the shared [contracts](../../../../docs/shared/contracts.md).

## What's here

| Path | What it is |
| --- | --- |
| [`agents/`](agents/) | The AI agents and the harness they run in: triage for email, classify and extract for documents, and the Ask agent for chat |
| [`ai/`](ai/) | The AI layer: provider settings, task routing, the privacy gate, budgets, embeddings and the log of every model call |
| [`api/`](api/) | The FastAPI application factory and the platform's HTTP routes: sign-in, users, tokens and system status |
| [`auth/`](auth/) | Sign-in, sessions, scoped API tokens, login throttling and the single document-visibility rule |
| [`chat/`](chat/) | Chat sessions with streamed answers, and saved analyses that re-run a question on demand |
| [`config/`](config/) | Settings, the private overlay, versioned prompts and plugin discovery |
| [`contracts/`](contracts/) | The shared models every module agrees on |
| [`db/`](db/) | Database engine, sessions, the two metadata sets and the migration runner |
| [`documents/`](documents/) | The documents service: reading documents and applying metadata changes (from people or from AI) with locks, audit and events |
| [`index/`](index/) | Semantic search: chunking documents, embedding them, and finding similar documents |
| [`ingest/`](ingest/) | Turning any incoming file into a searchable PDF: type detection, conversion, OCR, text extraction and thumbnails, with strict limits on untrusted input |
| [`jobs/`](jobs/) | The durable job queue on PostgreSQL: registration, leases, retries and periodic schedules |
| [`kb/`](kb/) | Saved document scopes, ownership, vocabulary validation and indexing status |
| [`mail/`](mail/) | Email intake: Gmail, Microsoft Graph and IMAP connectors, sign-in, deterministic rules, sync and backfill |
| [`notify/`](notify/) | Notifications to ntfy or email, and the periodic checks that trigger them |
| [`reminders/`](reminders/) | Reminders built from extracted dates (due dates, renewals, notice deadlines), plus an iCalendar feed |
| [`review/`](review/) | The review queue: AI suggestions that wait for a person to accept, edit or reject them |
| [`search/`](search/) | Full-text and hybrid search, and the registration point for semantic search |
| [`taxonomy/`](taxonomy/) | The controlled vocabulary (categories, document types, tags and facts) the AI chooses from |
| [`worker/`](worker/) | The background worker that runs jobs from the queue, and the list of modules that register job handlers |
| [`__init__.py`](__init__.py) | DocuHive core platform |
| [`cli.py`](cli.py) | Command-line entry points for the platform and optional intelligence extensions |
| [`startup.py`](startup.py) | Optional intelligence extension initialization |

## Extending

Put new code in the module that owns the concern; cross-module calls go through `docuhive.contracts` and the public module APIs.
