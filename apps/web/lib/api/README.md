# `apps/web/lib/api`

**Overview.** The typed API client. `openapi.json` and `schema.d.ts` are generated from the Python API; `client.ts` and `server.ts` wrap them for the browser and for server components.

## What's here

| Path | What it is |
| --- | --- |
| [`client.ts`](client.ts) | Typed client for the browser (adds the CSRF header) |
| [`openapi.json`](openapi.json) | API schema exported from the Python app (generated) |
| [`schema.d.ts`](schema.d.ts) | TypeScript types for the API (generated) |
| [`server.ts`](server.ts) | Typed client for server components (forwards the session) |

## Extending

Never edit the generated files; run `make gen-api` and commit the result.
