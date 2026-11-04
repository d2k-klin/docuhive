# `apps/web`

**Overview.** The DocuHive web app: Next.js App Router, TypeScript, Tailwind and shadcn/ui. It talks only to the Python API, through its own same-origin proxy. Run it from the repo root with `make dev`.

## What's here

| Path | What it is |
| --- | --- |
| [`app/`](app/) | Routes and layouts |
| [`components/`](components/) | React components |
| [`lib/`](lib/) | Shared web helpers: the typed API client, the proxy rules, navigation, auth helpers, UI strings and control classes |
| [`tests/`](tests/) | Web unit tests (Vitest) and browser checks (Playwright): auth, navigation, the streaming proxy and UI consistency |
| [`AGENTS.md`](AGENTS.md) | Notes for coding agents working on the web app |
| [`components.json`](components.json) | shadcn/ui configuration |
| [`eslint.config.mjs`](eslint.config.mjs) | ESLint configuration |
| [`next-env.d.ts`](next-env.d.ts) | Next.js type declarations (generated) |
| [`next.config.ts`](next.config.ts) | Next.js configuration |
| [`package.json`](package.json) | Web workspace scripts and dependencies |
| [`playwright.config.ts`](playwright.config.ts) | Playwright configuration for the browser checks |
| [`postcss.config.mjs`](postcss.config.mjs) | PostCSS configuration for Tailwind |
| [`proxy.ts`](proxy.ts) | Redirects signed-out visitors to the sign-in page |
| [`tailwind.config.ts`](tailwind.config.ts) | Tailwind theme mapped to the design tokens |
| [`tsconfig.json`](tsconfig.json) | TypeScript configuration (strict) |
| [`vitest.config.ts`](vitest.config.ts) | Vitest configuration |

## Extending

Follow the [`docuhive-ui`](../../.agents/skills/docuhive-ui/SKILL.md) skill for every screen: tokens only, one control height, and loading, empty and error states. Regenerate the API types with `make gen-api` after backend changes.
