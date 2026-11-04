# `services/docuhive/src/docuhive/contracts`

**Overview.** The shared models every module agrees on. They mirror [`docs/shared/contracts.md`](../../../../../docs/shared/contracts.md), and a test fails if the two drift apart.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Binding interfaces shared by the platform and intelligence tracks |
| [`models.py`](models.py) | The shared Pydantic models |

## Extending

Change the document and the code in the same pull request.
