# `services/docuhive/src/docuhive/agents`

**Overview.** The AI agents and the harness they run in: triage for email, classify and extract for documents, and the Ask agent for chat. Every model call goes through `base.py`.

## What's here

| Path | What it is |
| --- | --- |
| [`tools/`](tools/) | Ask agent tools |
| [`__init__.py`](__init__.py) | Package marker |
| [`ask.py`](ask.py) | Ask agent: a tool-using chat over the archive with citations |
| [`base.py`](base.py) | The agent harness: the only way DocuHive calls a model |
| [`classify.py`](classify.py) | Classify agent: category, type, correspondent, tags, title, date, language |
| [`extract.py`](extract.py) | Extract agent: typed facts per document type (amounts, dates, IBANs...), validated in code |
| [`pipeline.py`](pipeline.py) | Job handlers that turn document events into AI work (queue "ai") |
| [`triage.py`](triage.py) | Triage agent: a cheap gatekeeper on the envelope before the expensive pipeline |
| [`validators.py`](validators.py) | Pure parsers and checks for model output |

## Extending

Follow the [`strands-agent-harness`](../../../../../.agents/skills/strands-agent-harness/SKILL.md) skill: a typed output, a versioned prompt, a route, FakeModel tests and eval cases.
