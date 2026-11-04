# Developer CL — Intelligence & connectors track

You own **everything AI and everything email**: the multi-provider agent layer, the taxonomy,
classification and extraction, the review queue, evals, the Gmail/Outlook/IMAP connectors, semantic
search, Ask/analyses, and reminders/notifications. Developer OA owns the platform you build on
(ingest, vault, DB, jobs, auth, web shell), which you reach only through the contracts.

## Project in one paragraph

DocuHive is a self-hosted, open-source, AI-first document hub. Documents arrive by email, phone
camera, scanner or upload. They are OCR'd and stored in a self-describing **vault** on a WD My Cloud
NAS (original + PDF/A + `meta.json` per document; the DB can be rebuilt from it), classified by AI
into a controlled taxonomy, and made searchable (full-text + semantic) and askable ("what did I pay
for electricity in 2025?") with local (Ollama) or cloud AI (Anthropic, OpenAI, Bedrock, GitHub
Copilot via LiteLLM). Stack: Python (FastAPI, worker, **Strands Agents SDK**) + Next.js, with
Postgres (FTS + pgvector). Personal configuration (taxonomy, prompts, rules, eval data) lives in a
private overlay repo.

## Read first

1. [../REQUIREMENTS.md](../REQUIREMENTS.md) and [../IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md)
2. [../shared/README.md](../shared/README.md): the split, integration points, joint milestones
3. [../shared/contracts.md](../shared/contracts.md): what you can call, and what you must provide
4. [../shared/working-agreement.md](../shared/working-agreement.md)
5. [../Developer-OA/README.md](../Developer-OA/README.md) and its `STATUS.md`

## Your milestones (in order)

| Milestone | File | Requirement IDs | Uses from OA (fallback until ready) |
|-----------|------|-----------------|--------------------------------------|
| **CL-M0** Standalone spikes: providers + OAuth | [01-ai-layer.md](01-ai-layer.md), [04-email-ingestion.md](04-email-ingestion.md) | AI-01, MAIL-01 | nothing (runs in `spikes/cl/`) |
| **CL-M1** AI layer: router, harness, privacy, budgets, `ai_runs` | [01-ai-layer.md](01-ai-layer.md) | AI-01..05, CLS-07 | I1, I2 (fakes) |
| **CL-M2** Taxonomy, classify + extract, review queue | [02-classification-and-review.md](02-classification-and-review.md) | CLS-01..07, DOC-03 | I3 (FakeDocuments), I6 (root layout) |
| **CL-M3** Eval harness, golden set, model selection | [03-evals.md](03-evals.md) | NFR-09 | none |
| **CL-M4** Email: OAuth, connectors, prefilter, triage, backfill | [04-email-ingestion.md](04-email-ingestion.md) | MAIL-01..10 | I4 (FakeIngest) |
| **CL-M5** Embeddings, semantic search, similar docs | [05-semantic-search-and-ask.md](05-semantic-search-and-ask.md) | SRCH-02, SRCH-05 | I3, I5 (dev user) |
| **CL-M6** Ask agent, facts tool, chat UI, analyses | [05-semantic-search-and-ask.md](05-semantic-search-and-ask.md) | QA-01..04, QA-06 | I5 (`search.hybrid` → own semantic), I6 (SSE proxy → direct API in dev) |
| **CL-M7** Reminders, notifications, privacy audit | [06-reminders-and-notifications.md](06-reminders-and-notifications.md) | QA-05, AUTO-03, AI-03 | I3 events |

**Ordering note:** CL-M3 (evals) can start as soon as CL-M2's classify agent works on synthetic documents. CL-M4 (email) is independent of CL-M2/M3 and may be done earlier if you prefer. The only hard order is M1 → M2 → M5 → M6.

## Skills to load

[`strands-agent-harness`](../../.agents/skills/strands-agent-harness/SKILL.md) (every model call), [`learning-showcase`](../../.agents/skills/learning-showcase/SKILL.md) (notes 01–08, 10, 11, examples, "How was this made?"), [`docuhive-ui`](../../.agents/skills/docuhive-ui/SKILL.md) (all your pages and slots), [`guided-experience`](../../.agents/skills/guided-experience/SKILL.md) (setup checks + wizard steps), [`document-pipeline`](../../.agents/skills/document-pipeline/SKILL.md) (email sources, AI jobs), [`document-editing`](../../.agents/skills/document-editing/SKILL.md) (review queue, AI panel), [`document-chat`](../../.agents/skills/document-chat/SKILL.md) (the Ask page), [`repo-structure`](../../.agents/skills/repo-structure/SKILL.md). See the working agreement §13.

## What OA needs from you, in priority order

1. **I7** `taxonomy.load()` + `config/defaults/taxonomy.yaml` (early in CL-M2: OA's filters and library view use it)
2. **`docuhive.ai.startup()`** existing (even if empty), so OA can call it
3. **I8** `search.register_semantic` implementation (CL-M5)
4. **I9** slot components (`components/intel/*`) as each feature lands

## Golden rule for your track

**AI never writes document state directly.** It always goes through `documents.apply_metadata`, with `actor="ai:<task>"` and a `Provenance`. Every model call goes through the agent harness, which means privacy gate → budget → `ai_runs` log. No exceptions; the privacy tests in CL-M7 verify it.

## Estimated effort

About 12 part-time weeks in total. Per milestone: M0 0.5 · M1 1.5 · M2 2.5 · M3 1 · M4 3 · M5 1 · M6 2 · M7 1.

## Track progress in

[STATUS.md](STATUS.md)
