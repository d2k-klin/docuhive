# `apps/web/public`

**Overview.** Public capture assets, including the service worker and the IndexedDB upload
queue shared between it and the capture page. None contains user data.

## What's here

| Path | What it is |
| --- | --- |
| [sw.js](sw.js) | Caches only the public capture shell/static assets and supports background retry |
| [capture-queue.js](capture-queue.js) | Durable, account-bound upload queue with cross-tab leases and backoff |
| [capture-queue.d.ts](capture-queue.d.ts) | Types for the queue used by TypeScript callers |
| [capture-192.png](capture-192.png) | Small generated app icon |
| [capture-512.png](capture-512.png) | Large generated maskable app icon |

## Extending

Never cache authenticated pages, document content or API responses. Queued bytes are removed
only after successful intake; errors retain their files and remain actionable.
