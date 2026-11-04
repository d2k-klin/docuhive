# CL-02 — Taxonomy, classification, extraction, review queue (CL-M2)

**Goal:** every stored document gets AI suggestions for its category, type, correspondent, tags, title, date, language and facts. Confident suggestions are applied automatically (once enabled); everything else goes to a fast review queue.
**Uses:** I3 (`documents.*`, events). Use `FakeDocuments` until OA-M3 is done. For the UI, the root layout stands in until I6.
**Provides:** I7 (taxonomy) **early**: do 2.1 first.

## 2.1 Taxonomy (I7) — `docuhive/taxonomy/`

- `load()` calls `config.load_yaml("taxonomy.yaml")`, then validates into `contracts.Taxonomy`, and caches the result. `reload()` clears the cache.
- **Validation:**
  - unique category ids, document type ids and tags
  - category ids match `^[a-z0-9-]+(/[a-z0-9-]+)*$`
  - every parent of a child category exists (e.g. `utilities` for `utilities/electricity`)
  - fact names are snake_case and unique per type
  - `languages` is non-empty and ISO 639-1
- `GET /api/taxonomy` returns the taxonomy plus a `tree` (categories nested by `/`) for the UI.
- `docuhive taxonomy check [path]` validates an overlay file and prints a diff against the default.
- Write a copy of the default file to `tests/fixtures/taxonomy.yaml` for OA's fallback. That fixture is CL-owned, and you keep it in sync.

### Default taxonomy

`config/defaults/taxonomy.yaml`. The overlay replaces these lists entirely (overlay rules: lists replace).

```yaml
version: 1
languages: [de, en]
default_currency: EUR
categories:
  - { id: finance, label: Finance }
  - { id: finance/banking, label: Banking, description: "Bank statements, account letters, cards" }
  - { id: finance/tax, label: Tax, description: "Tax returns, assessments, tax office letters" }
  - { id: finance/investments, label: Investments, description: "Brokerage, pension funds, securities" }
  - { id: finance/loans, label: Loans & credit }
  - { id: income, label: Income }
  - { id: income/payslips, label: Payslips }
  - { id: income/benefits, label: Benefits & pension }
  - { id: housing, label: Housing }
  - { id: housing/rent, label: Rent & lease }
  - { id: housing/property, label: Property & mortgage }
  - { id: utilities, label: Utilities }
  - { id: utilities/electricity, label: Electricity }
  - { id: utilities/gas-heating, label: Gas & heating }
  - { id: utilities/water, label: Water }
  - { id: utilities/internet-phone, label: Internet & phone }
  - { id: insurance, label: Insurance }
  - { id: insurance/health, label: Health insurance, restricted: true }
  - { id: insurance/vehicle, label: Vehicle insurance }
  - { id: insurance/home, label: Home & liability }
  - { id: insurance/life, label: Life & disability }
  - { id: health, label: Health, restricted: true, description: "Medical reports, prescriptions, invoices from doctors" }
  - { id: vehicle, label: Vehicle, description: "Registration, service, purchase" }
  - { id: employment, label: Employment, description: "Contracts, references, HR letters" }
  - { id: education, label: Education, description: "Certificates, diplomas, courses" }
  - { id: legal, label: Legal & contracts, description: "Contracts not covered elsewhere, legal letters" }
  - { id: government, label: Government }
  - { id: government/identity, label: Identity documents, restricted: true }
  - { id: government/official, label: Official letters }
  - { id: purchases, label: Purchases }
  - { id: purchases/receipts, label: Receipts }
  - { id: purchases/warranties, label: Warranties & manuals }
  - { id: travel, label: Travel }
  - { id: personal, label: Personal correspondence }
  - { id: other, label: Other }
document_types:
  - id: invoice
    label: Invoice
    facts:
      - { name: amount_total, type: money, required: true }
      - { name: amount_tax, type: money }
      - { name: invoice_number, type: string }
      - { name: invoice_date, type: date }
      - { name: due_date, type: date, remind_days_before: [7, 1] }
      - { name: period_start, type: date }
      - { name: period_end, type: date }
      - { name: iban, type: iban, description: "Payee IBAN if printed" }
  - id: receipt
    label: Receipt
    facts:
      - { name: amount_total, type: money, required: true }
      - { name: purchase_date, type: date }
      - { name: merchant, type: string }
  - id: bank-statement
    label: Bank statement
    facts:
      - { name: period_start, type: date }
      - { name: period_end, type: date }
      - { name: closing_balance, type: money }
      - { name: account_iban, type: iban }
  - id: payslip
    label: Payslip
    facts:
      - { name: period_month, type: date, description: "First day of the month" }
      - { name: gross, type: money }
      - { name: net, type: money }
  - id: contract
    label: Contract
    facts:
      - { name: start_date, type: date }
      - { name: end_date, type: date, remind_days_before: [90, 30] }
      - { name: notice_period_days, type: number }
      - { name: monthly_cost, type: money }
      - { name: contract_number, type: string }
  - id: insurance-policy
    label: Insurance policy
    facts:
      - { name: policy_number, type: string }
      - { name: premium, type: money }
      - { name: premium_interval, type: string, description: "monthly | quarterly | yearly" }
      - { name: renewal_date, type: date, remind_days_before: [60, 14] }
  - id: tax-document
    label: Tax document
    facts:
      - { name: tax_year, type: number }
      - { name: amount_due, type: money }
      - { name: due_date, type: date, remind_days_before: [14, 3] }
  - { id: letter, label: Letter }
  - { id: certificate, label: Certificate }
  - id: id-document
    label: ID document
    facts:
      - { name: document_number, type: string }
      - { name: expiry_date, type: date, remind_days_before: [180, 60] }
  - { id: medical-report, label: Medical report }
  - id: warranty
    label: Warranty
    facts:
      - { name: warranty_end, type: date, remind_days_before: [30] }
  - { id: manual, label: Manual }
  - { id: other, label: Other }
tags: [important, tax-relevant, private, recurring, archive-only]
```

