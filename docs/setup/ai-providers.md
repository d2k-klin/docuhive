# AI providers and models

DocuHive uses AI to read and sort your documents, find them by meaning, and answer questions. You choose where that AI runs:

| Choice | What it means |
|--------|---------------|
| **Local (Ollama)** | Runs on your own computer. Private and free, but slower; it needs about 16–32 GB RAM for good models. |
| **Cloud** (Anthropic, OpenAI, AWS Bedrock) | Faster and often more accurate. The text of a document is sent to that provider when it is processed. |
| **Both** (recommended) | Local for bulk work (sorting, extracting, search), cloud for chat. Private documents always stay local. |

## 1. Local models with Ollama

1. Install Ollama from <https://ollama.com> and start it.
2. Download the default models:
   ```bash
   ollama pull gemma4:12b
   ollama pull qwen3:8b
   ollama pull qwen3:4b
   ollama pull bge-m3
   ```
3. If Ollama runs on another machine, set `DOCUHIVE_AI_OLLAMA_HOST` (default `http://localhost:11434`) in `.env`.

## 2. Cloud providers (optional)

Add only the keys you want to use to `.env`, then restart DocuHive:

| Provider | Setting |
|----------|---------|
| Anthropic (Claude) | `DOCUHIVE_AI_ANTHROPIC_API_KEY` |
| OpenAI, or any OpenAI-compatible server | `DOCUHIVE_AI_OPENAI_API_KEY`, plus optionally `DOCUHIVE_AI_OPENAI_BASE_URL` |
| AWS Bedrock | `DOCUHIVE_AI_AWS_PROFILE` and `DOCUHIVE_AI_AWS_REGION` (standard AWS credentials) |
| GitHub Copilot | experimental and off by default. Enable it in your overlay `routing.yaml` (`providers.copilot.enabled: true`) |

Keys are read from the environment only. They are never stored in the database or shown in the app.

## 3. Choose which model does what

Each task has its own route in `config/defaults/routing.yaml`. Override any part in your private overlay (`$DOCUHIVE_OVERLAY_DIR/routing.yaml`):

| Task | What it does | Default |
|------|--------------|---------|
| triage | decides whether an email contains a document worth keeping | `ollama/qwen3:4b` |
| classify | picks the category, type, sender, title and date | `ollama/gemma4:12b`, falling back to `ollama/qwen3:8b` |
| extract | reads amounts, due dates, contract terms | `ollama/qwen3:8b` |
| embed | turns text into numbers for meaning-based search | `ollama/bge-m3` |
| chat / analyse | answers your questions | `anthropic/claude-sonnet-5-5`, falling back to `ollama/qwen3:8b` |

The local defaults were measured on the synthetic set in [decision 0004](../decisions/0004-model-selection.md): Gemma 4 sorts documents far better, and qwen3 finds far more facts. Together they need about 17 GB of memory, which fits a 32 GB machine next to the embedding model. Ollama's `think` setting is off by default (`providers.ollama.think` in `routing.yaml`): thinking made answers no more accurate and 2–13 times slower.

To keep everything on your machine, set `privacy.local_only: true`. Health and identity documents are always processed locally; see [privacy routing](../learn/05-privacy-routing.md).

## 4. Check it

```bash
uv run docuhive ai check
```
This prints the effective routing (secrets masked) and checks each provider. In the app, **Settings → AI** shows the same information, plus usage and budgets.

## Budgets

Set a monthly spending cap per cloud provider under `budgets:` in `routing.yaml`, and fill in the current prices under `pricing:`. When a cap is reached, bulk work waits until next month, and chat offers the local model instead.
