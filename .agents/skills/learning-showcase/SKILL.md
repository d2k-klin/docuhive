---
name: learning-showcase
description: "Keep DocuHive's learning purpose visible: every feature that uses Strands agents, the agent harness, tools, structured output, model providers, privacy routing, evals, embeddings or hybrid search must ship with a learning note in docs/learn, a runnable example in examples/learn, and an in-app 'How was this made?' trace. Use when adding or changing any AI/agent/eval/search feature, writing docs, or reviewing a PR that touches docuhive/ai, docuhive/agents, docuhive/index or evals."
---

# Learning showcase

DocuHive is a real, useful app **and** a teaching project. A developer should be able to clone it and learn, by reading, running and clicking:
- how to build agents with **Strands**
- how to wrap them in an **agent harness** (routing, privacy, budgets, audit)
- how to **evaluate** them
- how to do **RAG / hybrid search**

If a concept is in the code but not visible in these three places, it is not done.

## The three surfaces

### 1. Learning notes — `docs/learn/`
A path through the concepts, ordered from simple to advanced. Files are named `NN-<slug>.md` (e.g. `09-hybrid-search.md`), and `docs/learn/README.md` lists them with an estimated reading time per note. Notes 09 and 12 are OA's; the rest are CL's.

| # | Note | Concept | Where in the code |
|---|------|---------|-------------------|
| 01 | `strands-basics.md` | Agent, model, system prompt, first call | `examples/learn/01_hello_agent.py` |
| 02 | `structured-output.md` | Pydantic outputs, validation retry, controlled vocabulary | `agents/classify.py`, `agents/validators.py` |
| 03 | `model-providers.md` | Ollama, Anthropic, OpenAI, Bedrock, LiteLLM/Copilot; local vs cloud | `ai/router.py`, `routing.yaml` |
| 04 | `agent-harness.md` | why a harness: routing, fallbacks, budgets, `ai_runs` | `agents/base.py` |
| 05 | `privacy-routing.md` | restricted documents, local-only, the DB constraint | `ai/privacy.py` |
| 06 | `tools-and-agent-loop.md` | `@tool`, scoped tools, tool-call limits, streaming | `agents/ask.py`, `agents/tools/` |
| 07 | `numbers-without-hallucination.md` | computing with SQL tools instead of the LLM | `agents/tools/facts.py` |
| 08 | `embeddings-and-chunking.md` | chunking with metadata headers, pgvector, HNSW | `index/` |
| 09 | `hybrid-search.md` | FTS + vectors + RRF fusion | `search/hybrid.py`, `index/semantic.py` |
| 10 | `evals.md` | golden sets, scorers, calibration, the auto-apply gate | `evals/` |
| 11 | `email-triage-agent.md` | a cheap gatekeeper agent before the expensive pipeline | `agents/triage.py` |
| 12 | `pipelines-and-jobs.md` | an idempotent job queue around agents | `jobs/`, `agents/pipeline.py` |

**Note format** (keep it under about 1,200 words):
```markdown
# <Concept>

**In one sentence.** …
**Why DocuHive needs it.** the real problem in this app
## How it works            short explanation + one small diagram (mermaid or ASCII)
## In the code             links to files/functions (relative links, checked by the docs test)
## Run it                  `make learn EX=03` → what you will see
## See it in the app       which screen shows it (e.g. Settings → AI → Runs → a run)
## Try it yourself         1–3 exercises (change a route, break the schema, add a tool)
## Pitfalls we hit         real lessons from building it (update when you learn something)
## Further reading         official docs links
```

### 2. Runnable examples — `examples/learn/`
- `NN_<name>.py`: standalone, 30–120 lines, one concept each. They run with **FakeModel by default**, and against a real provider with `--provider ollama|anthropic|openai|bedrock|copilot`.
- They import from `docuhive` only where showing the real harness is the point (from example 04 onward). Examples 01–03 use plain Strands, so a learner sees the bare library first.
- `make learn` lists them, and `make learn EX=06 PROVIDER=ollama` runs one.
- `tests/unit/test_examples.py` runs every example with FakeModel in CI, so examples never rot.
- `examples/learn/README.md` holds the table of examples, with a link to the matching note.

### 3. In-app transparency — "How was this made?"
Every AI-produced value in the UI links to the run that produced it:
- **Document page** (`DocumentAIPanel`): each suggested or applied field shows a small "AI" badge. Clicking it opens the run.
- **Run detail** `/settings/ai/runs/[id]` (CL), the "Under the hood" view:
  - task, route, local/cloud badge and why (the privacy decision), prompt name and version (an expandable read-only prompt text)
  - input size (chars, tokens), the validated output (pretty JSON), validation retries, fallbacks taken, latency, tokens, cost
  - for agent runs: a **tool-call timeline** (tool, args, result summary, duration)
  - a "Learn about this" link to the matching `docs/learn/` note
- **Chat:** a collapsible "What I did" block per answer (searched, read, queried facts), with an "Under the hood" link to the run.
- **Settings → AI:** a "Learn" tab listing the learning path, with links to the notes on GitHub (open in a new tab).
- **Evals:** the latest committed synthetic report (`docs/evals/`) is linked from Settings → AI, so a learner can see how models compare.

## Procedure (every AI/agent/search/eval change)

1. Identify which concept your change teaches or alters (the table above, or a new row).
2. Update or create the learning note. Add a "Pitfalls we hit" entry if you discovered something.
3. Update or add the runnable example, and make sure `test_examples.py` passes.
4. Make sure the feature's runs appear in "How was this made?" (an `ai_run_id` stored and linked).
5. Mention the learning impact in the PR ("Learn: updated 06, new example 06b").
6. Keep the README's "What you'll learn" section in sync with the path.

## Style for learning content

- Plain language, second person, short sentences. Explain a term the first time it appears ("embedding: a list of numbers that captures meaning").
- Show the smallest working thing first, then the production version in the repo.
- Be honest about trade-offs and limits (e.g. "local 8B models miss correspondents ~15% of the time on our set").
- No marketing tone. No claims without a number or a link.

## Done when

The concept has a note in the path, a runnable example tested in CI, an in-app trace a user can click, and the PR says what a learner gains.
