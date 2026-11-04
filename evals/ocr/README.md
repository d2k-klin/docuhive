# `evals/ocr`

**Overview.** OA's character-error measurement for the private OCR go/no-go gate.

## What's here

| Path | What it is |
| --- | --- |
| [cer.py](cer.py) | NFC, case and whitespace normalisation followed by Levenshtein CER |

Run `uv run python evals/ocr/cer.py /private/reference.txt /private/observed.txt`.
Both inputs stay outside the public repository. Empty reference plus nonempty OCR
is an error, since no meaningful CER denominator exists.

## Extending

Keep OCR measurement independent of AI evals owned by CL. Gate thresholds are in
[the OA ingest plan](../../docs/Developer-OA/02-ingest-and-vault.md).
