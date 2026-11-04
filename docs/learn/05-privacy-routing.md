# Privacy routing

**In one sentence.** Before any model call, the harness checks whether the document is private, and if it is, only local models may see it.

**Why DocuHive needs it.** Health records, ID cards and similar documents should never leave your network, even when you use a cloud model for everything else.

## How it works

```
document ──► is_restricted?  (local_only setting · restricted category or its parent · restricted tag)
                │ no                        │ yes
                ▼                           ▼
     all routes for the task       only routes with local: true
                │                           │ none configured?
                ▼                           ▼
           model call                skip + review notice "AI skipped: restricted"
```

- **Before classification** the category is unknown. With `classify_unknown_locally: true` (the default), new documents are classified locally first. If the result is restricted, every later task stays local.
- **Every attempt is logged** in `ai_runs` with `restricted` and `local` flags. A database constraint (`CHECK (NOT restricted OR local)`) makes it impossible to record a restricted run on a cloud model.
- **In chat**, restricted documents found by a cloud-routed chat are masked ("content withheld"), and the user can switch the chat to "Local only".

## In the code

- [`ai/privacy.py`](../../services/docuhive/src/docuhive/ai/privacy.py): `is_restricted`
- [`ai/router.py`](../../services/docuhive/src/docuhive/ai/router.py): `resolve(task, restricted=…)` filters the routes
- [`agents/base.py`](../../services/docuhive/src/docuhive/agents/base.py): the harness applies the gate before every call
- [`config/defaults/routing.yaml`](../../config/defaults/routing.yaml): the `privacy:` section
- the restricted flags on categories: [`config/defaults/taxonomy.yaml`](../../config/defaults/taxonomy.yaml)

## See it in the app

Settings → AI → Runs: open a run of a health document. It shows `restricted` and a local route. Settings → AI also shows the privacy summary for the month.

## Try it yourself

1. Set every task to a cloud route in your overlay `routing.yaml` and upload a medical letter. You'll get a review notice instead of a cloud call.
2. Add a `lan` provider with `local: true` (an OpenAI-compatible server on your network) and repeat. The document is processed there.

## Pitfalls we hit

- The gate has to run on *every* path, including email triage snippets, query embeddings in search, and chat tools, not only classification.
- "Unknown" is not "safe": a document has no category until it is classified, which is why the first classification is local.

## Further reading

- [AI providers setup](../setup/ai-providers.md)
- [Strands Agents model providers](https://strandsagents.com/docs/user-guide/concepts/model-providers/)
