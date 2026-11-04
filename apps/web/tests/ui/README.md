# `apps/web/tests/ui`

**Overview.** Playwright checks for the shell, the sign-in flow and the control-height rule from the design system.

## What's here

| Path | What it is |
| --- | --- |
| [`archive-tools.spec.ts`](archive-tools.spec.ts) | Saved view create, pin and delete, plus the custom fields and duplicates pages, with responsive and accessibility checks |
| [`auth-flow.spec.ts`](auth-flow.spec.ts) | Sign-in and sign-out flow |
| [`controls.spec.ts`](controls.spec.ts) | Every control has the same height |
| [`knowledge.spec.ts`](knowledge.spec.ts) | Real saved-scope CRUD and token lifecycle, with responsive and accessibility checks |
| [`shell.spec.ts`](shell.spec.ts) | The app shell renders and navigates |

## Extending

Add new controls to `/dev/ui` so `controls.spec.ts` covers them.
