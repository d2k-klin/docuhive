# `services/docuhive/src/docuhive/review`

**Overview.** The review queue: AI suggestions that wait for a person to accept, edit or reject them.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Review queue: AI suggestions become review_items; people accept, edit or reject them |
| [`models.py`](models.py) | review_items: AI suggestions waiting for a person |
| [`routes.py`](routes.py) | /api/review: the queue grouped by document, resolving items, bulk reclassify |

## Extending

Accepting a suggestion is a user edit and locks the field against AI changes.
