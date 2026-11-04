---
name: strands-agent-harness
description: "Add or change any AI behaviour in DocuHive with the Strands Agents SDK through the project's agent harness: structured output, tools, the agent loop, streaming, model providers (Ollama, Anthropic, OpenAI, Bedrock, LiteLLM/Copilot), routing.yaml, the privacy gate, budgets, ai_runs logging, versioned prompts, FakeModel tests and evals. Use when touching docuhive/ai, docuhive/agents, prompts, routing, or anything that calls a model."
---

# Strands + the DocuHive agent harness

All model calls in DocuHive go through **one** harness (`docuhive/agents/base.py`) on top of the Strands Agents SDK. The harness adds what Strands deliberately leaves to the application:
- routing per task
- privacy (restricted documents stay local)
- budgets
- validation retries
- an audit log of every attempt (`ai_runs`)

Never call a provider or `strands.Agent` directly from feature code.

## Procedure: adding a new AI task (e.g. "summarise")

1. **Check the pinned Strands version** (`uv pip show strands-agents`) and read its docs for `Agent`, structured output and `@tool`. **Don't trust memory**: method names around structured output and streaming have changed between versions. Confirm them with a 10-line script in `examples/learn/` first.
2. **Define the output** as a Pydantic model in the agent module (`docuhive/agents/<task>.py`), with `Field` constraints and short descriptions; the model reads them. Keep it flat and small.
3. **Write the prompt** in `config/defaults/prompts/<task>.md`, with front matter `version: 1`. Use `{placeholders}` (filled by `str.format_map`). Bump `version` on **every** wording change; the version is stored in every `ai_runs` row and every eval report.
4. **Route it:** add `tasks.<task>` in `config/defaults/routing.yaml` (route, fallbacks, timeout, context limits). The local route is the default.
5. **Call it through the harness only:**
   ```python
   from docuhive.agents.base import run_structured
   res = run_structured("summarise", "summarise", {"text": text, "language": lang},
                        SummaryOut, document=view)        # pass the document so the privacy gate can decide
   res.value      # validated SummaryOut
   res.ai_run_id  # link it in Provenance / UI "How was this made?"
   ```
   For tool-using, streaming agents, use `run_agent(task, prompt_name, vars, tools, messages)`.
6. **Write the state through contracts:** `documents.apply_metadata(..., actor="ai:<task>", provenance=Provenance(...))`. AI never writes tables directly.
7. **Handle the harness outcomes explicitly:**
   - `NoAllowedRoute` → skip, and create a review notice explaining why (privacy)
   - `BudgetExceeded` → `ctx.defer(...)` for bulk jobs, or an error with a local-fallback offer for interactive use
   - a validation failure after the retry → the result stays `invalid` in `ai_runs`, with no partial writes
8. **Test it with `FakeModel`** (`tests/fakes/intel.py`). Cover:
   - the happy path
   - invalid output then a successful retry
   - a timeout falling back to the next route
   - a restricted document with only cloud routes → the model is never called
   - an `ai_runs` row written for every attempt

   No network in `make test`.
9. **Evaluate:** add cases to `evals/synthetic/` and, if it matters for quality, a scorer. Run `make eval` on two routes and paste the table in the PR.
10. **Make it visible and learnable** (learning-showcase skill): the run shows in "How was this made?", and `docs/learn/` has a note or an updated section.

## Strands essentials, as used here

| Concept | How DocuHive uses it |
|---------|----------------------|
| `Agent(model=…, system_prompt=…, tools=[…])` | built inside the harness per call. Feature code never builds one |
| Structured output | `run_structured` asks Strands for a Pydantic instance, validates it again (our domain rules), and retries once with the error text |
| Tools (`@tool`) | small, typed functions in `docuhive/agents/tools/`. **The user and the scope come from a closure, never from model arguments.** They return compact JSON-able dicts (ids, titles, short snippets), not whole documents |
| Agent loop | the model decides which tools to call, and the harness caps it (`max_tool_calls`, default 8) and the wall time |
| Streaming | `run_agent(..., stream=True)` yields token, tool_call, tool_result and done events, which the chat API maps to SSE |
| Model providers | `OllamaModel`, `AnthropicModel`, `OpenAIModel` (any OpenAI-compatible `base_url`), `BedrockModel`, and `LiteLLMModel` (`github_copilot/…`, experimental). Built lazily by `ai/router.py` from `routing.yaml` |
| Metrics | token usage from the Strands result goes to `ai_runs.tokens_*`, and cost comes from `routing.yaml` `pricing` |
| Embeddings | **not** part of Strands. Tiny per-provider clients live in `ai/embeddings.py` |

## Harness rules (enforced by review and tests)

- **Privacy first:** `privacy.is_restricted(doc)` runs before route selection. Restricted input runs only on `local: true` routes. The DB `CHECK (NOT restricted OR local)` on `ai_runs` must never be bypassed.
- **Every attempt logged**, with task, route, local flag, restricted flag, prompt version, status, tokens, cost, latency, output or error.
- **Deterministic work stays out of the model:** parsing, validation, arithmetic (`query_facts`), dedupe and I/O are plain Python. The model decides and extracts; code checks and computes.
- **Controlled vocabulary:** the model chooses from lists we pass in, and validation rejects anything else. New terms become proposals for review.
- **Small context, on purpose:** use head + tail truncation with limits from `routing.yaml`. Never send attachments or whole archives to triage.
- **No provider-specific code outside `ai/`.** Adding a provider means a new `kind` in `router.py` and `embeddings.py`, a `routing.yaml` example, and `docs/learn/model-providers.md` updated.
- **Copilot via LiteLLM** stays `experimental: true, enabled: false` by default, with a warning in the UI.

## Done when

The task has a typed output, a versioned prompt, a route with a local default, goes through the harness, handles all three outcomes, has FakeModel tests including the privacy case, has eval cases with numbers in the PR, and is visible in "How was this made?" with a learning note.
