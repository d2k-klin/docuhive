# `deploy/scripts`

**Overview.** Helper scripts used by the `Makefile` and CI.

## What's here

| Path | What it is |
| --- | --- |
| [`check_licenses.py`](check_licenses.py) | Fail on AGPL Python distributions; subprocess tools are listed separately |
| [`dev.py`](dev.py) | Run the three development processes and shut down the entire process groups together |
| [`generate_ocr_fixtures.py`](generate_ocr_fixtures.py) | Generate a small public, synthetic corpus for smoke checks; it cannot pass the real OCR gate |

## Extending

Scripts must be runnable from the repo root and must not need network access unless they say so.
