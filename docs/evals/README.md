# `docs/evals`

**Overview.** How DocuHive measures AI quality, and when automatic sorting is switched on. Committed reports from the synthetic set go here. Reports built from private documents stay in the overlay.

## Why automatic sorting starts off

By default, AI suggestions go to the **Review** queue, and nothing is applied automatically (`apply.auto: false` in `routing.yaml`). Auto-apply is switched on only after a model has been measured on your own labelled documents (the "golden set") and passes the gate:
- at least 95% accuracy on the fields above the confidence threshold
- at least 90% overall on category and document type

## Running evals

```bash
uv run docuhive eval classify --set evals/synthetic --route classify=ollama/gemma4:12b --route classify=ollama/qwen3:8b
uv run docuhive eval extract  --set evals/synthetic --route extract=ollama/qwen3:8b
uv run docuhive eval search   --set evals/synthetic --mode hybrid
uv run docuhive eval ask      --set evals/synthetic --route chat=anthropic/claude-sonnet-5-5
```
- Repeat `--route` to compare models side by side.
- Reports are written to `evals/reports/` (gitignored), as markdown and JSON.

Reports from the synthetic set that back a decision are kept in [`reports/`](reports/), for example the [model selection](../decisions/0004-model-selection.md) runs.

## Building your golden set

Once you have reviewed documents in DocuHive, export the ones whose fields you confirmed:

```bash
uv run docuhive eval export-golden --reviewed --n 100 --out "$DOCUHIVE_OVERLAY_DIR/evals/golden"
```
Then run the evals with `--set "$DOCUHIVE_OVERLAY_DIR/evals/golden"`. The golden set never goes into this public repository.

## Extending

Add synthetic cases with `evals/synthetic/generate.py`, commit the generated set, and record model decisions in [`docs/decisions/`](../decisions/). See the [learning path](../learn/README.md) for how the harness and scorers work.
