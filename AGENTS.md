# AGENTS.md

Instructions for coding agents (Claude Code, Codex, Copilot) working on DocuHive. OA extends this file in OA-M0 with the repo map and commands; CL appends a section for its area.

## Start here

1. [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) and [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)
2. [docs/shared/README.md](docs/shared/README.md), then [contracts](docs/shared/contracts.md) and the [working agreement](docs/shared/working-agreement.md)
3. Your track: [docs/Developer-OA/](docs/Developer-OA/README.md) or [docs/Developer-CL/](docs/Developer-CL/README.md)

## Project skills (load the one that matches your task)

| Skill | When |
|-------|------|
| [docuhive-ui](.agents/skills/docuhive-ui/SKILL.md) | any web UI work |
| [repo-structure](.agents/skills/repo-structure/SKILL.md) | new files and folders, docs, workflows, releases |
| [strands-agent-harness](.agents/skills/strands-agent-harness/SKILL.md) | anything that calls a model |
| [learning-showcase](.agents/skills/learning-showcase/SKILL.md) | any AI, agent, search or eval change |
| [guided-experience](.agents/skills/guided-experience/SKILL.md) | settings, integrations, empty states, errors |
| [document-pipeline](.agents/skills/document-pipeline/SKILL.md) | sources, ingest, OCR, vault, jobs |
| [document-editing](.agents/skills/document-editing/SKILL.md) | metadata editing, tags, categories, facts |
| [document-chat](.agents/skills/document-chat/SKILL.md) | the Ask experience |
| [lessons-learned](.agents/skills/lessons-learned/SKILL.md) | **always**: before each milestone and every PR review (never/always rules) |

## Rules

- Contracts first ([docs/shared/contracts.md](docs/shared/contracts.md)). Edit only paths your track owns.
- The repo is public: no real documents, no personal data, no secrets, nothing from `overlay/`.
- Default tests need no API keys and no network (`FakeModel`, recorded fixtures).
- No AGPL imports. Tools under AGPL/GPL run only as subprocesses or containers.
- **Commits are authored and committed only by the repo owner's git identity (`d2k-klin`, from `git config`).** Never set another author or committer, never use `--author` or `GIT_AUTHOR_*`/`GIT_COMMITTER_*` overrides, and never add `Co-authored-by:` or other attribution trailers. This applies to humans, Claude, Codex, Copilot and every other agent.

## OA platform map and commands

- `services/docuhive/src/docuhive/{config,db,jobs,worker,ingest,vault,documents,auth,search,api}`:
  OA platform code. The OCR gate must be measured before selecting the ingest backend.
- `apps/web`: App Router web workspace. `deploy`: development/test containers and scripts.
- `services/docuhive/migrations/core`: OA migrations. Intel's independent migration
  environment is bootstrapped by OA and then owned by CL.
- Use `make setup`, `make dev`, `make test`, `make lint`, `make test-integration`,
  `make db-upgrade`, `make gen-api`, `make ocr-smoke` (real OCR in the worker image; run it
  after changing the Dockerfile, OCR dependencies or ingest code) and `make spike-ocr DIR=...`.
  `make` supersedes the older planning references to `just`.
- Python 3.12, type hints for application functions, Pydantic I/O, Ruff defaults
  with 100-character lines. TypeScript strict; server components by default.
- Test non-trivial behavior and update OA's STATUS.md with actual evidence.
  Do not mark hardware-dependent acceptance complete from mocks.
- In a concurrently used checkout, prefer `UV_PROJECT_ENVIRONMENT=.venv-oa` for OA validation.
