# Developer OA — Core platform track

You own the **platform and the document core**: everything that gets a file into the vault and
lets a user see, find and manage it. Developer CL builds the AI and email side on top of your
contracts.

## Project in one paragraph

DocuHive is a self-hosted, open-source, AI-first document hub. Documents arrive by email, phone
camera, scanner or upload. They are OCR'd and stored in a self-describing **vault** on a WD My Cloud
NAS (original + PDF/A + `meta.json` per document; the DB can be rebuilt from it), classified by AI
into a controlled taxonomy, and made searchable (full-text + semantic) and askable ("what did I pay
for electricity in 2025?") with local (Ollama) or cloud AI. Stack: Python (FastAPI, worker,
Strands agents) + Next.js, with Postgres (FTS + pgvector), OCRmyPDF/Tesseract and Gotenberg.
Personal configuration lives in a private overlay repo.

## Read first

1. [../REQUIREMENTS.md](../REQUIREMENTS.md) and [../IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md)
2. [../shared/README.md](../shared/README.md): the split, integration points, joint milestones
3. [../shared/contracts.md](../shared/contracts.md): **you implement most of it**
4. [../shared/working-agreement.md](../shared/working-agreement.md)
5. [../Developer-CL/README.md](../Developer-CL/README.md) and its `STATUS.md`

## Your milestones (in order)

| Milestone | File | Requirement IDs | Unblocks CL? |
|-----------|------|-----------------|--------------|
| **OA-M0** Repo skeleton + contract stubs + CI | [01-foundations.md](01-foundations.md) | NFR-06, NFR-10 | **I1** |
| **OA-M1** OCR spike + **go/no-go gate** | [02-ingest-and-vault.md](02-ingest-and-vault.md) | ING-02/03, NFR-04 | (decides the fallback) |
| **OA-M2** Platform: settings, overlay, DB, jobs, worker, CLI | [01-foundations.md](01-foundations.md) | EXT-01..03, AUTO-02, NFR-07 | **I2** |
| **OA-M3** Ingest pipeline, vault, documents service, events | [02-ingest-and-vault.md](02-ingest-and-vault.md) | STO-*, ING-*, DOC-03 | **I3, I4** |
| **OA-M4** Auth, permissions, REST API, FTS + hybrid search | [03-api-auth-search.md](03-api-auth-search.md) | AUTH-*, DOC-*, SRCH-01/03/04, CAP-04 | **I5** |
| **OA-M5** Web shell, BFF proxy, documents/search/settings UI | [04-web-and-mobile.md](04-web-and-mobile.md) | WEB-*, DOC-01..05 | **I6** |
| **OA-M6** PWA capture + consume folder | [04-web-and-mobile.md](04-web-and-mobile.md) | CAP-01..03, CAP-05 | — |
| **OA-M7** Ops: compose, NAS, backups, drills, library view | [05-ops-security-cloud.md](05-ops-security-cloud.md) | STO-03/05/08, NFR-03 | — |
| **OA-M8** Hardening + cloud profile | [05-ops-security-cloud.md](05-ops-security-cloud.md) | NFR-02, §9.3 of the plan | — |

**Ordering note:** do OA-M0 first (it is small: 1–3 days) so CL can work in the repo. OA-M1 and OA-M2 can be interleaved. The gate result must be known before OA-M3.

## Skills to load

[`repo-structure`](../../.agents/skills/repo-structure/SKILL.md) (OA-M0 and every new file), [`docuhive-ui`](../../.agents/skills/docuhive-ui/SKILL.md) (OA-M5/M6), [`guided-experience`](../../.agents/skills/guided-experience/SKILL.md), [`document-pipeline`](../../.agents/skills/document-pipeline/SKILL.md) (OA-M3/M6), [`document-editing`](../../.agents/skills/document-editing/SKILL.md), [`document-chat`](../../.agents/skills/document-chat/SKILL.md) (entry points only), [`learning-showcase`](../../.agents/skills/learning-showcase/SKILL.md) (notes 09, 12). See the working agreement §13.

## What CL needs from you, in priority order

CL never waits; they use fallbacks. But the sooner these are real, the sooner the joint milestones work:

1. **I1** skeleton + `contracts/models.py` + stub modules (OA-M0)
2. **I2** `jobs.*`, `db.session`, `config.load_yaml`/`prompt`, the intel Alembic env (OA-M2)
3. **I3/I4** `documents.get/get_content/apply_metadata`, `ingest.submit/incoming_dir`, `document.*` events (OA-M3)
4. **I5** `auth.current_user`, `auth.visible_docs`, `search.hybrid` + `register_semantic` (OA-M4)
5. **I6** web shell, `/api/*` proxy with SSE streaming, generated client, slot placeholders (OA-M5)

## What you need from CL, with fallbacks

| Item | Fallback |
|------|----------|
| I7 `taxonomy.load()` | `tests/fixtures/taxonomy.yaml`, a copy of the default taxonomy in [../Developer-CL/02-classification-and-review.md](../Developer-CL/02-classification-and-review.md#default-taxonomy) |
| I8 semantic search fn | hybrid = FTS only |
| I9 slot components | your `null` placeholders |
| `docuhive.ai.startup()` | call it inside `try/except ImportError` |

## Estimated effort

About 11–12 part-time weeks in total. Per milestone: M0 0.5 · M1 1 · M2 1.5 · M3 2 · M4 2 · M5 2 · M6 1 · M7 1 · M8 1.

## Track progress in

[STATUS.md](STATUS.md)
