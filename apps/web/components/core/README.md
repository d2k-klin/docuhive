# `apps/web/components/core`

**Overview.** Components for the platform screens: sign-in and the user menu.

## What's here

| Path | What it is |
| --- | --- |
| [`login-form.tsx`](login-form.tsx) | Sign-in form |
| [`user-actions.tsx`](user-actions.tsx) | User menu: theme switch and sign-out |
| [`knowledge-bases.tsx`](knowledge-bases.tsx) | Saved document scopes, indexing status and owner-only editing |
| [`document-filters.tsx`](document-filters.tsx) | Category, type, tag, source, correspondent and date filters |
| [`api-tokens.tsx`](api-tokens.tsx) | Personal tokens, permissions and explicit local-consumer trust |

## Extending

Put shared primitives in `../ui`; keep feature components here small and typed.
