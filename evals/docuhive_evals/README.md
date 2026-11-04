# `evals/docuhive_evals`

**Overview.** The eval harness behind `docuhive eval`: loaders, runners, scorers and reports.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Package marker |
| [`cli.py`](cli.py) | `docuhive eval ...` (registered through docuhive.ai.cli when this package is installed) |
| [`datasets.py`](datasets.py) | Loaders for eval sets (evals/synthetic, overlay/evals/golden) |
| [`oracle.py`](oracle.py) | FakeModels for the CI smoke run: they answer from the labels, so the machinery is tested without a real model |
| [`report.py`](report.py) | Markdown + JSON reports with a side-by-side table per route |
| [`retrieval.py`](retrieval.py) | Search and Ask evals: ingest the set into the SQLite fakes, then query it |
| [`runner.py`](runner.py) | Run the real agents in-process against an eval set, one route at a time |
| [`scorers.py`](scorers.py) | Per-field metrics |

## Extending

Add a scorer per new field type, with a unit test using hand-computed expectations.
