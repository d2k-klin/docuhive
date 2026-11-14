<a href="https://mr-d.dev"><img src="assets/brand/mr-d-art-9@2x.webp" alt="Mr. D, the DocuHive mascot, holding a document checklist" align="right" width="170"></a>

# ⬡ DocuHive

> Point it at your mailboxes, your phone and your scanner, and get one searchable, AI-sorted archive on your own storage, with no folder-and-filename wrangling.

[![CI](https://github.com/d2k-klin/docuhive/actions/workflows/ci.yml/badge.svg)](https://github.com/d2k-klin/docuhive/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Runs locally](https://img.shields.io/badge/runs-locally-green.svg)](docs/setup/ai-providers.md)
[![Status: production-ready](https://img.shields.io/badge/status-production--ready-green.svg)](#project-status)

## What DocuHive does

Invoices arrive by email, letters come by post, contracts sit in a drawer, and a year later you need the one with the notice period. DocuHive keeps all of them in one archive that you own, and lets you find anything in seconds.

1. **Capture.** It picks up attachments from Gmail, Outlook and other mailboxes (including years of old mail), photos from your phone, files from a scanner folder, and anything you upload.
2. **Read.** Scans and photos are straightened and turned into searchable PDFs. Office files and emails are converted too.
3. **Sort.** An AI assistant files each document into your categories, recognises who sent it, and pulls out the details that matter: amounts, due dates, contract terms, policy numbers. When it isn't sure, it asks you instead of guessing.
4. **Keep.** Originals are stored unchanged on your own storage (a NAS or a disk), next to a readable description of each document. The archive stays usable even without DocuHive.
5. **Find and ask.** Search by words or by meaning, or just ask: *"How much did I spend on electricity in 2025?"* Answers link to the documents they came from, and totals are calculated, not guessed.
6. **Remind.** Due dates, renewal dates and contract notice deadlines become reminders on your phone or in your calendar.

You choose where the AI runs: entirely on your own machine, with a cloud provider, or both. Health and identity documents always stay local.

## A look inside

<video src="https://github.com/d2k-klin/docuhive/raw/main/docs/video.mp4" controls muted playsinline width="1280">
  <a href="docs/video.mp4">Watch the DocuHive demo video</a>
</video>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/screenshots/ask-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="assets/screenshots/ask-light.png">
  <img alt="The DocuHive Ask screen with category and model selectors, a local-only option, suggested questions and a question box." src="assets/screenshots/ask-light.png" width="1280">
</picture>

*Ask your archive: suggested questions, category filters and a local-only switch. Real app UI with a synthetic test account; the image follows your light or dark theme.*

<details>
<summary><strong>AI settings</strong>: providers, routing per task, privacy and usage</summary>

![DocuHive AI settings in dark mode, showing which providers are available, which model runs each task, and local versus cloud run counts.](assets/screenshots/ai-settings-dark.png)

*The `qa` provider and the usage figures come from the scripted test environment. More in [assets/screenshots](assets/screenshots/README.md).*

</details>

## What you'll learn

DocuHive is also a worked example of building a real AI product. The code, the [learning notes](docs/learn/README.md) and the app itself show:

- **Agents with [Strands](https://strandsagents.com):** structured output, tools, the agent loop, streaming, several model providers
- **An agent harness:** routing per task, fallbacks, a privacy gate, budgets, and an audit trail of every model call
- **Evals:** golden sets, per-field scoring and a gate before automation is switched on
- **Retrieval:** chunking, embeddings, full-text plus vector search, answers with citations and SQL-computed numbers

Every model call is recorded with its model, prompt version, tools, tokens and cost. The AI settings page shows routing, privacy and usage, and every AI-set value links to a *How was this made?* page with its prompt, output and retries.

## Quick start

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22, and Docker.

```bash
git clone https://github.com/d2k-klin/docuhive && cd docuhive
make setup
docker compose -f deploy/compose.dev.yml up -d --wait
make db-upgrade
uv run docuhive user create admin --admin
make dev
```

Open <http://localhost:3000> and sign in with the account you just created. The dashboard's setup checklist lists what is still missing. For details, see [Development setup](docs/setup/development.md). To install it on a home server, follow the [installation guide](docs/setup/installation.md).

## Documentation

| Guide | What's in it |
| --- | --- |
| [Installation guide](docs/setup/installation.md) | From an empty Linux host to a signed-in household archive, step by step |
| [User guide](docs/user-guide.md) | Adding, finding, correcting and asking about documents, day to day |
| [Features](docs/FEATURES.md) | Every feature in one sentence, and what works today |
| [AI providers](docs/setup/ai-providers.md) | Local (Ollama) and cloud models, which model does what, privacy and budgets |
| [Email accounts](docs/setup/mail-accounts.md) | Connecting Gmail, Outlook and IMAP; importing old mail |
| [Notifications](docs/setup/notifications.md) | Push and email alerts, reminders, the calendar feed |
| [Capture guide](docs/setup/mobile.md) | Phone capture, offline uploads, scanner folders and tokens |
| [Operations guide](docs/setup/operations.md) | Production containers, backups, recovery and upgrades |
| [Development setup](docs/setup/development.md) | Running DocuHive locally and running the checks |
| [Learning path](docs/learn/README.md) | Strands, the agent harness, evals and retrieval, step by step |
| [Requirements](docs/REQUIREMENTS.md) | What DocuHive must do, and why |
| [Architecture](docs/ARCHITECTURE.md) | How it works, from the big picture to each component, user action and hosting option |
| [Implementation plan](docs/IMPLEMENTATION_PLAN.md) | How it is built, milestone by milestone |
| [All documentation](docs/README.md) | Everything else, including decisions and the team plans |

## Project status

DocuHive is production-ready: install it from the [installation guide](docs/setup/installation.md) and keep real documents in it. The owner declared this on 2026-11-14 ([decision](docs/decisions/0005-production-status.md)); the table says what has been verified and where your own first run is the check.

| Area | State |
| --- | --- |
| Platform: settings, database, job queue, sign-in | working, tested |
| AI layer, classification, review queue, email connectors, chat | working, tested against test doubles and local models; run `docuhive ai check` against your own providers |
| Document intake and archive (OCR, vault) | working, tested with synthetic files; OCR quality on real documents is not measured ([OCR gate](docs/decisions/0001-ocr-gate.md)) |
| Web app | all document, review, chat, source and settings pages; undo, notes and a compact phone menu are planned |
| Security hardening | [checklist](docs/security-checklist.md) ticked with evidence; OWASP ZAP baseline with no failures; no second sign-in factor yet, so keep it on your tailnet or LAN |
| Phone, scanner and token capture | working through the same intake as uploads; tested in desktop browsers, not on a range of real phones |
| Deployment and recovery | production stack, backup and restore tested locally with synthetic data; run the [restore drill](docs/setup/operations.md) on your own host before you rely on it |

Progress is tracked in the [team plans](docs/shared/README.md).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow and checks, and [SECURITY.md](SECURITY.md) for reporting vulnerabilities privately. The [project skills](.agents/skills/README.md) describe the conventions that humans and coding agents follow.

## License

Code: [Apache-2.0](LICENSE). Third-party tools and their licences are listed in [THIRD_PARTY.md](THIRD_PARTY.md). The Mr.D name and artwork are not covered by the code licence ([assets/brand/LICENSE.md](assets/brand/LICENSE.md)); forks keep the code and replace them.

---

Created by **[Mr. D](https://mr-d.dev)**. DocuHive is part of the Hive family, alongside [ReelHive](https://github.com/d2k-klin/reelhive), [SentryHive](https://github.com/d2k-klin/sentryhive) and [CostHive](https://github.com/d2k-klin/costhive).
