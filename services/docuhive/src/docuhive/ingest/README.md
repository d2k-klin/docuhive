# `services/docuhive/src/docuhive/ingest`

**Overview.** Turning any incoming file into a searchable PDF: type detection, conversion, OCR, text extraction and thumbnails, with strict limits on untrusted input.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | `submit`: the single entry point for every source (validate, dedupe, stage, queue) |
| [`consume.py`](consume.py) | Durable scanner polling; retains input until the stored original is checksum-verified |
| [`convert.py`](convert.py) | Pure conversion steps reused by the OCR feasibility spike |
| [`detect.py`](detect.py) | Content detection without trusting a filename or decoding arbitrary binary as text |
| [`errors.py`](errors.py) | Explicit reasons for preserving a file for review |
| [`html.py`](html.py) | Self-contained email rendering with a deliberately small inert HTML allowlist |
| [`process.py`](process.py) | The `ingest.process` job: convert, OCR, thumbnail, vault write, quarantine and retry |
| [`ocr.py`](ocr.py) | OCR policy and limited fallbacks, executed in an isolated process by the spike |
| [`safety.py`](safety.py) | Bound expensive parsing and terminate the entire OCR subprocess group on timeout |
| [`spike.py`](spike.py) | A measurable OCR experiment; never inserts documents or chooses the production backend |
| [`text.py`](text.py) | Extract page text without invoking another OCR pass |
| [`thumbs.py`](thumbs.py) | Render a bounded first-page preview |

## Extending

Follow the [`document-pipeline`](../../../../../.agents/skills/document-pipeline/SKILL.md) skill: one entry point, nothing lost, every step repeatable.
