# `config/defaults/prompts`

**Overview.** Versioned prompts for the AI agents. Each file starts with `version:` front matter; the version is stored with every model call and every eval report.

## What's here

| Path | What it is |
| --- | --- |
| [`ask.md`](ask.md) | Prompt for the Ask agent |
| [`classify.md`](classify.md) | Prompt for classifying documents |
| [`extract.md`](extract.md) | Prompt for extracting facts |
| [`triage.md`](triage.md) | Prompt for deciding whether an email holds a document |

## Extending

Bump `version` on every wording change and run the evals before merging (see the [`strands-agent-harness`](../../../.agents/skills/strands-agent-harness/SKILL.md) skill).
