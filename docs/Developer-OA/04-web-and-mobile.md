# OA-04 — Web shell, document UI, PWA capture, consume folder (OA-M5, OA-M6)

## OA-M5 — Web shell + document UI

**Goal:** daily use without touching the CLI. CL's pages plug into your shell. **Unblocks:** I6.

### 5.1 Stack & conventions (`apps/web`)
- Next.js 15 App Router, TypeScript strict, Tailwind, and shadcn/ui (`components/ui`).
- **Server components by default.** Client components only for interactivity (filters, forms, upload, chat).
- **Data access:** `lib/api/client.ts`, which uses `openapi-fetch` with the generated `schema.d.ts`:
  - `serverClient()`, for server components and route handlers: calls `DOCUHIVE_API_URL` directly and forwards the `dh_session` cookie from `cookies()`.
  - `browserClient()`, for client components: calls the same-origin `/api/*` (the BFF proxy) and always adds `X-DocuHive-CSRF: 1`.
- No global state library. URL search params hold the list/filter state. Add TanStack Query only if a real need appears.
- i18n: English UI strings in `lib/i18n/en.ts` (a single object), so German can be added later without refactoring.
- Accessibility (WEB-03): every input has a label, and focus is visible. Dialogs come from shadcn (Radix). Lists are keyboard-navigable. Colour contrast is AA.

### 5.2 BFF proxy — `app/api/[...path]/route.ts`
- Proxies every method to `${DOCUHIVE_API_URL}/api/<path>?<query>`.
- Forwards the `cookie`, `content-type`, `range`, `if-none-match`, `x-docuhive-csrf` and `authorization` headers.
- Returns the status, the headers (including `set-cookie`, `content-disposition`, `etag`) and the **streamed** body.
- Request bodies are streamed too: `duplex: "half"`, no buffering, so large multipart uploads work.
- **SSE:** `text/event-stream` responses are passed through unbuffered (`cache-control: no-cache`, `x-accel-buffering: no`). Verify it with `/api/system/sse-test`: the 10 ticks must arrive about 500 ms apart in the browser, not all at the end.
- Set `export const dynamic = "force-dynamic"` and `runtime = "nodejs"`.

### 5.3 Shell
- `middleware.ts`: no `dh_session` cookie and a path outside `/login` and the static assets → redirect to `/login?next=…`.
- `app/(auth)/login/page.tsx`: a username/password form that posts via the proxy, then redirects to `next`. Errors include the rate-limit message.
- `app/(app)/layout.tsx`:
  - **Sidebar nav** from `lib/nav.ts` (the shared touchpoint: `{href, label, icon, section: "core" | "intel", adminOnly?}`).
  - **Top bar** with search, user menu and logout.
  - **Vault-unavailable banner**, from `/api/system/vault`, polled every 60 s.
  - **Mobile:** a collapsible sidebar and a bottom "Capture" button.
- Core nav entries: Dashboard, Documents, Search, Upload, Capture (mobile), Quarantine (badge), Vocabulary, Settings.

