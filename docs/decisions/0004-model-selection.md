# Decision: local models for classification and extraction

Date: 2026-11-05 · State: accepted for the defaults; automatic filing still waits for the golden set

## Context

`routing.yaml` routed classification and extraction to `ollama/qwen3:8b` and triage to `ollama/qwen3:4b`. This file is the gate its comments and the eval report point to. No model had been measured, because no model had run.

On 2026-11-05 the evals ran for the first time against real local models, on the committed synthetic set (`evals/synthetic`: 40 invented German and English documents, 36 of them with facts). The machine was an Apple M3 Pro with 36 GB, Ollama 0.40.14 and prompts `classify@1` and `extract@1`. Reports: [classification](../evals/reports/2026-11-05-classify.md) and [extraction](../evals/reports/2026-11-05-extract.md).

### Finding 1: thinking was on, and it only cost time

qwen3 and Gemma 4 reason before answering unless they are told not to, and DocuHive never told them. On one document and a short prompt, `qwen3:8b` took 24 s with thinking and 3.8 s without; `qwen3:4b` took 91 s and 1.9 s. A first 3-document run with thinking on took 120 s per document at the median and 305 s at p95, so calls ran into the 120 s timeout.

On the first 10 documents, with each task's best model:

| Run | Done | Accuracy | p50 / p95 per document |
| --- | --- | --- | --- |
| `gemma4:12b` classify, thinking off | 10/10 | category, type and date 100% | 11.9 s / 20.7 s |
| `gemma4:12b` classify, thinking on | 8/10 (2 timed out) | 100% of the 8 | 25.4 s / 97.7 s |
| `qwen3:8b` extract, thinking off | 10/10 | facts exact 100% | 20.4 s / 23.0 s |
| `qwen3:8b` extract, thinking on | 8/10 (2 timed out) | facts exact 79% | 258.9 s / 338.7 s |

### Finding 2: each model wins one task

All 40 documents for classification and 36 for extraction, with thinking off:

| Classification | `qwen3:8b` | `gemma4:12b` |
| --- | --- | --- |
| Category | 47.5% | **92.5%** |
| Category parent | 87.5% | 97.5% |
| Document type | 97.5% | 100% |
| Correspondent | 100% | 100% |
| Document date | 97.5% | 100% |
| Precision above the 0.80 threshold | 87.7% | **97.9%** |
| Gate (≥ 95% precision above threshold, ≥ 90% category and type) | fail | **pass** |
| p50 / p95 per document | 11.9 s / 13.9 s | 11.4 s / 16.4 s |

| Extraction | `gemma4:12b` | `qwen3:8b` |
| --- | --- | --- |
| Facts exact | 57.0% | **95.3%** |
| Facts found | 57.0% | **96.2%** |
| Precision above the threshold | 100% | 99.0% |
| Share above the threshold | 17.5% | **96.1%** |
| Valid on the first try | 88.9% (2 documents failed) | 100% |
| p50 / p95 per document | 13.4 s / 57.8 s | 17.4 s / 26.5 s |

`qwen3:8b` mostly picks the right parent category but not the subcategory. `gemma4:12b` is rarely wrong on a fact, but it misses many and is unsure about most of the rest.

`qwen3:4b` classified a 3-document trial correctly, but on the full prompt it took about 60 s per call, against about 15 s for `qwen3:8b`, so its full run was stopped. Triage stays on `qwen3:4b`, untested, because its prompt is much shorter.

## Decision

- **Thinking off:** Ollama gets `think: false` by default (`providers.ollama.think`). It can be set to `true`, or `null` for the model's own default, in the overlay.
- **Classification:** `ollama/gemma4:12b`, falling back to `ollama/qwen3:8b`.
- **Extraction:** stays on `ollama/qwen3:8b`.
- **Automatic filing:** stays off (`apply.auto: false`). The gate is meant for the owner's golden set of real documents, which does not exist yet. A pass on 40 invented documents does not switch anything on.

Both models together need about 17 GB, which fits a 32 GB host next to `bge-m3`. Ollama keeps a model loaded for five minutes, so alternating tasks costs a few seconds per switch.

## Validation and consequences

- **Covered by tests:** the routing tests check that `think` reaches the Ollama request, and that `null` sends nothing.
- **Tags:** tag scores are not meaningful on this set. 39 of the 40 documents have no expected tags, so every suggested tag counts as a false positive. Tags are not part of the gate.
- **Search eval:** `docuhive eval search` only supports `semantic` mode. Its hybrid and word-search modes still say they need a database, so hybrid search was checked through the running app instead.
- **Revisit:**
  - when the golden set exists;
  - when a prompt version changes;
  - when a new model family is worth trying (`gemma4:26b-a4b` runs about 4B parameters per step and is the obvious next candidate);
  - on the target host, where speed will differ.
