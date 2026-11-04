---
name: repo-structure
description: "Create, move or review files and folders in the DocuHive repository so it matches the d2k-klin public-repo conventions shared with ReelHive, SentryHive and CostHive: root community files, folder READMEs, docs index, Makefile targets, CHANGELOG, .github templates and workflows, agent skill folders, and public-repo hygiene (no private data, overlay kept out). Use when adding a folder, a top-level file, a workflow, a doc, a skill, or before a release."
---

# Repo structure (public, d2k-klin conventions)

DocuHive is a **public** Apache-2.0 repo under `github.com/d2k-klin/docuhive`. It follows the same layout and habits as the sibling repos (ReelHive is the closest model: Python + uv + a web UI + evals + agent skills). Anything personal lives in the private overlay repo, never here.

## Target layout

```
docuhive/
├─ README.md               short overview (template below), links to docs/README.md
├─ LICENSE                 Apache-2.0
├─ CHANGELOG.md            Keep a Changelog + SemVer, always has [Unreleased]
├─ CONTRIBUTING.md         dev setup (make targets), where things go, gates, PR rules
├─ CODE_OF_CONDUCT.md      Contributor Covenant
├─ SECURITY.md             private advisory link, supported versions, design guarantees
├─ AGENTS.md               instructions for coding agents (repo map, commands, rules, skills list)
├─ CLAUDE.md               one line: "Read AGENTS.md" (+ skill pointers if needed)
├─ Makefile                the commands CI runs (see below). No justfile
├─ pyproject.toml / uv.lock   uv workspace root (services/docuhive, evals)
├─ package.json / package-lock.json   npm workspaces (apps/web)
├─ .env.example            every variable, grouped by prefix, with comments
├─ .gitignore  .gitattributes  .pre-commit-config.yaml
├─ .agents/
│  ├─ README.md
│  └─ skills/<name>/SKILL.md      CANONICAL skills (this file lives here)
├─ .claude/
│  ├─ README.md
│  └─ skills/<name>/SKILL.md      thin pointers to .agents/skills (same front matter)
├─ .github/
│  ├─ CODEOWNERS  PULL_REQUEST_TEMPLATE.md  dependabot.yml  copilot-instructions.md (→ AGENTS.md)
│  ├─ ISSUE_TEMPLATE/{bug_report.yml, feature_request.yml, config.yml}
│  └─ workflows/{README.md, ci.yml, evals.yml, nightly.yml, release.yml, codeql.yml}
├─ apps/web/               Next.js app (README.md)
├─ services/docuhive/      Python package (README.md), migrations/, tests/
├─ config/defaults/        taxonomy, routing, mail rules, prompts (README.md)
├─ evals/                  harness, synthetic sets, baselines/ (README.md)
├─ examples/learn/         runnable learning examples (README.md; see the learning-showcase skill)
├─ deploy/                 compose files, scripts, drills (README.md)
├─ assets/                 brand/ (own LICENSE.md if artwork), screenshots, demo
└─ docs/
   ├─ README.md            the docs index: Using / Understanding / Learning / Extending / Planning
   ├─ setup/  learn/  decisions/  evals/  shared/  Developer-OA/  Developer-CL/
   └─ REQUIREMENTS.md  IMPLEMENTATION_PLAN.md
```
**There is no `.github/README.md`**, because GitHub would show it instead of the root README.

## Procedure

1. **Before adding a folder:** check whether an existing one fits (the table above). Avoid new top-level folders.
2. **Every folder you create gets a `README.md`** in the house format:
   ```markdown
   # `path/to/folder`

   **Overview.** One or two sentences: what this folder is for.

   ## What's here
   | Path | What it is |
   | --- | --- |
   | `file.py` (as a relative link) | … |

   ## Extending
   How to add the next thing here (naming, tests, docs to update).
   ```
