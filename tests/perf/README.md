# `tests/perf`

**Overview.** Measurements against a seeded real QA stack; synthetic timings do not sign hardware gates.

## What's here

| Path | Purpose |
| --- | --- |
| [search_bench.py](search_bench.py) | Search p50/p95 and the 500 ms target |
| [baselines.json](baselines.json) | Approval state for reference-host baselines |

## Extending

`make qa-perf` requires at least 20,000 documents. Do not populate a development
database or invent a baseline. Record the reference host when the owner approves one.
