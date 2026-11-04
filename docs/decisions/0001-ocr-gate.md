# OCR gate: waived, native core selected

Date: 2026-11-04 · State: decided · Decision: **GO (waived by the owner)**

The private 50-document sample set and ten reference transcriptions do not exist
(confirmed 2026-11-03). On 2026-11-04 the owner waived the gate and chose the native
core (OCRmyPDF, Tesseract, Gotenberg) over the Paperless adapter, so document intake
(OA-M3) can start.

The evidence is limited, and that is recorded here rather than hidden:

- The synthetic conversion and OCR tests pass, both locally and in the worker image
  (`ci.yml`, "OCR in the worker image").
- Nothing about real-world OCR quality or speed on the target host has been measured.

| Criterion | Threshold | Measured |
| --- | --- | --- |
| Unattended ingest, including expected encrypted quarantine | ≥95% | not measured |
| Scan character error rate | ≤3% | not measured |
| Phone-photo character error rate | ≤8% | not measured |
| OCR time per page on target host | ≤10 s | not measured |
| Born-digital text preserved | 100% | synthetic only |

## What still has to happen

The measurements move to the release gate (phase 6 of the
[production-readiness plan](../shared/production-readiness.md)). Before 1.0, run
`make spike-ocr DIR=/private/corpus OUT=/private/report` on the target host with the
first real documents, compare text with private transcriptions using `evals/ocr/cer.py`,
and record the aggregate numbers in the table above without private filenames or text.
A failing result there blocks 1.0. It does not undo this choice, because the
Paperless adapter would sit behind the same contracts.
