# Third-party software

Python dependencies are locked in `uv.lock`, and npm dependencies in `package-lock.json`.
Run `make license-check` before introducing dependencies. AGPL Python imports are
rejected, including SPDX and full-name variants of the license.

| Subprocess or container | License | Role |
| --- | --- | --- |
| Tesseract | Apache-2.0 | OCR engine |
| Ghostscript | AGPL-3.0 or commercial | Separate OCRmyPDF subprocess |
| unpaper | GPL-2.0 | Optional separate image-cleaning subprocess |
| Gotenberg | MIT | Isolated document-conversion service |
| PostgreSQL | PostgreSQL | Metadata, search and durable queue |
| pgvector | PostgreSQL | Vector extension for CL's semantic index |

No Ghostscript or unpaper library is imported into DocuHive. Their inclusion in
container images retains their own distribution and license obligations.
