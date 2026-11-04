# CL-01 — AI layer: providers, router, harness, privacy, budgets (CL-M0, CL-M1)

## CL-M0 (part 1) — Provider spike (standalone)

**Goal:** confirm that Strands structured output works reliably on every provider before you design around it. **Location:** `spikes/cl/providers/` (committed for reference; deleted at v1).

### Tasks
1. Write `spikes/cl/providers/run.py`:
   - It takes 10 synthetic document texts (German and English: invoice, contract, insurance letter, payslip, receipt) and a Pydantic model like the classify output in CL-02.
   - It calls `Agent(model=...).structured_output(Model, prompt)` on every provider you have access to:

     | Provider | How |
     |----------|-----|
     | Ollama | `OllamaModel(host, model_id)`: try `qwen3:4b`, `qwen3:8b`, `llama3.1:8b` and `mistral-small` (whatever is current and fits RAM) |
     | Anthropic | `AnthropicModel`: e.g. `claude-haiku-5-5` for bulk, `claude-sonnet-5-5` for chat |
     | OpenAI | `OpenAIModel` |
     | Bedrock | `BedrockModel` (any Claude or Nova model enabled in your account) |
     | GitHub Copilot | `LiteLLMModel(model_id="github_copilot/<model>")`: experimental. LiteLLM runs a device-flow login on first use and stores the token itself |

2. Record, per provider and model:
   - valid-JSON rate
   - schema-valid rate
   - latency p50
   - input/output tokens (from the Strands result metrics)
   - any quirks (e.g. tool-calling support, max context)
3. Also measure embeddings, which **Strands does not provide**: Ollama `/api/embed` with `bge-m3` and `nomic-embed-text`, OpenAI `text-embedding-3-small`, and Bedrock Titan/Cohere embed. Record dims, latency for 32 chunks, and multilingual sanity (does the German query "Stromrechnung" find the English "electricity invoice" text?).
4. Write the results to `spikes/cl/providers/RESULTS.md`, ending with a recommendation for the default `routing.yaml`.

### Acceptance
- `RESULTS.md` exists, with a default local model per task that reaches ≥ 95% schema-valid output on the 10 texts.

---

## CL-M1 — AI layer in the repo

**Uses:** I1 (skeleton), I2 (`config`, `db`, `jobs`). Until OA-M2 is done, use `tests/fakes/core.py` and read YAML directly.

### 1.1 Settings — `docuhive/ai/settings.py`
`AISettings(BaseSettings)`, with env prefix `DOCUHIVE_AI_`:
- `OLLAMA_HOST` (default `http://localhost:11434`)
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`
- `AWS_PROFILE`, `AWS_REGION`
- `LITELLM_*` passthrough
- `ENABLED` (default `true`). If it is false, `startup()` registers nothing and every AI job is skipped with the note "AI disabled".

Add the `[project.optional-dependencies] ai = [...]` extra: `strands-agents`, `strands-agents[ollama,anthropic,openai,litellm]` (whatever extras exist in the version you pin), `boto3`, `httpx`.

### 1.2 Routing config — `config/defaults/routing.yaml` (CL-owned)
```yaml
version: 1
providers:                     # what is configured; secrets come from env, never from YAML
  ollama:    { kind: ollama, host: ${DOCUHIVE_AI_OLLAMA_HOST}, local: true }
  anthropic: { kind: anthropic, local: false }
  openai:    { kind: openai, local: false }          # base_url optional -> any OpenAI-compatible
  bedrock:   { kind: bedrock, local: false }
  copilot:   { kind: litellm, prefix: github_copilot, local: false, experimental: true, enabled: false }
  # an OpenAI-compatible server on the LAN (LM Studio, vLLM) can be declared with local: true
tasks:
  triage:   { route: ollama/qwen3:4b }
  classify: { route: ollama/qwen3:8b }
  extract:  { route: ollama/qwen3:8b }
  embed:    { route: ollama/bge-m3, dims: 1024 }
  chat:     { route: anthropic/claude-sonnet-5-5, fallback: [ollama/qwen3:8b] }
  analyse:  { route: anthropic/claude-sonnet-5-5, fallback: [ollama/qwen3:8b] }
privacy:
  local_only: false
  classify_unknown_locally: true         # see 1.4
  restricted_tags: [private]
  # restricted categories come from taxonomy (Category.restricted)
  on_restricted_without_local: skip      # skip | error
budgets:                                  # USD per calendar month; omitted = unlimited
  anthropic: 10
  openai: 5
  bedrock: 10
pricing:                                  # USD per 1M tokens; user-maintained, check provider pages
  anthropic/claude-sonnet-5-5: { in: 0.0, out: 0.0 }   # fill in current prices
  # local models cost 0
limits:
  timeout_s: { triage: 60, classify: 120, extract: 120, chat: 300 }
  retries: 2
