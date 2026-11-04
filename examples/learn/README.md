# `examples/learn`

**Overview.** One runnable example per concept in the [learning path](../../docs/learn/README.md). `make learn` lists them; `make learn EX=12` runs one.

## What's here

| Path | What it is |
| --- | --- |
| [`12_job_queue.py`](12_job_queue.py) | A durable-work contract demonstration with a fake queue; no database or AI needed |
| [`run.py`](run.py) | List or run a learning example by its numeric prefix |

## Extending

Name examples `NN_slug.py` to match the note number; `tests/unit/test_examples.py` runs every example in CI.
