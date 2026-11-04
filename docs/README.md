# `docs`

**Overview.** Everything you need to use, understand and extend DocuHive, beyond the [README](../README.md), which stays a short overview. Start with the guide that matches what you're doing.

## Using DocuHive

| Doc | Read it for |
| --- | --- |
| [setup/mobile.md](setup/mobile.md) | Phone capture, offline uploads, scanner folders and personal tokens |
| [setup/operations.md](setup/operations.md) | Production containers, nightly backups, recovery and upgrades |
| [setup/nas-wd-ex2-ultra.md](setup/nas-wd-ex2-ultra.md) | Mounting the NAS and securing the generated library |
| [setup/remote-access.md](setup/remote-access.md) | Private HTTPS for phones through Tailscale |
| [setup/development.md](setup/development.md) | Running DocuHive locally, and the checks to run before a pull request |
| [setup/knowledge-bases.md](setup/knowledge-bases.md) | Saved scopes, indexing status and API token privacy |
| [setup/ai-providers.md](setup/ai-providers.md) | Local and cloud AI, which model does what, privacy and budgets |
| [setup/mail-accounts.md](setup/mail-accounts.md) | Connecting Gmail, Outlook and IMAP accounts, and importing old mail |
| [setup/notifications.md](setup/notifications.md) | Push and email alerts, reminders and the calendar feed |
| [../SECURITY.md](../SECURITY.md) | How to report a vulnerability, and what DocuHive guarantees |

## Understanding it

| Doc | Read it for |
| --- | --- |
| [FEATURES.md](FEATURES.md) | Every feature in one sentence with its current state |
| [ARCHITECTURE.md](ARCHITECTURE.md) | How DocuHive works, from the big picture down to each component, user action and hosting option |
| [REQUIREMENTS.md](REQUIREMENTS.md) | What DocuHive must do, with requirement IDs used across tests and plans |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | The architecture: vault, ingest pipeline, AI layer, search and web app |
| [decisions/](decisions/README.md) | Decisions with their evidence, such as the [OCR quality gate](decisions/0001-ocr-gate.md) |
| [shared/contracts.md](shared/contracts.md) | The interfaces between the platform and the AI modules |

## Learning from it

| Doc | Read it for |
| --- | --- |
| [learn/](learn/README.md) | The learning path: Strands agents, the agent harness, privacy routing, jobs and retrieval |
| [evals/](evals/README.md) | How AI quality is measured, and when automatic sorting is switched on |
| [../examples/learn/](../examples/learn/README.md) | Runnable examples, one per learning note |
| [../evals/ocr/](../evals/ocr/README.md) | Measuring OCR accuracy (character error rate) |

## Extending it

| Doc | Read it for |
| --- | --- |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Development workflow, checks and pull-request rules |
| [../.agents/skills/](../.agents/skills/README.md) | Project conventions for humans and coding agents: UI, repo structure, the agent harness and more |
| [shared/working-agreement.md](shared/working-agreement.md) | Ownership, migrations, shared files and how contracts change |

## Planning

DocuHive is built by three parallel tracks. Each has a plan, an execution plan and a live status.

| Track | Plan | Status |
| --- | --- | --- |
| Production readiness phases | [shared/production-readiness.md](shared/production-readiness.md) | — |
| Work split and integration points | [shared/README.md](shared/README.md) | — |
| Knowledge bases (all tracks): retrieve and ask APIs, MCP, evals | [shared/knowledge-bases.md](shared/knowledge-bases.md) | — |
| Archive tools: vault health, custom fields, saved views, near-duplicates, export | [shared/archive-tools.md](shared/archive-tools.md) | — |
| Production readiness: what is left before 1.0, in order | [shared/production-readiness.md](shared/production-readiness.md) | — |
| Platform (OA): storage, ingest, sign-in, search, web shell, operations | [Developer-OA/](Developer-OA/README.md) | [status](Developer-OA/STATUS.md) |
| Intelligence (CL): AI layer, classification, email, chat, reminders | [Developer-CL/](Developer-CL/README.md) | [status](Developer-CL/STATUS.md) |
| Quality (QA): contracts, end-to-end, non-functional checks, releases | [Developer-QA/](Developer-QA/README.md) | [status](Developer-QA/STATUS.md) |

QA also keeps the [traceability matrix](Developer-QA/traceability.md), [manual checks](Developer-QA/manual-checks.md), [defect register](Developer-QA/bugs.md) and [verification reports](Developer-QA/reports/README.md).

## Extending the docs

One topic per file, linked from this index (and from the root README's documentation table if it's a main guide). Every folder in the repository has its own README for the code in it. Relative links are checked by `tests/unit/test_docs.py`.
