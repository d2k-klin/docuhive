---
name: guided-experience
description: "Make sure a DocuHive user always knows what to do next: the first-run setup wizard (storage/NAS vault, AI providers and models, privacy, mail accounts, mobile capture, notifications), the dashboard setup checklist, SetupCheck endpoints, empty states with one next action, actionable errors, inline help, progress for long jobs, and plain-language copy. Use when adding a setting, an integration, a page, an empty state, an error message, or anything a user must configure."
---

# Guided experience

A first-time user with no knowledge of OCR, embeddings or OAuth must get from `make dev` to "my mail is being archived automatically" **without reading the repo**. At every moment the UI answers three questions: *Where am I? What is the state? What should I do next?*

## Building blocks

### 1. Setup status contract (each owner reports their own area)
Each owner exposes `GET …/setup-status` → `list[SetupCheck]` (`docuhive.contracts.SetupCheck`):
```python
class SetupCheck(BaseModel):
    id: str                 # "vault", "ai.provider", "ai.models", "mail.accounts", ...
    area: Literal["storage", "ai", "mail", "capture", "notifications", "security", "backup"]
    title: str              # "Connect an email account"
    status: Literal["ok", "todo", "warn", "error", "optional"]
    message: str            # current state in one sentence, plain language
    action_label: str | None  # "Connect Gmail"
    action_href: str | None   # "/sources?connect=gmail"
    help_doc: str | None      # "docs/setup/mail-accounts.md"
    required: bool          # blocks "automation is ready"
```
| Endpoint | Owner | Checks |
|----------|-------|--------|
| `/api/system/setup-status` | OA | vault mounted + initialised, admin password changed from bootstrap, backups configured + last run, Tailscale/HTTPS reachable (`PUBLIC_URL` is https), consume folder present |
| `/api/ai/setup-status` | CL | at least one provider reachable, models present (Ollama `/api/tags`), every task routed, privacy mode chosen, embedding model set, auto-apply state (off until evals pass, with an explanation) |
| `/api/sources/setup-status` | CL | at least one mail account (optional but recommended), no account in `needs_reauth`, initial backfill offered |
| `/api/notifications/setup-status` | CL | a channel configured (optional) |

### 2. Setup wizard — `/setup` (OA page, steps call each owner's API)
It opens automatically on first login while any `required` check is not `ok`. It can be reopened from Settings at any time.

