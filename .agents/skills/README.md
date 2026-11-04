# `.agents/skills`

**Overview.** Project skills for coding agents (Claude Code, Codex, Copilot and others): short, task-focused procedures for building DocuHive. Each skill lives in its own folder as a `SKILL.md` with a `name` and `description` in its front matter; that file is the skill's documentation, so the folders have no separate README.

## What's here

| Skill | Use it when working on |
|-------|------------------------|
| [`docuhive-ui`](docuhive-ui/SKILL.md) | any web screen or component: tokens, font, type scale, uniform control heights, alignment, states |
| [`repo-structure`](repo-structure/SKILL.md) | new files and folders, docs, workflows, skills, releases; public-repo hygiene |
| [`strands-agent-harness`](strands-agent-harness/SKILL.md) | anything that calls a model: Strands, the harness, routing, privacy, budgets, prompts, evals |
| [`learning-showcase`](learning-showcase/SKILL.md) | keeping the learning purpose visible: `docs/learn`, `examples/learn`, "How was this made?" |
| [`guided-experience`](guided-experience/SKILL.md) | the setup wizard, setup checks, empty states, error copy, inline help |
| [`document-pipeline`](document-pipeline/SKILL.md) | sources, ingest, OCR, vault, jobs, events: automatic, idempotent, lossless |
| [`document-editing`](document-editing/SKILL.md) | editing tags, category, type, correspondent, dates, facts; locks, undo, bulk edit |
| [`document-chat`](document-chat/SKILL.md) | the Ask experience: entry points, scope, citations, numbers, follow-ups, failures |
| [`lessons-learned`](lessons-learned/SKILL.md) | **always**: never/always rules and pitfalls from sibling projects; load before each milestone and PR review |

These are the canonical copies; [`.claude/skills`](../../.claude/skills) holds thin pointers to them for Claude Code.

## Extending

Add `<name>/SKILL.md` with `name` and `description` front matter (the description says *when* to use it), keep it procedural and repo-specific, add a pointer in `.claude/skills/<name>/SKILL.md` with the same front matter, and list it here and in [`AGENTS.md`](../../AGENTS.md).
