# `apps/web/components/core`

**Overview.** Components for the platform screens: sign-in, the user menu, knowledge bases, tokens and the archive tools.

## What's here

| Path | What it is |
| --- | --- |
| [`login-form.tsx`](login-form.tsx) | Sign-in form |
| [`user-actions.tsx`](user-actions.tsx) | User menu: theme switch and sign-out |
| [`knowledge-bases.tsx`](knowledge-bases.tsx) | Saved document scopes, indexing status and owner-only editing |
| [`document-filters.tsx`](document-filters.tsx) | Category, type, tag, source, correspondent and date filters |
| [`api-tokens.tsx`](api-tokens.tsx) | Personal tokens, permissions and explicit local-consumer trust |
| [`custom-fields.tsx`](custom-fields.tsx) | Custom fields: list for everyone, add, edit and delete for administrators |
| [`duplicates.tsx`](duplicates.tsx) | Possible duplicate pairs with their signals and the two decisions |
| [`export-button.tsx`](export-button.tsx) | Downloads a ZIP export for a saved view or knowledge base |
| [`saved-views.tsx`](saved-views.tsx) | Saved views: create, edit, pin, share and delete |
| [`vault-health.tsx`](vault-health.tsx) | The last storage check and buttons to start a quick or full one |
| [`view-documents.tsx`](view-documents.tsx) | The documents a saved view matches, with paging and export |
| [capture.tsx](capture.tsx) | Phone capture with page ordering, rotation and persistent offline uploads |
| [operations-status.tsx](operations-status.tsx) | Live storage and backup warning banner |
| [`documents.tsx`](documents.tsx) | Documents list: filters, processing strip, selection and bulk edit; shared filter bar and table |
| [`document-detail.tsx`](document-detail.tsx) | One document: PDF preview, editing with AI/user provenance and unlock, facts, history, download, trash |
| [`search.tsx`](search.tsx) | Search with highlighted snippets and the list filters |
| [`upload.tsx`](upload.tsx) | Drag-and-drop upload with category and tags, following each file until it is stored |
| [`document-queues.tsx`](document-queues.tsx) | Quarantine with plain-language reasons and retry; trash with restore |
| [`vocabulary.tsx`](vocabulary.tsx) | Tags and senders; rename and merge for administrators |
| [`account.tsx`](account.tsx) | Password change and links to the other personal settings |
| [`setup-checklist.tsx`](setup-checklist.tsx) | Every area's setup checks on the dashboard, with the next action for each |

## Extending

Put shared primitives in `../ui`; keep feature components here small and typed.
