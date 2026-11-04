# `tests`

**Overview.** Repository-level tests: unit checks of docs and examples, QA's system and browser tests, mocks, the synthetic corpus and benchmarks.

## What's here

| Path | What it is |
| --- | --- |
| [`corpus/`](corpus/) | Reproducible, invented documents for QA; never evidence for the real OCR gate |
| [`e2e/`](e2e/) | Real browser journeys against QA's seeded stack, with no route interception |
| [`mocks/`](mocks/) | Loopback test services with deterministic responses |
| [`perf/`](perf/) | Measurements against a seeded real QA stack; synthetic timings do not sign hardware gates |
| [`system/`](system/) | Independent QA checks of real contracts, the running backend and the QA harness |
| [`unit/`](unit/) | Docs, examples and licence checks |

## Extending

Product unit tests belong in `services/docuhive/tests` or `apps/web/tests`; this folder is for whole-system checks.