```
- `${VAR}` interpolation from env happens at load time.
- The YAML is validated with a Pydantic model `RoutingConfig`, and errors are reported with their path.
- `docuhive ai check` prints the effective routing (secrets masked) and pings each enabled provider (Ollama `/api/tags` to confirm the model is present; a tiny completion for the cloud providers, only when run with `--ping`).

### 1.3 Router — `docuhive/ai/router.py`
```python
@dataclass(frozen=True)
class Route:
    provider: str     # key in providers
    model: str
    local: bool

def resolve(task: str, *, restricted: bool) -> list[Route]: ...
    # ordered: primary then fallbacks; filtered: if restricted or local_only -> only local routes
def model_for(route: Route) -> strands.models.Model: ...   # cached per route; lazy imports per kind
```
- **Lazy imports:** a missing optional dependency raises `ProviderUnavailable("pip install docuhive[ai]")`.
- **Copilot:** used only if `enabled: true`. Log a warning once that it is experimental and unofficial for this use.

### 1.4 Privacy gate — `docuhive/ai/privacy.py`
```python
def is_restricted(doc: DocumentView | None, taxonomy: Taxonomy) -> bool:
    # True if: privacy.local_only, or doc.category is a restricted category (or a child of one:
    # "health" restricted => "health/medical" restricted), or any doc tag in restricted_tags,
    # or doc.category is None AND hints suggest restricted (not used in v1)
```
- **Classification chicken-and-egg:** before classification, the category is unknown. **Rule:** if any route for `classify` is non-local and `privacy.classify_unknown_locally` is true (default **true**), unclassified documents are classified **locally first**. If the result is a restricted category, all later tasks stay local. If no local route exists, `on_restricted_without_local` applies.
- **Every** call through the harness (§1.5) passes through `is_restricted`. There is no API for calling a model that bypasses it.

### 1.5 Agent harness — `docuhive/agents/base.py`
```python
class StructuredResult(Generic[T]):
    value: T
    ai_run_id: int
    route: Route
    prompt_version: str

def run_structured(task: str, prompt_name: str, variables: dict, output: type[T], *,
                   document: DocumentView | None = None) -> StructuredResult[T]: ...

def run_agent(task: str, prompt_name: str, variables: dict, tools: list, messages: list, *,
              documents_restricted: bool = False, stream: bool = True) -> AgentRun: ...
    # AgentRun: async iterator of events (token/tool_call/tool_result/done) + final ai_run_id
