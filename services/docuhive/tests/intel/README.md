# `services/docuhive/tests/intel`

**Overview.** Tests for the AI, review, email, search, chat and reminder modules, including the privacy audit. Recorded Gmail and Graph responses live in `fixtures/`.

## What's here

| Path | What it is |
| --- | --- |
| [`fixtures/`](fixtures/) | Recorded Gmail and Graph responses |
| [`__init__.py`](__init__.py) | Package marker |
| [`conftest.py`](conftest.py) | Fixtures: test doubles, FakeModel and a test client |
| [`test_ai_layer.py`](test_ai_layer.py) | Routing, privacy gate, harness and budgets |
| [`test_api.py`](test_api.py) | AI, review and taxonomy endpoints |
| [`test_ask.py`](test_ask.py) | The Ask agent, tools and streaming |
| [`test_classify_extract.py`](test_classify_extract.py) | Classification, extraction and apply rules |
| [`test_evals.py`](test_evals.py) | Eval harness smoke run |
| [`test_index.py`](test_index.py) | Chunking, embedding and semantic search |
| [`test_mail.py`](test_mail.py) | Connectors, rules, triage, sync and backfill |
| [`test_postgres_integration.py`](test_postgres_integration.py) | PostgreSQL-only checks: pgvector search, the privacy constraint and the review index |
| [`test_privacy_audit.py`](test_privacy_audit.py) | AI-03 audit: restricted documents never reach a non-local model, through any flow |
| [`test_reminders_notify.py`](test_reminders_notify.py) | Reminders, channels and the calendar feed |
| [`test_validators.py`](test_validators.py) | Money, date and IBAN parsing |

## Extending

Use FakeModel and recorded fixtures; no test may call a real provider.