3. **Every new doc** gets one topic per file, linked from `docs/README.md` (and from the root README's documentation table if it is a main guide). Relative links are checked by `tests/unit/test_docs.py` (it fails on broken links and anchors).
4. **Every new skill** goes in `.agents/skills/<name>/SKILL.md`, with `name` and `description` front matter (the description says *when* to use it). Then:
   - add the pointer `.claude/skills/<name>/SKILL.md` with the same front matter and the single line "Load and follow the canonical project skill at …"
   - list the skill in `.agents/skills/README.md`, and in `AGENTS.md`
5. **Every new command** goes into the `Makefile`, so contributors can run exactly what CI runs.
6. **Every user-visible change** gets a `CHANGELOG.md` entry under `[Unreleased]` (Added / Changed / Fixed / Removed / Security).

## Makefile targets (keep these names)

| Target | Does |
|--------|------|
| `setup` | `uv sync --all-extras --dev`, `npm ci`, pre-commit install |
| `dev` | compose up db + gotenberg (+ ollama if `AI=1`), then api, worker and web with reload |
| `test` | pytest with fakes only (no keys, no network), coverage gate 85%, plus web unit tests |
| `test-ui` | build the web app + Playwright e2e + axe + the control-height check |
| `test-integration` | compose.test stack + `pytest -m integration` |
| `lint` | ruff check, ruff format --check, mypy, eslint, `tsc --noEmit`, link check |
| `fmt` | ruff format + prettier |
| `db-upgrade`, `gen-api`, `openapi` | migrations and the API client |
| `eval`, `eval-baseline` | evals (CL), and refreshing the committed baseline |
| `spike-ocr DIR=…` | the OCR spike (OA) |
| `ocr-smoke` | build the worker image and run real OCR in it (unit tests mock ocrmypdf) |
| `up`, `down`, `logs`, `backup` | production compose helpers |
| `learn` | list and run the examples in `examples/learn/` |

## README template (root)

Same structure as the other Hive repos (ReelHive, SentryHive, CostHive):

1. **Hero:** the Mr.D mascot, right-aligned, 170 px wide, linked to `https://mr-d.dev`, loaded from `assets/brand/` by relative path (never hot-linked). Then the title `# ⬡ DocuHive`, and a one-line tagline as a quote in the house form "Point it at …, and get …, with no … wrangling."
2. **Badges:** CI, License Apache-2.0, "runs locally", and the project status.
3. **What DocuHive does**, in plain language with no tool names: the numbered flow (capture → read → sort → keep → find and ask → remind).
4. **What you'll learn**: Strands agents, the agent harness, evals, retrieval (link `docs/learn/README.md`).
5. **Quick start**: commands that work on a fresh clone, copied from `docs/setup/development.md` (including creating the first user). Describe only screens that exist; mark planned ones as planned.
6. **Documentation**: a table of the main guides, plus "All documentation" → `docs/README.md`.
7. **Project status**: an honest table of what works and what doesn't yet. No overclaiming.
8. **Contributing** (`CONTRIBUTING.md`, `SECURITY.md`, the skills), then **License**: the code licence, plus the note that the Mr.D name and artwork are not covered by it (`assets/brand/LICENSE.md`).
9. **Footer**, after a rule: `Created by **[Mr. D](https://mr-d.dev)**`, plus links to the other Hive repos.

Never in a README: internal plan IDs (`OA-M3`, `CL-01 §1.6`), track names as owners ("owned by CL"), "TODO", or placeholder text such as "Source, configuration or documentation". Folder README rows describe what each file *is for*, in plain words.

## Brand assets (`assets/brand/`)

- Mr.D files come from the brand archive, supplied by Dav. Each Hive repo ships its own copy; nothing is loaded from a server.
- Keep `manifest.json` (SHA-256 per file), `LICENSE.md` (the brand files are excluded from the code licence) and a `README.md` saying which pose is used where.
- `tests/unit/test_brand.py` checks every file against the manifest and keeps the set under 2 MB. Never edit the files by hand.

## `.github` conventions

- `CODEOWNERS`: `* @d2k-klin`, then the per-track entries from `docs/shared/working-agreement.md` §5.
- **PR template checklist:**
  - tests (`make test`, no keys or network)
  - `make lint`
  - docs and folder READMEs updated
  - CHANGELOG
  - contract changed → `docs/shared/contracts.md` updated
  - prompt or taxonomy changed → eval gate run locally
  - UI changed → `make test-ui` and screenshots in light and dark
  - a "Notes for reviewers" section: never paste tokens or real documents
- **Issue templates:** `bug_report.yml`, `feature_request.yml`, and `config.yml` with `blank_issues_enabled: false` plus a security advisory contact link.
- `dependabot.yml`: weekly updates for `uv` (it updates `uv.lock`; `pip` would not), `npm` and `github-actions`, with commit prefixes `deps`/`ci` and labels. Majors that need a migration (Tailwind) or must follow the runtime (`@types/node`) are ignored and done by hand.
- **Workflows:**
  - Pin third-party actions to a full commit SHA with the version in a comment.
  - Default to `permissions: contents: read` and widen only per job.
  - Normal CI is key-free. The eval gate (`evals.yml`) runs on PRs touching prompts, taxonomy or eval sets, and fails rather than skips when a needed secret is missing. Describe every workflow in `workflows/README.md`.
  - `release.yml` runs on a `v*` tag, checks that the tag equals the version in `pyproject.toml`, builds the images (GHCR), and creates a GitHub Release with the CHANGELOG section.

## Public-repo hygiene (check before every commit)

- [ ] No real documents, emails, names, addresses, IBANs or screenshots with personal data. Fixtures are synthetic.
- [ ] Nothing from the overlay: `overlay/`, private taxonomy or prompts, the golden eval set, eval reports built from it.
- [ ] No secrets: `.env`, OAuth tokens, API keys (gitleaks runs in pre-commit and CI). Only `.env.example`.
- [ ] No machine-specific paths. Paths come from settings with documented defaults.
- [ ] Brand artwork (if any) has its own licence note in `assets/brand/LICENSE.md`. The code licence doesn't cover it.
- [ ] Generated folders are ignored: `.venv/`, `node_modules/`, `.next/`, `data/`, `tmp/`, `runs/`, `evals/reports/`, `test-results/`, `playwright-report/`, `.coverage`, `*.local.*`.

## Commits & releases

- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `ci:`, `deps:`, `chore:`. Use a scope where useful (`feat(ingest): …`).
- **Only the owner's identity:** author and committer are always `d2k-klin` (from `git config`). No other users, no `--author` or env overrides, no `Co-authored-by:` or "Generated with" trailers in commits or PR descriptions.
- SemVer from `0.1.0`. Bump the version in `pyproject.toml`, move `[Unreleased]` to the new version with a date, then tag `vX.Y.Z`.

## Done when

The new file or folder fits the layout, has its README, is linked from the right index, has a Makefile target if it is a command, a CHANGELOG entry if it is user-visible, passes `make lint` (including the link check), and contains nothing private.
