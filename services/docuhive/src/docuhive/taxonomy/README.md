# `services/docuhive/src/docuhive/taxonomy`

**Overview.** The controlled vocabulary (categories, document types, tags and facts) the AI chooses from.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Taxonomy loader: config/defaults/taxonomy.yaml + overlay, validated and cached |
| [`routes.py`](routes.py) | GET /api/taxonomy: the taxonomy plus a category tree for pickers and filters |

## Extending

Your own taxonomy goes into the private overlay; it replaces the default lists.
