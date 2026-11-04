# `services/docuhive/src/docuhive/agents/tools`

**Overview.** Tools the Ask agent can call. The user and the search scope come from the server, never from the model.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Tools for the Ask agent |
| [`facts.py`](facts.py) | query_facts: numbers come from SQL, never from the model |

## Extending

Return compact, typed results, and do any arithmetic in SQL, not in the model.