## 2.2 Pipeline orchestration — `docuhive/agents/pipeline.py`

| Job (queue `ai`) | Trigger | Does |
|------------------|---------|------|
| `document.stored` handler | OA event | If `hints.rebuild == "true"`, enqueue only `index.embed` (from CL-M5). Otherwise enqueue `ai.classify {document_id}` (dedupe key `classify:<id>`) |
| `ai.classify` | above, or reclassify | classify (§2.3). On success, enqueue `ai.extract` if the (applied or suggested) document type has facts, otherwise `index.embed` |
| `ai.extract` | after classify | extract (§2.4), then enqueue `index.embed` |
| `document.metadata_changed` handler | OA event | If the user changed `document_type`, enqueue `ai.extract` (dedupe). Mark the pending review items for the changed fields as `superseded`. If `title`, `correspondent` or `category` changed, enqueue `index.embed` (CL-M5) |
| `document.quarantined` handler | OA event | Until CL-M7 only log it; from CL-M7, notify |
| `document.purged` handler | OA event | delete `review_items` and `doc_chunks` (CL-M5); `ai_runs.document_id` is set to null by the FK |

**Behaviour when skipping:**
- `NoAllowedRoute` → add a review item of kind `notice` ("AI skipped: restricted document, no local model configured"), with no retry.
- `BudgetExceeded` → defer (CL-01 §1.7).
- `AI ENABLED=false` → no-op.

## 2.3 Classify agent — `docuhive/agents/classify.py`, prompt `config/defaults/prompts/classify.md`

