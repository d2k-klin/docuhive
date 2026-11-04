# OA-02 — OCR spike, ingest pipeline, vault (OA-M1, OA-M3)

## OA-M1 — OCR spike + go/no-go gate

**Goal:** prove, on real documents, that our own ingest is good enough before building on it. **Size:** about 1 week.

### Tasks
1. **Worker image** `services/docuhive/Dockerfile` (multi-stage, `python:3.12-slim-bookworm`):
   - apt: `tesseract-ocr`, `tesseract-ocr-deu`, `tesseract-ocr-eng`, `ghostscript`, `unpaper`, `pngquant`, `qpdf`, `libheif1`, `fonts-dejavu-core`
   - pip: `ocrmypdf`, `pypdfium2`, `pikepdf`, `img2pdf`, `pillow`, `pillow-heif`, `filetype`
   - The image runs as a non-root user `docuhive` (uid 1000). Pin `ocrmypdf` and Tesseract versions in the image tag notes.
2. **Ingest steps as pure functions** (they become the real pipeline in OA-M3, so write them properly now) in `docuhive/ingest/`:
   - `detect.py`: `detect(path) -> Detected(mime, ext, kind)`. Uses `filetype` (magic bytes), with fallbacks for text-like formats:
     - `.eml` = starts with RFC 822 headers (`From:`, `Received:`, `MIME-Version:`)
     - HTML = `<html` or `<!doctype html` within the first 1 KB
     - TXT = valid UTF-8 with no NUL bytes

     The file extension is never trusted.
   - `convert.py`: `to_pdf(path, detected) -> Path`:
     - **PDF**: open with pikepdf. If it is encrypted, try an empty password. On failure, raise `Quarantine("encrypted")`. A broken xref is repaired via `pikepdf.open(...).save()`.
     - **Images**: HEIC/HEIF → JPEG via pillow-heif, then EXIF-transpose, then `img2pdf`. TIFF is multi-page; each frame becomes a page.
     - **Office** (docx/xlsx/pptx/odt/ods): Gotenberg `POST /forms/libreoffice/convert` (timeout 120 s).
     - **HTML**: Gotenberg `POST /forms/chromium/convert/html` with the file as `index.html`. External resources are disabled (Gotenberg is configured with `--chromium-deny-list=^.*` except `file://`).
     - **`.eml`**: parse with `email` (`policy=default`). Render a header block (From, To, Date, Subject) plus the HTML body (or the text body wrapped in `<pre>`) into a self-contained HTML document. `cid:` images are replaced by data URIs, and remote images are removed. Convert via the HTML route. Attachments inside an uploaded `.eml` are **not** extracted in v1.
     - **TXT**: wrap in `<pre>` → HTML route.
     - **Unknown type**: `Quarantine("unsupported_type:<mime>")`.
   - `ocr.py`: `ocr(pdf_in, pdf_out, languages)` calls `ocrmypdf.ocr(...)` in-process. The settings, and the fallback on failure:

     | Parameter | Value |
     |-----------|-------|
     | `output_type` | `"pdfa-2"` |
     | `skip_text` | `True` |
     | `rotate_pages` | `True` |
     | `deskew` | `True` |
     | `clean` | `False` (keep the originals' look) |
     | `language` | from settings |
     | `jobs` | `OCR_JOBS` |
     | `optimize` | `1` |
     | `tesseract_timeout` | `180` |

     - On `PriorOcrFoundError` or similar, retry with `force_ocr=False, skip_text=True`.
     - On a deskew-related failure, retry without `deskew`.
     - On `EncryptedPdfError`, raise `Quarantine("encrypted")`.
     - If PDF/A conversion fails, fall back to `output_type="pdf"` and record `archive_pdfa=false`.
   - `text.py`: `extract_text(pdf) -> str` with pypdfium2, page by page, joined with `\f`. Normalise whitespace and keep line breaks.
   - `thumbs.py`: `thumbnail(pdf, out_webp, width=480)`. Renders page 1 with pypdfium2 and saves WebP at quality 80.
   - **Safety limits:** `Image.MAX_IMAGE_PIXELS = 200_000_000`, a max page count of 500 (otherwise quarantine with `too_many_pages`), and a per-step wall-clock timeout via `concurrent.futures` with process isolation for OCR.
3. **Spike CLI**: `docuhive spike ingest <input_dir> --out <out_dir>` runs detect → convert → OCR → text → thumb for every file. It writes `report.csv` and `report.md` with these columns:
   - file, mime, pages, status, error
   - seconds total and per page
   - text chars, and text chars per page (low values flag OCR failure)
4. **OCR quality**: hand-transcribe 10 pages (a mix of scans, phone photos and German/English) into `overlay/evals/ocr/<name>.txt`. A script `evals/ocr/cer.py` computes the character error rate after whitespace and case normalisation (Levenshtein in pure Python is fine). OA owns `evals/ocr/`.
5. **Sample set** (from you, private, in the overlay; never committed to the public repo), 50 documents in total:

   | Count | Kind |
   |-------|------|
   | 15 | born-digital PDFs (invoices, statements) |
   | 10 | flatbed or scanner scans |
   | 10 | phone photos (skewed, shadows, multi-page) |
   | 5 | office files |
   | 5 | `.eml` / HTML receipts |
   | 5 | odd cases: encrypted PDF, huge PDF, mixed text and scan, rotated pages, HEIC |

6. **Benchmark** on the target always-on host (Q2) or the closest equivalent.

### Gate (write `docs/decisions/0001-ocr-gate.md` with the numbers)

| Criterion | Pass |
|-----------|------|
| Ingest success without manual action (encrypted files count as expected quarantine) | ≥ 95% |
| CER on scans | ≤ 3% |
| CER on phone photos | ≤ 8% |
| Seconds per page (OCR'd pages, target host) | ≤ 10 s |
| Born-digital PDFs keep their text (no re-OCR) | 100% |

- **GO** → OA-M3.
- **NO-GO** → the fallback in [../shared/README.md](../shared/README.md#if-the-ocr-gate-fails-oa-m1--no-go). Implement the contracts as a Paperless-ngx adapter. Tell CL via an issue labelled `contract`; CL's code does not change.
- If the result is close, try tuning (`clean=True`, `--oversample 300`, the Tesseract `tessdata_best` models) before deciding.

---

## OA-M3 — Ingest pipeline, vault, documents service, events

**Goal:** the real pipeline (plan §6.1) and the vault (plan §5), with every contract from §2.4 and §2.5 implemented. **Unblocks:** I3, I4.

### 3.1 Vault — `docuhive/vault/`
- **Layout**: `vault/<YYYY>/<doc_id>/` where `YYYY` is the year of `added_at` (stable; it never changes when the document date changes).

  | File | Contents |
  |------|----------|
  | `original.<ext>` | the received bytes |
  | `archive.pdf` | the OCR'd copy |
  | `thumb.webp` | page-1 thumbnail |
  | `meta.json` | metadata |

  Also: `vault/_system/VAULT_ID` (a UUID), `vault/_system/FORMAT` (`1`), `vault/consume/`, `vault/library/`.
- `docuhive vault init`:
  - Refuses if the directory is non-empty and has no `_system/`.
  - Writes `VAULT_ID` and `FORMAT`, and stores `vault_id` in DB `settings`.
- **Health:** `vault.check() -> VaultStatus(ok, reason)`.
  - Every vault-writing job calls it first.
  - It checks that `VAULT_DIR/_system/VAULT_ID` exists and matches the DB value, and that a test write in `_system/.probe` succeeds (cached for 30 s).
  - On failure, the job calls `ctx.defer(now()+2min, "vault unavailable")`. Uploads keep landing in staging.
  - `GET /api/system/vault` exposes the status, and the UI shows a banner (OA-M5).
- **Atomic write:** `write_atomic(path, data | src_path)`:
  1. Write to `path.with_suffix(path.suffix + ".tmp-<uuid>")` in the same directory.
  2. `flush` + `os.fsync`, then `os.replace`, then fsync the directory (best effort on SMB).
  3. Verify by re-reading the sha256 for originals and archive copies.
- **`meta.json`:**
  - Pydantic `MetaV1`, matching the example in plan §5. Also publish its JSON Schema at `vault/meta.schema.json` (generated).
  - `render_meta(doc_id) -> MetaV1` builds it from the DB (documents, tags, correspondent, facts, sources, notes and the `ai` provenance stored in `documents`. Store provenance in a `ai_provenance jsonb` column added in this milestone's migration).
  - **Rule:** `meta.json` is always rendered from the DB after a DB change, and `vault rebuild` is the inverse. Writing goes: DB commit, then render, then atomic write.
  - If the write fails, enqueue `vault.repair_meta {document_id}` (it is retried; the vault check defers it).
- **Rebuild:** `docuhive vault rebuild [--dry-run]`:
  1. Walk `vault/*/*/meta.json`.
  2. Validate each file and upsert users (by username; missing users are created disabled), documents, tags, correspondents, facts, sources and notes.
  3. Re-extract `content` from `archive.pdf`, and recompute `content_tsv`.
  4. Enqueue `document.stored` with `hints={"rebuild":"true"}` so CL re-embeds (CL's handler skips classification when `rebuild` is set).
  5. Report counts and errors.
- **Schema migrations:** `meta.json.schema` is an int. `vault/migrate.py` holds an ordered list of `fn(dict)->dict` functions. Reading always upgrades in memory; `docuhive vault migrate` rewrites the files.

### 3.2 Staging + submit — `docuhive/ingest/submit.py`
- `incoming_dir()` returns `STAGING_DIR/incoming/` (created on demand).
- `submit(files, req)` follows contracts §2.4:
  1. Validate: count, size (`MAX_UPLOAD_MB`), and detected types (`combine` requires all images).
  2. Compute sha256. For `combine`, hash the concatenation of the file hashes in order.
  3. **Dedupe**: if `SELECT id FROM documents WHERE owner_id=:o AND sha256=:h` finds a row, delete the files and return `duplicate`.
  4. Allocate a ULID, move the files to `STAGING_DIR/<doc_id>/input-<n>.<ext>`, and insert a `documents` row (`status=staged`, `mime`, `sha256`, `owner_id`, `shared`) plus `doc_sources`.
  5. Enqueue `ingest.process {document_id, combine, hints}` on queue `ocr`.
  6. Return `staged`.
- A race on the dedupe check is handled by the unique constraint: catch `IntegrityError`, then return `duplicate`.

### 3.3 Pipeline job — `ingest.process` (queue `ocr`, `timeout_s=1800`, `max_attempts=3`)
1. Set `status=processing`.
2. Convert the input(s) to one PDF (`combine` → img2pdf over all images in order).
3. OCR into `STAGING_DIR/<doc_id>/archive.pdf`, then extract text and render the thumbnail. Set `pages`.
4. Run `vault.check()`. If it fails, defer (the staged files stay).
5. Write `original.<ext>` (for combine: `original.pdf` = the img2pdf result without OCR, and the individual images as `original-<n>.<ext>`), `archive.pdf`, `thumb.webp` and `meta.json` with atomic writes. Verify the hashes.
6. In one DB transaction:
   - set `status=stored`, `vault_path`, `content`, `fts_config='dh_simple'` (CL updates the language later via `apply_metadata`), and `content_tsv`
   - set `title` = the original filename without its extension (until AI sets one)
   - add an `audit_log` row `ingest.stored`
7. Delete `STAGING_DIR/<doc_id>/`.
8. Enqueue `document.stored` on queue `ai` with the payload from contracts §4.
9. **On `Quarantine(reason)`**, or after the final failed attempt:
   - set `status=quarantined` and `quarantine_reason`, and keep the staging files
   - enqueue `document.quarantined`
   - `POST /api/system/quarantine/{id}/retry` (OA-M4) re-enqueues `ingest.process`

**FTS vector** (`search/fts.py: tsv_sql(doc)`), recomputed on every content, title or correspondent change:
```sql
setweight(to_tsvector(:cfg, coalesce(title,'')), 'A') ||
setweight(to_tsvector(:cfg, coalesce(:correspondent,'')), 'B') ||
setweight(to_tsvector(:cfg, coalesce(content,'')), 'C')
```
Content is truncated to 1 MB for the tsvector (the Postgres tsvector limit). A `ponytail:` comment notes the truncation.

### 3.4 Documents service — `docuhive/documents/`
Implements contracts §2.5:
- `get`, `get_content` (honours `max_chars`), `iter_ids` (server-side cursor, and filters reuse the search filter builder from OA-M4. Until then, support status and `added_since` only).
- `get_for_user` is implemented in OA-M4, together with auth.
- **`apply_metadata`** follows the exact semantics in contracts §2.5. Details:
  - Tag names: trimmed, max 64 chars. The slug is lowercase with `-` replacing spaces. A merged tag (`merged_into`) resolves to its target.
  - Correspondent `norm_name`: `casefold`, collapse whitespace, strip legal suffix punctuation (keep the suffix words themselves). Merged correspondents resolve to their target.
  - Facts: upsert by `(document_id, field)`, with `value_num` and `value_date` parsed from the canonical string. A `None` fact deletes the row.
  - If `language` changes, `fts_config` is mapped (OA-M2 §2.3 map) and `content_tsv` recomputed.
  - `audit_log.before`/`after` hold only the changed fields.
  - `meta.json` is re-rendered after commit (via a job if the vault is unavailable).
  - `document.metadata_changed` is enqueued only if something changed.
- **Vocabulary helpers:** `merge_tags(src_ids, target_id)` and `merge_correspondents(...)`. They re-point the links, set `merged_into`, and re-render the `meta.json` of affected docs (as a job, batched).

### 3.5 Tests
- **Unit:**
  - detection on fixtures (a PDF with a wrong extension, `.eml` without an extension, HTML, HEIC)
  - convert routing
  - atomic write (simulated crash leaves no partial file)
  - `meta.json` render ↔ rebuild round-trip
  - dedupe
  - every `apply_metadata` rule (manual skip, force, user adds to manual, tag create, correspondent normalise, facts delete, events emitted only on change)
- **Integration** (compose.test with Gotenberg), using the fixture corpus `tests/fixtures/ingest/`: synthetic files for each type, plus rotated-scan and mixed text/scan PDFs generated by a script (no real data).
- **Drills (scripted):**
  - Make the vault unavailable (rename `_system/VAULT_ID`), upload 3 docs: they stay staged. Restore it: they are stored within 3 minutes.
  - Drop the DB, `db upgrade`, `vault rebuild`: document count, titles, tags and facts are equal before and after.

### Acceptance
- `docuhive ingest <file> --owner dev` (a CLI wrapper over `submit`) on each fixture type ends in `stored` with an `archive.pdf` that has a text layer, or in `quarantined` with the right reason.
- A born-digital PDF is not re-OCR'd (its text is identical to the original's text).
- Every contract test from `tests/contracts/` for ingest and documents passes against the **real** implementation.
- **I3 and I4 marked done** in `STATUS.md`.
