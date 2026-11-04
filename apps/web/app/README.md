# `apps/web/app`

**Overview.** Routes and layouts. `(app)` holds the signed-in screens, `(auth)` the sign-in page, `api` the proxy to the Python API, and `dev` the design kitchen sink.

## What's here

| Path | What it is |
| --- | --- |
| [`(app)/`](%28app%29/) | Signed-in screens |
| [`(auth)/`](%28auth%29/) | Sign-in |
| [`api/`](api/) | Same-origin API routes |
| [`dev/`](dev/) | Design kitchen sink (development only) |
| [`globals.css`](globals.css) | Design tokens: font, type scale, control sizes, colours for light and dark |
| [`layout.tsx`](layout.tsx) | Root layout: fonts, theme and metadata |

## Extending

Add a screen as a folder under `(app)/` with a `page.tsx`, add its entry to `lib/nav.ts`, and give it loading, empty and error states.
