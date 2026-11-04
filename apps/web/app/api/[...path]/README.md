# `apps/web/app/api/[...path]`

**Overview.** The streaming proxy to the Python API. It forwards the session cookie and CSRF header, and streams uploads and chat answers without buffering.

## What's here

| Path | What it is |
| --- | --- |
| [`route.ts`](route.ts) | Proxy handler for every HTTP method |

## Extending

Header and streaming rules live in `lib/proxy.ts`; change them there, with a test in `tests/proxy.test.ts`.