```
Steps inside `run_structured`:
1. Load the prompt with `config.prompt(prompt_name)` → `(template, version)`. The template uses `str.format_map` with escaping, so no Jinja dependency.
2. `restricted = privacy.is_restricted(document, taxonomy)`, then `routes = router.resolve(task, restricted=restricted)`. If it is empty, raise `NoAllowedRoute` (callers turn this into a skip with a reason).
3. Run `budgets.check(route)` for each route in order, skipping any over budget. If all are over budget, raise `BudgetExceeded`.
4. Call `Agent(model=model_for(route), system_prompt=…).structured_output(output, prompt)` with a timeout from `limits.timeout_s[task]`.
   - Provider errors (timeout, 5xx, rate limit) are retried `limits.retries` times with backoff, then the next route.
   - A validation error is retried **once** on the same route, with the validation message appended ("Your previous answer was invalid: … Return only valid JSON matching the schema.").
5. Log `ai_runs` (below) for **every** attempt, successful or failed.
6. Return the result.

### 1.6 `ai_runs` — intel migration `0001_ai_runs`
```sql
CREATE TABLE ai_runs (
  id            bigserial PRIMARY KEY,
  at            timestamptz NOT NULL DEFAULT now(),
  task          text NOT NULL,
  document_id   text,                         -- FK to documents(id) ON DELETE SET NULL (op.create_foreign_key)
  provider      text NOT NULL,
  model         text NOT NULL,
  local         boolean NOT NULL,
  restricted    boolean NOT NULL,             -- was the input restricted? (must imply local=true)
  prompt_version text NOT NULL,
  status        text NOT NULL,                -- ok | invalid | error | timeout | skipped
  tokens_in     int, tokens_out int,
  cost_usd      numeric(10,5),
  latency_ms    int,
  output        jsonb,                        -- parsed output (or raw text on failure, truncated 20 KB)
  error         text
);
CREATE INDEX ai_runs_doc ON ai_runs (document_id);
CREATE INDEX ai_runs_month ON ai_runs (provider, at);
ALTER TABLE ai_runs ADD CONSTRAINT restricted_is_local CHECK (NOT restricted OR local);
```
The `CHECK` constraint is a database-level guarantee for AI-03: a restricted input can never be logged as a non-local run.

### 1.7 Budgets — `docuhive/ai/budgets.py`
- Spend this month is `SUM(cost_usd)` from `ai_runs` per provider for the current calendar month (UTC).
- `check(route)` raises `BudgetExceeded(provider, spent, cap)` if `spent >= cap`.
- **Job behaviour:** AI jobs catching `BudgetExceeded` call `ctx.defer(first_day_next_month, "budget")` for bulk work (backfill, reclassify, re-embed). Interactive chat returns error `budget_exceeded`, and the UI offers the fallback local route.
- **80% warning:** emit a notification (CL-M7) once per provider per month.

### 1.8 Fake provider for tests — `tests/fakes/intel.py`
- A `FakeModel` implementing the Strands model interface. It returns canned outputs keyed by `prompt_name` (and optionally by a substring of the document text). It can be configured to return invalid JSON once, to raise a timeout, or to report tokens.
- `provider kind: fake` is available only when `DOCUHIVE_ENV=test`.

### 1.9 API — `docuhive/ai/routes.py` (prefix `/api/ai`)
| Endpoint | Returns |
|----------|---------|
| `GET /api/ai/providers` | configured providers, enabled, local, reachable (cached 60 s), experimental flag |
| `GET /api/ai/routing` | effective routing per task (masked) |
| `GET /api/ai/usage?month=2026-11` | per provider: runs, tokens, cost, budget, % used |
| `GET /api/ai/runs?task=&status=&document_id=&cursor=` | `ai_runs` list (admin) |
| `GET /api/ai/runs/{id}` | full row including output |

Register the router in `api/routers.py` (touchpoint) and the handlers in `worker/handlers.py` (touchpoint).

### 1.10 `docuhive/ai/startup.py`
`startup()` loads the routing (validating it) and imports the handler modules, so they register. From CL-M5 it also registers the semantic fn. It must be safe to call twice.

### 1.11 UI — `app/(app)/settings/ai/page.tsx` (read-only in v1)
- A providers table (status dots), a routing table (task → route → fallbacks, a local badge), usage this month (bars vs. budget), and the last 50 runs with a link to the document.
- Uncomment the "Settings → AI" nav entry in `lib/nav.ts`.
- **Editing routing in the UI is backlog.** In v1 the overlay `routing.yaml` is the source of truth.

### 1.12 Setup, "Under the hood", learning
- **`GET /api/ai/setup-status`** → `list[SetupCheck]`:
  - `ai.provider` (at least one reachable, required)
  - `ai.models` (every routed Ollama model present; otherwise the message shows the `ollama pull …` command)
  - `ai.routing` (every task routed)
  - `ai.privacy` (a mode chosen)
  - `ai.embed` (an embedding model set)
  - `ai.auto_apply` (`optional`; the message explains it stays off until evals pass)
- **Wizard steps** in `components/intel/SetupSteps.tsx` (`intelSetupSteps`): "AI provider" (Local / Cloud / Both, test connection, copy-paste `.env` lines for keys), "Models" (recommended routing with plain-language task names), "Privacy" (local-only or restricted categories). The email and notification steps are added in CL-M4 and CL-M7. Follow the `guided-experience` skill.
- **Run detail page** `app/(app)/settings/ai/runs/[id]/page.tsx`, the "Under the hood" view from the [`learning-showcase` skill](../../.agents/skills/learning-showcase/SKILL.md):
  - route, local/cloud and the privacy decision
  - prompt name@version with the prompt text (a new endpoint, `GET /api/ai/prompts/{name}?version=`)
  - input size, validated output, retries and fallbacks, tokens, cost, latency
  - a tool-call timeline (from CL-M6)
  - a "Learn about this" link

  `DocumentAIPanel` badges and the chat's "What I did" link here.
- **Learn tab** in Settings → AI: the learning path, with links to `docs/learn/` on GitHub and to the latest synthetic eval report.
- **Learning notes and examples owned by CL**, delivered with the milestone that builds the concept:

  | Milestone | Notes + examples |
  |-----------|------------------|
  | CL-M1 | 01 strands-basics, 02 structured-output, 03 model-providers, 04 agent-harness, 05 privacy-routing |
  | CL-M3 | 10 evals |
  | CL-M4 | 11 email-triage-agent |
  | CL-M5 | 08 embeddings-and-chunking |
  | CL-M6 | 06 tools-and-agent-loop, 07 numbers-without-hallucination |

  Examples 01–03 use plain Strands; from 04 on they use the harness. `tests/unit/test_examples.py` runs them all with FakeModel.

### 1.13 Tests
- Router: restricted filtering, fallback order, local_only, disabled Copilot.
- Privacy:
  - a restricted category (including a child category), and a restricted tag
  - classify-unknown-locally
  - `NoAllowedRoute`
  - the DB `CHECK` constraint rejects `restricted=true, local=false`
- Harness:
  - a validation retry succeeds
  - a provider timeout falls to the fallback
  - every attempt is logged
  - cost is computed from pricing
  - budget skip
- Budgets: month boundaries, defer for bulk.

### Acceptance
- `docuhive ai check` shows the routing, and every configured provider is reachable.
- With FakeModel, `run_structured("classify", …)` returns a valid object and writes `ai_runs` rows. With a restricted document and only cloud routes, no model is called and the reason is "skipped".
- The `ai_runs` constraint test passes.
