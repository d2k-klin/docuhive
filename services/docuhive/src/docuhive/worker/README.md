# `services/docuhive/src/docuhive/worker`

**Overview.** The background worker that runs jobs from the queue, and the list of modules that register job handlers.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Threaded worker with bounded graceful shutdown and scheduler failover |
| [`handlers.py`](handlers.py) | Shared touchpoint: append handler modules; preserve other track registrations |

## Extending

Append handler modules to `handlers.py`; never remove another module's entry.
