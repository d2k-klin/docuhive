# `apps/web/tests`

**Overview.** Web unit tests (Vitest) and browser checks (Playwright): auth, navigation, the streaming proxy and UI consistency.

## What's here

| Path | What it is |
| --- | --- |
| [`ui/`](ui/) | Playwright checks |
| [`auth.test.ts`](auth.test.ts) | Sign-in redirect rules |
| [`nav.test.ts`](nav.test.ts) | Navigation by role |
| [`proxy.test.ts`](proxy.test.ts) | Proxy headers, streaming and cross-site rejection |

## Extending

Test logic and boundaries, not markup; browser checks live in `ui/`.
