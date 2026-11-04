# Archive tools: plan

**Overview.** Five features from the [feature list](../FEATURES.md): vault health check, custom fields, saved views, near-duplicate detection and filtered export. They sit on the existing schema (`documents`, `doc_facts`, the vault layout in [the ingest plan](../Developer-OA/02-ingest-and-vault.md)), so they work as soon as documents are stored. Until document intake lands they run against an empty archive and are tested with synthetic rows and files.

## Shared rules

- Every query applies `auth.visible_docs(user)`, exactly like search and knowledge bases.
- Nothing here modifies the vault. The health check and export only read it.
- Saved filters reuse `SearchFilters` and the knowledge-base filter validation.
- New core tables come in one migration, `0003_archive_tools`.
- API errors use the `{code, message, details}` shape with plain copy.

## 1. Vault health check

- `docuhive.vault.check(full: bool) -> VaultReport`, read-only:
  - every stored document's folder, `original.*`, `archive.pdf` and `meta.json` exist;
  - `meta.json` parses and names the same document;
  - with `full`, the original's SHA-256 matches `documents.sha256`;
  - document folders under `vault/<year>/` with no database row are reported as orphans;
  - a missing or unreadable vault is one clear problem, not one per document.
- The report is stored in `settings` (`vault.health`) with counts and at most 200 problems.
- `docuhive vault check [--full]` prints the report and exits non-zero on problems.
- Periodic job `vault.check`: weekly, full.
- `GET /api/vault/health` (admin): the last report. `POST /api/vault/health` (admin): queue a check.

## 2. Custom fields

- Table `custom_fields`: `name` (snake_case, unique), `label`, `type` (a `FactType`), `description`, `document_types` (empty means all types), `remind_days_before`, timestamps.
- `taxonomy.document_type()` appends matching custom fields to the type's facts, so extraction, review, reminders and Ask pick them up without other changes. A name that clashes with a built-in fact of that type is rejected.
- `GET /api/custom-fields` (signed in), `POST`, `PATCH`, `DELETE /api/custom-fields/{id}` (admin). Deleting a field keeps values already extracted.
- Web: `/settings/fields`.

## 3. Saved views

- Table `saved_views`: `owner_id`, `name`, `filters` (`SearchFilters`), `pinned`, `shared`, timestamps.
- Owner-only changes; shared views are visible to the household, and sharing never grants document access.
- `GET/POST /api/views`, `PATCH/DELETE /api/views/{id}`, `GET /api/views/{id}/documents` (paginated: title, date, category, type, sender, tags).
- Web: `/views` manager, `/views/[id]` document table, pinned views listed in the sidebar.

## 4. Near-duplicate detection

- Table `duplicate_pairs`: `document_id`, `other_id` (ordered pair), `score`, `reasons`, `status` (`open`, `dismissed`, `confirmed`).
- Job `duplicates.scan {document_id}`, queued after extraction and on demand. Candidates are visible documents of the same owner; signals:
  - same sender, and the same total amount or a document date within 7 days;
  - semantic similarity of at least 0.92 (when embeddings exist).
  - A pair needs two signals, or a similarity of at least 0.97.
- `GET /api/duplicates` (open pairs the user can see both sides of), `POST /api/duplicates/{id}` with `dismissed` or `confirmed`. Confirming never deletes anything; trashing is the user's choice.
- Learning note 10 and a runnable example explain the scoring.

## 5. Filtered export

- `POST /api/export` with `filters` (or a saved view / knowledge base id) streams a ZIP:
  - `documents/<date> <title> (<id>).pdf`: each archive copy, with safe, unique filenames;
  - `documents.csv`: title, date, category, type, sender, tags, source and one column per fact, with spreadsheet formula injection neutralised.
- At most 1000 documents per export; above that the API returns `export_too_large`.
- Missing archive files are listed in `MISSING.txt`, never silently skipped.
- Web: an Export button on saved views and knowledge bases.

## Done when

- Unit tests (no network) and PostgreSQL integration tests cover permissions, empty archives and failure paths.
- Generated API types are refreshed, the web checks pass, and folder READMEs, CHANGELOG, feature list and status are updated.
