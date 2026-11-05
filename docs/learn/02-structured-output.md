# Structured output and controlled categories

**In one sentence.** The model chooses from your category list; validation checks its answer before any document changes.

**Why DocuHive needs it.** An archive becomes hard to browse if every invoice invents a new name for the same category.

## How it works

The category list starts with the shipped taxonomy and any private overlay. An administrator can enable predefined categories and add custom categories in Vocabulary. These preferences live in the existing settings table, rather than changing a source file. Every worker reads the latest preferences when it starts analysis.

The classification prompt receives only enabled categories, including their descriptions. The structured output validator rejects any other category ID. The existing confidence policy still decides whether the result is applied or offered for review. Saving category preferences does not reclassify old documents or unlock manual edits.

Disabled categories remain in the complete taxonomy. This preserves labels on old documents and, especially, their local-only privacy restrictions. A parent category includes its children when you filter documents.

## In the code

- [Category preferences and validation](../../services/docuhive/src/docuhive/taxonomy/routes.py)
- [Classification input and output validation](../../services/docuhive/src/docuhive/agents/classify.py)
- [The privacy gate](../../services/docuhive/src/docuhive/ai/privacy.py)
- [Progress from real jobs and runs](../../services/docuhive/src/docuhive/ai/progress.py)

## Run it

Run `make learn EX=02`, or `uv run python examples/learn/02_categories.py`. The example validates a synthetic category choice and rejects a disabled choice without a provider or database.

## See it in the app

Open Documents → Categories. After an upload, AI status shows queued, in progress, completed or needing attention. On the document page, open the AI run from its history to see the structured answer. A suggested category is shown separately until it has been accepted or automatically applied.

## Try it yourself

1. Add a category with a precise description, then analyse a synthetic document that belongs there.
2. Disable a category and confirm it is absent from the next classification prompt.
3. Disable a local-only category and confirm its existing documents still stay on local AI.

## Pitfalls we hit

A cached taxonomy hides preference changes from already-running workers. Cache the file defaults, then read the saved preferences for each analysis. Removing disabled categories entirely would also remove privacy rules for documents already assigned to them.
