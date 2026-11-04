# `services/docuhive/src/docuhive/documents`

**Overview.** The documents service: reading documents and applying metadata changes (from people or from AI) with locks, audit and events.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | The documents service: read, apply metadata with locks, audit, search vector and events, trash |
<<<<<<< HEAD
| [`vocabulary.py`](vocabulary.py) | Renaming and merging tags and senders, with audit, `meta.json` refresh and events |
=======
>>>>>>> origin/main
| [`metadata.py`](metadata.py) | Pure metadata changes used to keep the fake and eventual backend semantics aligned |

## Extending

Metadata changes always go through `apply_metadata`; see the [`document-editing`](../../../../../.agents/skills/document-editing/SKILL.md) skill.
