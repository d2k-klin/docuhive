# `apps`

**Overview.** User-facing applications. Today that is the Next.js web app; a native mobile app is out of scope (the web app installs as a PWA).

## What's here

| Path | What it is |
| --- | --- |
| [`web/`](web/) | The DocuHive web app: Next.js App Router, TypeScript, Tailwind and shadcn/ui |

## Extending

Add a new app as its own npm workspace under `apps/` and register it in the root `package.json`.
