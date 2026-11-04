# `apps/web/components/intel`

**Overview.** Components for the AI and email features, including the slots the platform screens render: dashboard widgets, the document AI panel, similar documents, the search hint and the setup-wizard steps.

## What's here

| Path | What it is |
| --- | --- |
| [`common.tsx`](common.tsx) | Shared helpers for the AI and email screens |
| [`DashboardWidgets.tsx`](DashboardWidgets.tsx) | Dashboard widgets: review count, email status, deadlines |
| [`DocumentAIPanel.tsx`](DocumentAIPanel.tsx) | AI suggestions and history on a document page |
| [`Markdown.tsx`](Markdown.tsx) | Sanitised Markdown rendering for answers |
| [`SearchModeHint.tsx`](SearchModeHint.tsx) | Hint shown when semantic search is unavailable |
| [`SetupSteps.tsx`](SetupSteps.tsx) | Setup-wizard steps for AI, privacy, email and notifications |
| [`SimilarDocuments.tsx`](SimilarDocuments.tsx) | Similar documents on a document page |

## Extending

Slot names and props are part of the [contracts](../../../../docs/shared/contracts.md#7-web-ownership-appsweb); change them only through a contract update.
