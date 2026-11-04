# `evals`

**Overview.** How AI quality is measured: the eval harness, the synthetic data set and the OCR measurement. Real labelled documents (the golden set) live in the private overlay.

## What's here

| Path | What it is |
| --- | --- |
| [`docuhive_evals/`](docuhive_evals/) | The eval harness behind `docuhive eval`: loaders, runners, scorers and reports |
| [`ocr/`](ocr/) | Character-error measurement for the private OCR go/no-go gate |
| [`synthetic/`](synthetic/) | A committed, generated eval set: 40 invented German and English documents with expected labels, search queries and questions |
| [`pyproject.toml`](pyproject.toml) | Eval harness package definition |

## Extending

See [`docs/evals`](../docs/evals/README.md) for running evals and for the gate that switches on automatic sorting.
