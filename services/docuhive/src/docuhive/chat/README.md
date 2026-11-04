# `services/docuhive/src/docuhive/chat`

**Overview.** Chat sessions with streamed answers, and saved analyses that re-run a question on demand.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Chat sessions and saved analyses around the Ask agent |
| [`jobs.py`](jobs.py) | analyses.run {analysis_id, user}: run a saved analysis to completion and store the result |
| [`models.py`](models.py) | chat_sessions, chat_messages, analyses |
| [`routes.py`](routes.py) | /api/chat (sessions, streamed answers over SSE) and /api/analyses (saved analyses) |

## Extending

Follow the [`document-chat`](../../../../../.agents/skills/document-chat/SKILL.md) skill for anything users see.
