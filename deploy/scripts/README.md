# `deploy/scripts`

**Overview.** Helper scripts used by the `Makefile` and CI.

## What's here

| Path | What it is |
| --- | --- |
| [`backup.sh`](backup.sh) | Entry point for the host backup timer |
| [`backup.py`](backup.py) | Quiesced database/vault/staging backup with retention and status |
| [`perf_ingest.py`](perf_ingest.py) | NFR-04: times synthetic scanned PDFs from upload to stored through a real worker; empties the `_test` database and uses a temporary vault (`make perf-ingest`) |
| [`perf_search.py`](perf_search.py) | NFR-04: seeds synthetic documents into a `_test` database and times word search (`make perf-search`) |
| [`upgrade.sh`](upgrade.sh) | Build a release, back up, migrate and start with a recovery boundary |
| [`restore.md`](restore.md) | Full, database-only and single-document recovery |
| [`check_licenses.py`](check_licenses.py) | Fail on AGPL Python distributions; subprocess tools are listed separately |
| [`dev.py`](dev.py) | Run the three development processes and shut down the entire process groups together |
| [`ocr_smoke.py`](ocr_smoke.py) | Run DocuHive's real OCR on a synthetic scan inside the worker image; used by `make ocr-smoke` |
| [`generate_ocr_fixtures.py`](generate_ocr_fixtures.py) | Generate a small public, synthetic corpus for smoke checks; it cannot pass the real OCR gate |

## Extending

Scripts must be runnable from the repo root and must not need network access unless they say so.
