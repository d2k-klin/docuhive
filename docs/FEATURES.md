# Features

**Overview.** Every DocuHive feature in one sentence, with its current state. The details are in the [requirements](REQUIREMENTS.md) and the [architecture](ARCHITECTURE.md).

States:

- **Works**: implemented and checked against real services (PostgreSQL, Docker).
- **Built**: code and tests exist, but it is checked only with test doubles, or it waits for the document archive.
- **Planned**: in the requirements, not built yet.

## Capture

| Feature | State | What it does |
| --- | --- | --- |
| Email accounts | Built | Connects several Gmail, Outlook and IMAP accounts and syncs new mail on a schedule. |
| Email backfill | Built | Imports a chosen date range of old mail, resumable and without duplicates. |
| Email filters and triage | Built | Skips newsletters and unwanted senders per account, then lets the AI decide which attachments are real documents. |
| Mail stays untouched | Built | Never deletes or moves your mail; adding an "imported" label is optional. |
| Web upload | Built | Upload one or more files, with category and tags set at upload time; the API works, the browser screen comes with the document screens. |
| Phone capture | Built | An installable web app that takes photos, lets you reorder the pages and uploads them as one document. |
| Scanner folder | Built | Picks up files from a NAS folder by polling, because network mounts don't support change notifications. |
| API upload | Works | Personal API tokens let scripts and iOS Shortcuts upload documents. |

## Reading and storing

| Feature | State | What it does |
| --- | --- | --- |
| OCR | Works | Turns scans and photos into searchable PDFs in your languages (German and English by default), straightening and rotating pages. |
| Format conversion | Works | Converts images (including HEIC), Office files, HTML, emails and plain text to PDF. |
| PDF/A archive copy | Works | Keeps a PDF/A copy for long-term storage next to the unchanged original. |
| Quarantine | Works | Keeps corrupt, encrypted or unsupported files with a reason, so they can be retried instead of being lost. |
| Vault on your storage | Works | Stores each document as a plain folder (original, archive PDF, metadata file) on your NAS or disk, readable without DocuHive. |
| Duplicate detection | Works | Recognises a file you already have and reports it instead of importing it again. |
| Near-duplicate detection | Built | Flags the same document arriving twice in different forms, such as an email PDF and a paper scan, by comparing sender, amounts, dates and meaning. |
| Rebuildable index | Planned | Rebuilds the database from the vault's metadata files alone. |
| Vault health check | Built | A weekly, read-only check that every document's files exist, match their checksums and agree with the database, and that no folder is orphaned. |
| Library view | Built | An optional, read-only folder tree sorted by category, year, date and title. |
| Parallel processing | Works | A job queue lets several workers process documents at once and recovers jobs from a crashed worker. |

## Sorting

| Feature | State | What it does |
| --- | --- | --- |
| AI classification | Built | Sets category, type, sender, tags, title, date and language, choosing from your own vocabulary. |
| Fact extraction | Built | Pulls out amounts, due dates, contract terms and policy numbers, and validates them (dates, currencies, IBAN checksums). |
| Review queue | Built | Asks you about low-confidence results and proposed new tags instead of guessing. |
| Custom fields | Built | Lets you define your own typed fields (such as a licence plate) that the AI fills in like the built-in details, with optional reminders for dates. |
| Provenance and locks | Built | Shows who set each field (AI or you) and keeps AI from overwriting what you set. |
| Bulk edit with undo | Planned | Edits many documents at once, records every change and lets you undo it. |
| Vocabulary management | Planned | Manages senders, tags, types and categories, including merging duplicates. |
| Trash | Built | Deleted documents go to a trash you can restore from; permanent removal is an admin-only command. |

## Finding and asking

| Feature | State | What it does |
| --- | --- | --- |
| Full-text search | Works | Finds words with German and English stemming, accents and typos. |
| Hybrid ranking | Works | Merges word matches and meaning matches into one relevance ranking. |
| Highlighted snippets | Works | Shows the matching passage with your search words highlighted. |
| Similar documents | Built | Finds documents that are close in meaning to the one you are looking at. |
| Ask | Built | Answers questions about your documents with links to the sources and totals calculated in SQL, not guessed. |
| Saved analyses | Built | Keeps useful answers so you can rerun them later. |
| Knowledge bases | Works | Named, shareable scopes of documents (categories, senders, dates, tags) for chat and other agents. |
| Saved views | Built | Pins a saved filter, such as "Unpaid invoices" or "Car", to the sidebar and lists the documents it matches. |
| Filtered export | Built | Exports the documents behind a saved view, knowledge base or filter as one ZIP with their PDFs and a CSV of their details. |
| Document list and filters | Built | Browses all documents with filters, sorting and pagination. |
| Agent access (MCP) | Planned | Lets other AI agents search and ask your knowledge bases, with the same permissions. |

## Reminders and notifications

| Feature | State | What it does |
| --- | --- | --- |
| Reminders | Built | Turns due dates, renewals and notice deadlines into reminders. |
| Notifications | Built | Sends alerts by push or email. |
| Calendar feed | Built | Publishes reminders as a calendar you can subscribe to. |

## Privacy and access

| Feature | State | What it does |
| --- | --- | --- |
| Your choice of AI | Built | Runs each AI task locally (Ollama) or with a cloud provider, with fallbacks and budgets. |
| Privacy routing | Built | Keeps health and identity documents on local models only. |
| AI audit trail | Built | Records the model, prompt version, tokens and cost of every AI call. |
| User accounts | Works | Local accounts with hashed passwords and secure sessions. |
| Household sharing | Works | Each document has an owner and can be shared with the household, enforced inside every database query. |
| Scoped API tokens | Works | Personal tokens limited to reading or asking knowledge bases, with an explicit flag for local-only consumers. |

## Not planned for the first version

Document versions, a workflow engine, fine-grained per-user permissions, public share links, a native mobile app and cloud OCR. See [Requirements § Out of scope](REQUIREMENTS.md#7-out-of-scope-v1).
