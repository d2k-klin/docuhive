# `services/docuhive/src/docuhive/ai`

**Overview.** The AI layer: provider settings, task routing, the privacy gate, budgets, embeddings and the log of every model call.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | AI providers, routing, privacy gate, budgets, ai_runs |
| [`budgets.py`](budgets.py) | Monthly USD caps per provider, computed from ai_runs (calendar month, UTC) |
| [`cli.py`](cli.py) | AI subcommands for the `docuhive` CLI: ai check, taxonomy check, index rebuild, mail gen-key, and `eval ...` (from the evals package when installed) |
| [`coretables.py`](coretables.py) | Read-only handles on the platform tables |
| [`embeddings.py`](embeddings.py) | Embeddings: Strands has no embeddings API, so this is a tiny client per provider kind |
| [`fake.py`](fake.py) | FakeModel: a scripted Strands model for tests, examples and the eval smoke run |
| [`http.py`](http.py) | Small HTTP helpers shared by the AI routers (error format and auth dependencies) |
| [`models.py`](models.py) | ai_runs: one row per model attempt (successful or not) |
| [`privacy.py`](privacy.py) | Privacy gate: restricted documents are only ever sent to local models |
| [`router.py`](router.py) | Task -> ordered routes (primary, fallbacks), filtered by privacy; route -> Strands model |
| [`routers.py`](routers.py) | All AI routers, appended to docuhive.api.routers.ROUTERS (shared touchpoint) |
| [`routes.py`](routes.py) | /api/ai: providers, routing, usage, runs ("How was this made?"), setup status |
| [`routing.py`](routing.py) | routing.yaml: the validated description of providers, task routes, privacy, budgets, pricing |
| [`runs.py`](runs.py) | Write ai_runs rows |
| [`settings.py`](settings.py) | AI provider settings (env prefix DOCUHIVE_AI_) |
| [`startup.py`](startup.py) | docuhive.ai.startup(): called once by the API and the worker (safe to call twice) |
| [`types.py`](types.py) | Column types for intel tables: Postgres types in production, portable ones in SQLite tests |

## Extending

Add a provider by adding a `kind` in `router.py` and `embeddings.py`, plus an example in `config/defaults/routing.yaml`.
