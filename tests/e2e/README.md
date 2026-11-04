# `tests/e2e`

**Overview.** Real browser journeys against QA's seeded stack, with no route interception.

## What's here

| Path | Purpose |
| --- | --- |
| [playwright.config.ts](playwright.config.ts) | All three widths, light/dark, zero retries |
| [journeys.spec.ts](journeys.spec.ts) | Login and first test-ahead journeys |
| [ui-consistency.spec.ts](ui-consistency.spec.ts) | Axe, typography, control and overflow checks |
| [streaming.spec.ts](streaming.spec.ts) | Real incremental SSE through the authenticated web proxy |

## Extending

`make qa-up qa-e2e`. Each test title carries requirements and milestone tags.
Pending journeys use `test.fixme` with a [tracked blocker](../../docs/Developer-QA/bugs.md).
Screenshots are evidence only until the owner approves baselines; do not auto-approve them.
The sweep covers the nine static production pages. `/dev/ui` intentionally returns
404 in production and has a separate guard check; its control demo is verified by
the existing development UI suite. Dynamic run details and loaded archive states remain pending.