### Input building
- `content = documents.get_content(id)`. Take the first `head_chars` (default 6000) and the last `tail_chars` (default 1500), joined by `\n…\n`. The limits are configurable per route in `routing.yaml` (`tasks.classify.context`), so bigger models can get more.
- **Vocabulary** passed to the prompt:
  - the categories (`id — label: description`)
  - the document types (`id — label`)
  - the allowed tags
  - the **top 200 correspondents** by usage (from OA's `correspondents` + `documents`, read-only SQL)
- Metadata hints: original filename, source kind, email subject and from (from `DocumentView.source`), and `hints.doc_hint`.

### Output model (Pydantic)
```python
class ClassifyOut(BaseModel):
    title: str = Field(max_length=120)          # human title, in document language, no filename noise
    category: str
    document_type: str
    correspondent: str | None                   # issuer/sender organisation or person
    tags: list[str] = []
    document_date: date | None                  # issue date printed on the document
    language: str                               # ISO 639-1
    confidence: dict[str, float]                # per field above, 0..1
    proposed_new_terms: list[NewTerm] = []      # {kind: category|document_type|tag, value, reason}
    reasoning: str = Field(max_length=400)      # short, stored in ai_runs only
```

### Validation (after the model returns; failure triggers the harness's one retry with the error text)
- `category`, `document_type` and `tags` must be in the taxonomy. An unknown tag is dropped and turned into a `proposed_new_terms` entry instead of causing a failure.
- `document_date`: not more than 1 year in the future, not before 1950. Otherwise it is set to null with confidence 0.
- `language` must be in `taxonomy.languages`, or any ISO 639-1 code (FTS falls back to the simple config).
- **Correspondent matching:**
  1. Normalise the name (same rule as OA: casefold + collapsed whitespace).
  2. Trigram-match it against the existing correspondents (`similarity ≥ 0.75`, SQL using `pg_trgm`).
  3. If there is a match, use the existing name.
  4. Otherwise keep the new name, and **cap its confidence at 0.7**, so new correspondents get reviewed until auto-apply is trusted.

### Apply policy — `routing.yaml` → `tasks.classify.apply`
```yaml
apply:
  auto: false            # stays false until CL-M3 evals pass the gate; then true
  threshold: 0.80
  per_field: { document_date: 0.90, correspondent: 0.85 }
```
- **`auto: false`:** nothing is applied. Every field becomes a `review_item` (`kind=field`). **Exception:** `language` is always applied (it only affects the FTS config), with `actor="ai:classify"`.
- **`auto: true`:** fields at or above the threshold are applied via **one** `apply_metadata(..., actor="ai:classify", provenance=...)` call. Fields below it become review items. Fields skipped because they are manual are ignored silently.
- `proposed_new_terms` → `review_item` (`kind=new_term`).
- `title` is applied only if the current title is still the filename default, or was set by AI. User-set titles are protected by `manual_fields` anyway.

## 2.4 Extract agent — `docuhive/agents/extract.py`, prompt `prompts/extract.md`

- The schema is built dynamically from `taxonomy.document_types[type].facts` with `pydantic.create_model`:
  - each fact becomes `{value: str | None, currency: str | None (money only), confidence: float}`
  - plus `evidence: str | None`, a short quote from the document (≤ 120 chars) to help review
- Input: the full content up to `tasks.extract.context.max_chars` (default 12000). Invoices often keep totals on the last page, so use head + tail as in classify when truncating.
- **Validators** (`docuhive/agents/validators.py`, a pure module with unit tests):
  - **money:** parse German and English formats (`1.234,56`, `1,234.56`, `1234.56 €`) into a `Decimal` with 2 places, `> 0`. Currency is ISO 4217 `^[A-Z]{3}$`, mapping symbols (`€`→EUR, `$`→USD, `£`→GBP, `CHF`). If the currency is missing, take it from the document context, otherwise use `taxonomy.default_currency`.
  - **date:** ISO, or parse `DD.MM.YYYY`, `D. Monat YYYY` (German month names), `Month D, YYYY`. Same sanity range as classify.
  - **number:** a Decimal.
  - **iban:** strip spaces, uppercase, mod-97 check, country length table (a small dict).
  - **string:** trimmed, max 200 chars.
  - An invalid value becomes `None`, with a review item (`kind=field`, reason `invalid: <why>`).
- Applied as `MetadataPatch(facts={...})` using the same apply policy and thresholds (`tasks.extract.apply`). A required fact that is missing creates a review item "missing required fact".

## 2.5 Review queue — `docuhive/review/`

### Table (intel migration `0002_review`)
```sql
CREATE TABLE review_items (
  id           bigserial PRIMARY KEY,
  document_id  text NOT NULL,              -- FK documents(id) ON DELETE CASCADE
  kind         text NOT NULL,              -- field | new_term | notice
  field        text,                       -- e.g. category, facts.amount_total
  suggested    jsonb,                      -- {"value": ..., "currency": ...}
  current      jsonb,                      -- value at suggestion time
  confidence   real,
  reason       text,
  evidence     text,
  ai_run_id    bigint,                     -- FK ai_runs(id) ON DELETE SET NULL
  status       text NOT NULL DEFAULT 'pending',  -- pending | accepted | rejected | superseded | dismissed
  created_at   timestamptz NOT NULL DEFAULT now(),
  resolved_at  timestamptz,
  resolved_by  bigint                      -- users.id
);
CREATE INDEX review_pending ON review_items (status, created_at) WHERE status = 'pending';
CREATE UNIQUE INDEX review_one_pending ON review_items (document_id, kind, field) WHERE status = 'pending';
```
A new suggestion for the same `(document, kind, field)` supersedes the old pending one.

### API (`/api/review`; every query joins `documents` with `auth.visible_docs(user)`, and only the document owner may resolve)
| Endpoint | Notes |
|----------|-------|
| `GET /api/review/queue?cursor=&kind=&category=` | grouped by document: `{document: DocumentSummary, items: [...]}`, oldest first |
| `GET /api/review/count` | pending count (for the badge and dashboard) |
| `POST /api/review/items/{id}/accept` | optional body `{value}` to edit before accepting → `apply_metadata(actor="user:<id>")`. The field becomes manual. Status `accepted` |
| `POST /api/review/items/{id}/reject` | status `rejected` |
| `POST /api/review/documents/{doc_id}/accept-all` · `/reject-all` | one `apply_metadata` call for all of the document's field items |
| `POST /api/review/terms/{id}/accept` | `new_term` → **writes to the overlay is not possible from the app.** It is recorded as `accepted`, and the UI shows a YAML snippet to add to `overlay/taxonomy.yaml`. Tags are the exception: an accepted tag is added to the document right away (OA creates the tag), and the snippet tells the user to add it to the taxonomy so the AI can use it next time |
| `POST /api/review/reclassify` | `{document_ids?: [...], filters?: SearchFilters, tasks: ["classify","extract"]}` → enqueue jobs (dedupe), returns a count. Bulk is admin or owner-only |

### Review UI — `app/(app)/review/page.tsx` (CL)
- **Layout:** document preview on the left (thumbnail, or the iframe of the archive), suggestions on the right as rows:
  - field label, current → suggested
  - a confidence bar
  - the reason or evidence, in small text
  - Accept / Edit / Reject buttons
- **Keyboard:** `j`/`k` next/previous document, `a` accept all, `r` reject all, `1–9` toggle an item, `e` edit the focused item, `?` shows help.
- Edit controls:
  - category and type: a select from the taxonomy tree
  - correspondent: a combobox (OA's `/api/vocabulary/correspondents?q=`)
  - date: native `<input type="date">`
  - money: amount + currency
- **Goal:** under 10 s per document (WEB/plan Phase 3). Prefetch the next 3 documents.
- **Notices** (`kind=notice`) are shown at the top with a "Dismiss" button.
- Nav: uncomment "Review", with the badge from `/api/review/count`.

### Slot components (I9)
- `components/intel/DashboardWidgets.tsx` → `IntelDashboardWidgets`: a "Needs review: N" card linking to `/review`. Mail and reminders widgets are added in later milestones.
- `components/intel/DocumentAIPanel.tsx`:
  - pending suggestions for this document, with inline accept/reject
  - AI history from `GET /api/ai/runs?document_id=` (task, model, local badge, confidence, date)
  - a "Re-run AI" button → reclassify

## 2.6 Tests
- Taxonomy validation (each rule), the overlay replace behaviour, and that the fixture equals the default file.
- Validators: a table-driven test with ≥ 40 cases (German and English money formats, dates, IBANs valid and invalid).
- Classify with FakeModel:
  - unknown category → retry → success
  - unknown tag → proposed term
  - correspondent fuzzy match
  - future date nulled
  - `auto=false` → only review items, plus the language applied
  - `auto=true` → threshold split
  - manual fields not touched (FakeDocuments implements the manual-field semantics)
- Pipeline: event → classify → extract → (embed enqueued), `rebuild` hint path, restricted + no local → notice.
- Review API: permissions (a non-owner cannot resolve), supersede, accept-with-edit makes the field manual.
- Contract tests: run the classify flow against the **real** OA documents service once I3 is marked done.

## Acceptance
- **J1:** upload a PDF (OA CLI), and within 5 min a review queue entry with sensible suggestions appears. Accepting them updates the document (visible in OA's document page and in `meta.json`).
- A restricted-category document produces only `local=true` `ai_runs` rows (asserted in a test).
- The review UI clears 20 documents in under 4 minutes in a manual test.
- **I7 marked done** (early), then CL-M2 done.
