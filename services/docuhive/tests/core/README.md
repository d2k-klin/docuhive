# `services/docuhive/tests/core`

**Overview.** Tests for the platform modules; Docker-backed ones are marked `integration`.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Package marker |
| [`test_archive_tools.py`](test_archive_tools.py) | Vault health, custom fields, saved views, near-duplicates and export without network |
| [`test_archive_tools_integration.py`](test_archive_tools_integration.py) | The same archive-tool scenarios on the real migrated PostgreSQL schema |
| [`test_document_core.py`](test_document_core.py) | Upload, processing, vault outage, quarantine and retry, crash recovery, edits and trash without network |
| [`test_document_core_integration.py`](test_document_core_integration.py) | The real pipeline: Gotenberg, Tesseract, vault and search vector on PostgreSQL |
| [`test_auth.py`](test_auth.py) | Password, request and login throttling behavior without a database |
| [`test_auth_integration.py`](test_auth_integration.py) | Real storage tests for session lifecycle, scoped tokens and visibility SQL |
| [`test_auth_memory.py`](test_auth_memory.py) | Run the same auth acceptance scenarios against a network-free test database |
| [`test_capture_operations.py`](test_capture_operations.py) | Bounded upload, scanner retention, library safety and backup reporting without network |
| [`test_capture_operations_integration.py`](test_capture_operations_integration.py) | Scanner and library scenarios on real PostgreSQL |
| [`test_backup_script.py`](test_backup_script.py) | Backup/upgrade failure recovery, retention and snapshot verification |
| [`test_operations_integration.py`](test_operations_integration.py) | v0.1.0-to-current upgrade preserving metadata, facts and credentials |
| [`test_cli.py`](test_cli.py) | CLI dispatch must preserve queue selection, fail-fast security and password handling |
| [`test_config.py`](test_config.py) | Overlay safety, merge rules, cache invalidation and startup validation |
| [`test_conversion_integration.py`](test_conversion_integration.py) | The conversion service receives only synthetic, self-contained document bodies |
| [`test_job_policy.py`](test_job_policy.py) | Exercise handler outcomes without a database; SQL concurrency is checked separately |
| [`test_jobs_integration.py`](test_jobs_integration.py) | Real PostgreSQL proof for dedupe, leases, retries and scheduler leadership |
| [`test_knowledge.py`](test_knowledge.py) | Saved-scope validation, ownership, status and token privilege checks without network |
| [`test_knowledge_integration.py`](test_knowledge_integration.py) | Real migration, CRUD, visibility, status and pagination checks |
| [`test_search.py`](test_search.py) | Rank fusion, chunk limits and compiled PostgreSQL query checks |
| [`test_search_integration.py`](test_search_integration.py) | Real stemming, accents, typo fallback, permissions and chunk diversification |
| [`test_migrations.py`](test_migrations.py) | Migration ordering is independent of each track's current head revision |
| [`test_ocr_report.py`](test_ocr_report.py) | The spike report must preserve failed inputs and measure the actual processing result |
| [`test_ocr_spike.py`](test_ocr_spike.py) | Synthetic parsing, conversion and OCR policy checks; no private corpus or external tools |
| [`test_platform.py`](test_platform.py) | Key-free checks for health, CLI, transactions and extension fallback |
| [`test_worker.py`](test_worker.py) | Shutdown, queue outages and scheduler connection ownership without external services |

## Extending

Name files after the module they test.
