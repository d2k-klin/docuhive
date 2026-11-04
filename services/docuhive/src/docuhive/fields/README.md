# `services/docuhive/src/docuhive/fields`

**Overview.** Custom fields: details the household defines (such as a licence plate) that extraction, review, reminders and Ask treat like the taxonomy's own facts.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Reads custom fields and appends them to a document type for live extraction; evals keep the built-in taxonomy |

## Extending

Routes live in [`api/fields.py`](../api/fields.py). A field's name and type are fixed once created, because extracted values are stored under the name.