### 5.4 Pages (OA)
| Route | Content |
|-------|---------|
| `/` Dashboard | Core widgets: recent documents (10), processing status (counts by status), documents per month (simple bar list; no chart library needed), quarantine count, vault status + free space. Then `<IntelDashboardWidgets/>` (CL slot) |
| `/documents` | Filter bar (category and type from `/api/taxonomy`, or the fixture until CL ships it; correspondents and tags with typeahead; date range via native `<input type="date">`; source). Sort. Grid/list toggle with thumbnails. Multi-select → bulk edit dialog (category, type, correspondent, add/remove tags, shared). Cursor "Load more" |
| `/documents/[id]` | Left: preview `<iframe src="/api/documents/{id}/archive?inline=1">` (native viewer), with an image fallback for phones whose viewer is poor (thumb + "Open PDF"). Right: metadata form (inline edit → PATCH), facts table (read-only here; CL's panel shows suggestions), source/provenance, notes, actions (download original/archive, trash, share toggle), then `<DocumentAIPanel documentId/>` and `<SimilarDocuments documentId/>` (CL slots) |
| `/search` | Query box (debounced 300 ms), mode toggle hybrid/fts/semantic (semantic disabled if `semantic_available=false`), `<SearchModeHint/>` slot, filters (the same component as on `/documents`), results with a thumbnail and the snippet (the `\u0002…\u0003` markers are rendered as `<mark>` by splitting the string, **never** with `dangerouslySetInnerHTML`) |
| `/upload` | Drag-and-drop zone plus `<input type="file" multiple>`, with per-file progress (XHR upload progress events), result rows (staged / duplicate → link / rejected reason), and a "combine images into one document" checkbox |
| `/quarantine` | Table of reason, filename, size and date, with Retry and Discard actions |
| `/vocabulary` | Tags and correspondents tabs: search, rename, multi-select merge, usage count |
| `/settings/account` | Change password, active sessions (revoke) |
| `/settings/tokens` | Create a token (scopes checkboxes; shown once, with a copy button), list, revoke. Includes an iOS Shortcut how-to snippet for uploading with an `upload`-scope token |
| `/settings/users` | Admin: list, create, disable, reset password, role |
| `/settings/system` | Admin: vault status, job list with filters, retry dead jobs |

### 5.5 Slots for CL (I9)
Create these files exactly as listed in contracts §7, each returning `null`, then render them in their slots:
- `components/intel/DashboardWidgets.tsx`
- `components/intel/DocumentAIPanel.tsx`
- `components/intel/SimilarDocuments.tsx`
- `components/intel/SearchModeHint.tsx`

From then on CL owns them. Add CL's nav entries as **commented placeholders** in `lib/nav.ts` (Review, Ask, Analyses, Sources, Reminders, Settings → AI, Settings → Notifications). CL uncomments them when their pages exist.

### 5.6 Design system, setup wizard, palette, editing UX
Load the [`docuhive-ui`](../../.agents/skills/docuhive-ui/SKILL.md), [`guided-experience`](../../.agents/skills/guided-experience/SKILL.md), [`document-editing`](../../.agents/skills/document-editing/SKILL.md) and [`document-chat`](../../.agents/skills/document-chat/SKILL.md) skills.

1. **Tokens first** (before any page):
   - `app/globals.css` and the Tailwind mapping, exactly as in the `docuhive-ui` skill
   - Inter via `next/font`
   - `lib/ui/control.ts`
   - restyle every shadcn primitive you add to use `control`
   - the theme toggle in the user menu
2. **`/dev/ui` kitchen sink** (only when `NODE_ENV !== "production"`): every control in one `[data-testid="control-row"]`, the type scale, buttons, badges, a table, a form, a dialog, and the empty/loading/error states. `tests/ui/controls.spec.ts` asserts equal control heights (36 ± 0.5 px) and equal top y.
3. **`/setup` wizard:**
   - steps: Welcome → Storage → `intelSetupSteps` (CL slot: AI provider, models, privacy, email, notifications) → Phone (QR code for `PUBLIC_URL/capture` + install steps) → Ready
   - it opens on first login while a `required` check is not `ok`
   - state is resumable (current step in `localStorage`, with the truth from the setup-status endpoints)
   - create the placeholder `components/intel/SetupSteps.tsx` with `export const intelSetupSteps = []`
4. **Dashboard "Getting started" card:** merges `/api/system|ai|sources|notifications/setup-status`. Ignore a 404 from an endpoint that isn't there yet. It collapses to "All set" when everything is `ok` and reappears on `warn` or `error`.
5. **Empty states and error copy** on every OA page. `lib/i18n/errors.ts` maps every OA error code to what happened, why, and what to do.
6. **⌘K command palette** (shadcn `Command`): go to pages, find documents (FTS, top 5), and "Ask: <text>" → `/ask?q=<text>`. On the documents list, "Ask about these N documents" → `/ask?filters=<encoded>`. On the detail page, "Ask about this document" → `/ask?document_id=<id>`. CL's Ask page reads these params.
7. **Editing UX on the detail page** (`document-editing` skill):
   - "AI" / "You" provenance badges from `field_sources`, with "Let AI manage this again" → `unlock_fields`
   - inline AI suggestions (from `DocumentAIPanel` data, rendered by CL's component)
   - an undo toast for every save and for bulk edits
   - a History section from the audit log
   - keyboard shortcuts
   - category and tags at upload time on `/upload` and `/capture`

### 5.7 Tests
- Unit tests (Vitest + Testing Library) only where there is logic: the snippet marker renderer, filter ↔ URL param serialisation, and the nav filtering by role.
- E2E (Playwright, against the dev stack, run on `main`): login → upload a fixture PDF → wait until it is stored → find it via search → edit its title → logout.
- Proxy test: SSE ticks arrive incrementally, and a 50 MB upload succeeds without the memory spike of a buffered body.

### Acceptance
- The E2E flow passes. The proxy SSE test passes. Lighthouse accessibility ≥ 90 on `/documents` and `/documents/[id]`.
- A CL page dropped at `app/(app)/review/page.tsx` renders inside the shell with auth, no OA change needed.
- **I6 marked done** in `STATUS.md`.

---

## OA-M6 — PWA capture + consume folder

**Goal:** the phone and the scanner become first-class inputs (CAP-01..03, CAP-05).

### 6.1 PWA
- `app/manifest.ts`: name, short name, `start_url: "/capture"`, `display: "standalone"`, theme colours, and icons (192, 512, maskable).
- **Service worker** `public/sw.js`, hand-written and small. Registered only on `/capture`. Its responsibilities:
  - **Upload queue:** pending uploads are stored in IndexedDB (`docuhive-uploads`: `{id, blobs[], combine, createdAt, attempts}`).
  - **Sending:** on `online`, on page load, and via Background Sync (`sync` event) where supported (Android Chrome; iOS does not support it), retry with exponential backoff. A successful send deletes the entry.
  - No offline caching of app pages beyond the capture page shell (keep it simple).
- **HTTPS:** camera and service workers need a secure context. Document `tailscale serve --https=443 http://localhost:3000` in `docs/setup/remote-access.md`, along with Tailscale MagicDNS and HTTPS certificates.

### 6.2 `/capture` page (client component, mobile-first)
1. A big "Take photo" button: `<input type="file" accept="image/*" capture="environment" multiple hidden>`. A second button, "Choose files", has no `capture` attribute (gallery and PDFs).
2. Thumbnail strip. Each page has rotate 90° (client-side canvas), delete, and drag to reorder (pointer events, no library).
3. **Downscale before upload:** draw onto a canvas with the long edge at 2400 px, export as JPEG quality 0.85, and honour EXIF orientation (`createImageBitmap(file, {imageOrientation: "from-image"})`).
4. "Upload as one document" (default on when there is more than one image) → `POST /api/upload` with `combine=true`, `source=mobile`.
5. While uploading: a progress bar. Offline: "Queued — will upload when online", with a count of queued items.
6. After upload: "Processing…", then poll `GET /api/documents/{id}` every 3 s for up to 2 min, then show the title and category once CL classifies it. Show a link to the document.

### 6.3 Consume folder — `docuhive/ingest/consume.py`
- `@periodic("consume.poll", every=30s, queue="ocr")` scans `CONSUME_DIR` (default `VAULT_DIR/consume`). Polling is required because inotify does not work on NFS/SMB.
- **Owner:** files in `consume/<username>/` belong to that user. Files at the top level belong to `CONSUME_DEFAULT_OWNER` (setting), or are ignored if that is unset.
- **Stability check:** a file is picked up only when its `(size, mtime)` is unchanged across two polls (tracked in an in-memory dict in the job, with fallback state in `settings['consume:seen']`).
- **Ignored names:** dotfiles, `~$*`, `*.part`, `*.tmp`, `*.crdownload`, and `Thumbs.db`.
- **Pickup:**
  1. Move the file to `incoming_dir()`. A cross-filesystem move is copy + fsync + verify + delete-source.
  2. Call `submit` with `source.kind=consume`.
  3. On `IngestRejected`, move the file to `consume/_rejected/` with a `.reason.txt` sidecar.
- `vault.check()` must pass first. If it fails, skip the poll.

### 6.4 Tests
- Capture: unit tests for the downscale and orientation helper (canvas mocked) and the IndexedDB queue logic (`fake-indexeddb`). A manual test checklist for iOS Safari and Android Chrome (in `docs/setup/mobile.md`).
- Consume: the stability check (a file still being written is not picked up), owner subfolders, ignored names, rejected handling, and moves across filesystems (integration).

### Acceptance
- **CAP-01:** on an iPhone over Tailscale, away from home, photograph a 3-page letter → upload → one 3-page searchable PDF in the vault.
- **CAP-01 offline:** with airplane mode on, the capture is queued. When airplane mode is turned off and the app is opened, the upload completes.
- **CAP-03:** a scanner saving to `consume/dev/` gets the document ingested within about 60 s, and a half-written file is never ingested.
