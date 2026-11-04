# OCR gate — pending measurements

Date: 2026-11-03 · State: pending · Decision: **not made**

The user confirmed that the private 50-document sample set and ten reference
transcriptions do not yet exist. Synthetic smoke tests cannot establish OCR
quality or target-host performance. No GO or NO-GO is inferred from this.

| Criterion | Threshold | Measured |
| --- | --- | --- |
| Unattended ingest, including expected encrypted quarantine | ≥95% | pending |
| Scan character error rate | ≤3% | pending |
| Phone-photo character error rate | ≤8% | pending |
| OCR time per page on target host | ≤10 s | pending |
| Born-digital text preserved | 100% | pending |

Run `make spike-ocr DIR=/private/corpus OUT=/private/report` on the target host,
then compare text with private transcriptions using `evals/ocr/cer.py`.
Record the aggregate measurements here without copying private filenames or text.
A GO unlocks OA-M3. A NO-GO selects the Paperless adapter through the same contracts.
