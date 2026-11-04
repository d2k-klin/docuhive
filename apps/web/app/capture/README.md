# `apps/web/app/capture`

**Overview.** A public shell for phone capture, containing no user data. It verifies the
signed-in account before sending files; the shell can reopen offline after an online visit.

## What's here

| Path | What it is |
| --- | --- |
| [page.tsx](page.tsx) | Renders the capture component outside the authenticated archive layout |

## Extending

Keep this shell independent of server-fetched user data so it stays safe to cache offline.
