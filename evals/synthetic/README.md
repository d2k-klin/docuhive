# `evals/synthetic`

**Overview.** A committed, generated eval set: 40 invented German and English documents with expected labels, search queries and questions. It contains no real data.

## What's here

| Path | What it is |
| --- | --- |
| [`docs/`](docs/) | Generated document texts |
| [`generate.py`](generate.py) | Generate the synthetic eval set: 40 German/English documents with labels |
| [`labels.yaml`](labels.yaml) | Expected classification and facts per document |
| [`qa.yaml`](qa.yaml) | Questions with expected citations and numbers |
| [`search.yaml`](search.yaml) | Search queries with expected documents |

## Extending

Change `generate.py` and regenerate the set; never hand-edit the generated files.
