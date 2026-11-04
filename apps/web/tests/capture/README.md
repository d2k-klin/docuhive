# `apps/web/tests/capture`

**Overview.** Browser checks for phone capture, including offline reloads against production
assets. The rest of the UI suite uses the development server for the control gallery.

## What's here

| Path | What it is |
| --- | --- |
| [capture.spec.ts](capture.spec.ts) | Accessibility, page ordering, IndexedDB persistence, retries and offline recovery |

## Extending

Run `make test-capture`. API responses use synthetic fixtures; phone/NAS acceptance is separate.
