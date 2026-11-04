# `apps/web/app/(app)`

**Overview.** The signed-in application: the shell layout (navigation, theme, user menu) and one folder per screen.

## What's here

| Path | What it is |
| --- | --- |
| [`analyses/`](analyses/) | Saved analyses |
| [`ask/`](ask/) | Chat with your documents |
| [`duplicates/`](duplicates/) | Possible duplicates waiting for a decision |
| [`knowledge/`](knowledge/) | Saved document scopes and indexing status |
| [`reminders/`](reminders/) | Upcoming deadlines |
| [`review/`](review/) | Review queue for AI suggestions |
| [`settings/`](settings/) | Settings: API tokens, custom fields, storage health, AI providers and runs, notifications |
| [`views/`](views/) | Saved views and the documents each one matches |
| [`sources/`](sources/) | Email accounts, backfills and the triage log |
| [`layout.tsx`](layout.tsx) | The app shell: navigation, theme switch and user menu |
| [`page.tsx`](page.tsx) | Dashboard |

## Extending

New screens get a folder with `page.tsx`, a nav entry in `lib/nav.ts`, and a row in the table above.
