# `services/docuhive/src/docuhive/auth`

**Overview.** Sign-in, sessions, scoped API tokens, login throttling and the single document-visibility rule.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Sessions, scoped API tokens and FastAPI authorization dependencies |
| [`permissions.py`](permissions.py) | The single document visibility rule, including for administrators |
| [`rate_limit.py`](rate_limit.py) | Failed-login windows using monotonic time and bounded cleanup |

## Extending

Every document query must use `visible_docs`; never write a second visibility rule.
