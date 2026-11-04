# DocuHive — Two-developer work split

Status: v0.1 · 2026-11-03

Two developers build DocuHive in parallel:

| Developer | Track | One-line scope |
|-----------|-------|----------------|
| **OA** | **Core platform** | Repo/platform, ingest + OCR + vault, database, auth, documents API, full-text/hybrid search, web shell + document UI, PWA capture, deployment, backups, security. |
| **CL** | **Intelligence & connectors** | AI provider layer + agent harness, taxonomy, classification + extraction, review queue, eval harness, email connectors + backfill, embeddings + semantic search, Ask/analyses, reminders + notifications. |

The two tracks are designed so that **neither developer ever waits for the other**. They may work at
very different speeds. Every dependency between the tracks goes through a written **contract**
([contracts.md](contracts.md)), and every contract has a **fallback** (a fake or stub). The consumer
uses the fallback until the provider ships the real thing.

## Reading order (both developers)

1. [../REQUIREMENTS.md](../REQUIREMENTS.md): what we build and why (requirement IDs referenced everywhere).
2. [../IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md): the full technical design.
3. This file: ownership, integration points, timeline.
4. [contracts.md](contracts.md): the exact interfaces between the tracks. **Binding.**
5. [working-agreement.md](working-agreement.md): branching, migrations, shared files, pace rules.
6. Your own folder: [../Developer-OA/](../Developer-OA/README.md) or [../Developer-CL/](../Developer-CL/README.md).
7. The other developer's `README.md` and `STATUS.md`, so you know what they provide and when.

## Ownership matrix

| Area | Owner | Requirement IDs | Plan file |
|------|-------|-----------------|-----------|
| Repo skeleton, CI, tooling, `AGENTS.md` | OA | NFR-06, NFR-10 | OA/01 |
| Config + overlay loader + plugin loader | OA | EXT-01..03 | OA/01 |
| DB engine, core migrations, job queue, worker, scheduler | OA | AUTO-02, NFR-07 | OA/01 |
| OCR spike + go/no-go gate | OA | ING-03, NFR-09 | OA/02 |
| Ingest pipeline, vault, `meta.json`, quarantine, dedupe | OA | STO-*, ING-* | OA/02 |
| Documents service (`apply_metadata`, read APIs) | OA | DOC-03, CLS-06 (manual protection) | OA/02 |
| Auth, sessions, API tokens, permissions | OA | AUTH-* | OA/03 |
| Documents/vocabulary/system REST API | OA | DOC-*, CAP-04 | OA/03 |
| Full-text search, hybrid fusion, search API | OA | SRCH-01, SRCH-03, SRCH-04 | OA/03 |
| Web shell, BFF proxy, API client, documents/search/upload/settings UI | OA | WEB-*, DOC-* | OA/04 |
| PWA capture, consume folder | OA | CAP-01..03, CAP-05 | OA/04 |
| Compose, NAS, backups, drills, library view, cloud profile, hardening | OA | STO-03, STO-08, NFR-02/03 | OA/05 |
| AI providers, router, harness, privacy gate, budgets, `ai_runs` | CL | AI-* | CL/01 |
| Taxonomy schema + default taxonomy + loader | CL | CLS-02 | CL/02 |
| Classify + extract agents, review queue (API + UI) | CL | CLS-* | CL/02 |
| Eval harness, golden set, model selection | CL | NFR-09 | CL/03 |
| Email: OAuth, Gmail/Graph/IMAP, prefilter, triage, backfill, sources UI | CL | MAIL-* | CL/04 |
| Embeddings, semantic search, similar docs | CL | SRCH-02, SRCH-05 | CL/05 |
| Ask agent, facts tool, chat UI, saved analyses | CL | QA-01..04, QA-06 | CL/05 |
| Reminders, notifications | CL | QA-05, AUTO-03 | CL/06 |
| Design tokens, `/dev/ui`, `/setup` wizard shell, dashboard checklist, ⌘K palette | OA | WEB-04, WEB-05, GUIDE-01..03 | OA/04 |
| Setup checks + wizard steps for AI, models, privacy, email, notifications | CL | GUIDE-01, GUIDE-02 | CL/01, CL/04, CL/06 |
| "How was this made?" run page, Learn tab | CL | LRN-03, LRN-04 | CL/01 |
| Learning notes + examples | CL (01–08, 10, 11), OA (09, 12) | LRN-01, LRN-02 | CL/01, OA/03 |

## Integration points

The consumer never blocks: it builds against the fallback and switches over when the provider marks the item done in its `STATUS.md`.