| Step | What the user does | What we explain (one or two sentences, plus a "Learn more" link) |
|------|--------------------|------------------------------------------------------------------|
| 1 Welcome | read the 3-line overview | "DocuHive reads, sorts and stores your documents on your own storage. Nothing leaves your network unless you choose a cloud AI." |
| 2 Storage | see the vault status, follow the NAS guide if it is not mounted | where files live, why the NAS must be mounted, what happens during an outage |
| 3 AI provider | choose **Local (Ollama)** / **Cloud** / **Both**, enter keys (stored in env; the UI shows copy-paste `.env` lines when keys can't be written by the app), and **Test connection** | local = private and free but slower; cloud = faster but text is sent to the provider |
| 4 Models | accept the recommended routing per task, or pick; for Ollama, show the `ollama pull …` commands and re-check | what each task does (triage, classify, extract, embed, chat) in plain words |
| 5 Privacy | choose local-only, or restricted categories (preset: health, identity) | which documents never go to cloud AI |
| 6 Email | connect Gmail / Outlook / IMAP, set the rules preset, choose the backfill range | read-only access, nothing is deleted, how triage decides |
| 7 Phone | QR code for `PUBLIC_URL/capture`, plus the "Add to Home Screen" steps for iOS and Android | how to scan from anywhere (Tailscale) |
| 8 Notifications | optional ntfy/email, with a test message | what you'll be told about (deadlines, problems) |
| 9 Ready | summary of all checks; "Automation is running" | what happens now: mail every 15 min, uploads anytime, review only when unsure |

Each step shows its live `SetupCheck` status, has **Skip for now** (except storage), and is resumable.

### 3. Dashboard checklist
While any check is not `ok`, the dashboard shows a "Getting started" card first: a progress bar plus the open checks, ordered by `required` then area, each with its action button. After everything is `ok` it collapses to a single "All set" line, and it reappears automatically if a check turns `warn` or `error` (e.g. a mail account needs reauth, the vault is offline, a backup is stale).

### 4. Empty states (every list and page)
Use the format: icon + **what this is** + **why it's empty** + **one primary action** (+ an optional secondary link).

| Screen | Empty-state copy | Action |
|--------|------------------|--------|
| Documents | "No documents yet. Upload a file, scan with your phone, or connect email." | Upload · Connect email |
| Review | "Nothing to review. DocuHive asks you only when it's unsure." | (link) How review works |
| Search, no results | "No documents match "…". Try fewer words, or switch to semantic search." | Switch mode · Clear filters |
| Ask, first visit | "Ask anything about your documents." plus 3 example questions from the user's own categories | the example chips |
| Sources | "Connect an email account to archive attachments automatically." | Connect Gmail · Outlook · IMAP |
| Quarantine | "No problem files." | — |

### 5. Errors that say what to do
Every error shown to a user has three parts: **what happened**, **why** (if known), **what to do** (a button or link). The API's `error.code` maps to UI copy in `apps/web/lib/i18n/errors.ts`. Unknown codes fall back to "Something went wrong. Try again, or check System status." with a link.

| Code | User copy | Action |
|------|-----------|--------|
| `vault_unavailable` | "Your storage (NAS) isn't reachable. New files are kept safely and will be stored when it's back." | Storage guide |
| `no_allowed_route` | "This document is private, and no local AI model is set up, so AI skipped it." | Set up local AI |
| `budget_exceeded` | "This month's budget for <provider> is used up." | Use local model · Change budget |
| `needs_reauth` | "Gmail access expired. Reconnect to keep archiving." | Reconnect |
| `encrypted` | "This PDF is password-protected, so DocuHive can't read it yet." | Download original |
| `unsupported_type` | "DocuHive can't read .xyz files yet. Supported: PDF, images, Office, email." | — |

### 6. Inline help
- Every setting or field that needs domain knowledge gets a description line under it (12px muted), plus an optional `?` popover (at most 2 sentences + "Learn more" → `docs/setup/*` or `docs/learn/*`).
- Jargon is explained on first use: "Embedding model: turns text into numbers so DocuHive can find documents by meaning."

### 7. Long-running work is visible
Backfills, OCR, embeddings and re-classification show:
- progress (count / total, or pages scanned)
- what's happening now
- ETA when known
- **what happens next** ("When this finishes, documents appear in Review only if DocuHive is unsure.")

Users can always pause or cancel where it is safe.

## Copy rules

- Plain language, second person, short sentences, sentence case. Name the user's benefit, not the technology.
- Say what will happen **before** it happens (connect mail: "read-only, nothing will be deleted or moved").
- Destructive confirmations name the object and the consequence.
- Never blame the user, and never show raw exceptions, stack traces or HTTP codes.

## Procedure (any new setting, integration or screen)

1. Add or extend a `SetupCheck` in the owning area if the user must configure something.
2. Add a wizard step or a sub-step if it is part of first-run, otherwise a dashboard checklist item.
3. Write the empty state, the error copy (an `errors.ts` entry for any new error code) and the inline help.
4. Write or update the `docs/setup/<topic>.md` guide the UI links to.
5. Walk the flow as a new user on a fresh DB (`make dev RESET=1`). Every screen must have an obvious next step.

## Done when

A fresh install reaches "Automation is running" through the wizard alone. Every page has an empty state with an action. Every error code has user copy with a next step. The setup checks turn `warn` or `error` when things break.
