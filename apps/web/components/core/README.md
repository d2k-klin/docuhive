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

## Extending

Put shared primitives in `../ui`; keep feature components here small and typed.