| ID | Provider → Consumer | What | Fallback until ready |
|----|---------------------|------|----------------------|
| **I1** | OA → CL | Repo skeleton, `docuhive.contracts` models, stub modules | CL works in `spikes/cl/` (standalone) or creates the skeleton itself per the working agreement §2 |
| **I2** | OA → CL | `config.load_yaml`, `db.session`, intel Alembic env, `jobs.enqueue/handler/periodic` | `tests/fakes/core.py`: in-memory jobs that run immediately; plain `yaml.safe_load` of defaults |
| **I3** | OA → CL | `documents.get/get_content/apply_metadata`, `document.*` events | `FakeDocuments` in-memory store seeded from `evals/synthetic/` |
| **I4** | OA → CL | `ingest.submit`, `ingest.incoming_dir` | `FakeIngest` writes to `./tmp/fake-vault/` and returns a ULID |
| **I5** | OA → CL | `auth.current_user`, `auth.visible_docs`, `search.hybrid` | `DOCUHIVE_AUTH_DISABLED=true` dev user; `visible_docs` = `owner_id == user.id`; hybrid = CL's own semantic only |
| **I6** | OA → CL | Web shell, `/api/*` BFF proxy (incl. SSE), generated API client, nav | Pages render with the root layout; call the Python API at `DOCUHIVE_API_URL` directly in dev |
| **I7** | CL → OA | `taxonomy.load()` + `config/defaults/taxonomy.yaml` | OA reads `tests/fixtures/taxonomy.yaml` (a copy of the default taxonomy in [CL-02](../Developer-CL/02-classification-and-review.md#default-taxonomy)) |
| **I8** | CL → OA | `search.register_semantic(...)` implementation | Hybrid search runs FTS-only |
| **I9** | CL → OA | Web components for the slots (dashboard widgets, document AI panel, similar docs) | Placeholder components that return `null` (created by OA, owned by CL) |

Knowledge bases add **I10–I13** and milestones KB-M1…KB-M7; see [knowledge-bases.md](knowledge-bases.md).

## Milestone dependency graph

```
OA-M0 skeleton+contracts ─┬─► OA-M1 OCR spike + GATE ─► OA-M3 ingest+vault ─► OA-M4 auth/API/search ─► OA-M5 web ─► OA-M6 PWA ─► OA-M7 ops ─► OA-M8 hardening
                          └─► OA-M2 platform (db/jobs/config) ─┘
                 (I1)            (I2)                     (I3, I4)              (I5)              (I6)
                  ▼               ▼                          ▼                    ▼                 ▼
CL-M0 spikes ─► CL-M1 AI layer ─► CL-M2 taxonomy+classify+review ─► CL-M3 evals ─► CL-M4 email ─► CL-M5 semantic ─► CL-M6 ask ─► CL-M7 reminders/notify
                                    (I7 ▲ to OA)                                              (I8 ▲ to OA)      (I9 ▲ to OA)
```

Arrows into CL milestones mean "switches from the fallback to the real implementation once ready". They are **not** blockers.

**Rough effort** (part-time): OA ≈ 11–12 weeks, CL ≈ 12 weeks. There are no calendar dates. Each developer moves through their own milestones in order, at their own pace.

## Joint milestones (system checkpoints)

Joint milestones are reached whenever both sides have delivered. Neither developer waits for them; they are just checkpoints.

| Joint | Needs | Demo |
|-------|-------|------|
| **J1 First classified doc** | OA-M3 + CL-M2 | Upload a PDF via CLI → stored in the vault → auto-classified suggestion in the review queue |
| **J2 Email to archive** | OA-M3 + CL-M4 | Gmail backfill of one month → documents in the vault with provenance |
| **J3 Daily use** | OA-M5 + CL-M2 UI | Log in, upload from phone, review suggestions, search |
| **J4 Ask** | OA-M4 + CL-M6 | "How much did I spend on electricity in 2025?" answered with citations |
| **J5 v1** | all milestones | Full requirements acceptance, restore drill, security checklist |

## If the OCR gate fails (OA-M1 = NO-GO)

The fallback is the Paperless-based design (commit `2f38128`):
- OA implements the **same contracts** (`ingest.submit`, `documents.*`, `search.hybrid`, events) as an adapter over the Paperless-ngx REST API, instead of an own pipeline and vault.
- **CL's track is unaffected**, because it only talks to the contracts.
- That decision is recorded in `docs/decisions/0001-ocr-gate.md`.
