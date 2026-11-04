# Manual checks register

No check has been signed. Only the person who performed it may enter a passing result.
Use an ISO date, concrete environment and runner name; retain private artifacts outside this repo.

| ID | Requirements | Steps | Expected | Date | Environment | Result | Person |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MC-01 | CAP-01, CAP-05 | iPhone Safari installed PWA: capture three pages away from home over Tailscale | One searchable PDF in page order | pending | pending | pending | pending |
| MC-02 | CAP-01, CAP-02 | Android Chrome: capture offline, reconnect | Queue uploads exactly once, correct rotation | pending | pending | pending | pending |
| MC-03 | MAIL-01, MAIL-03 | Gmail production consent, one-month backfill; check again after eight days | No re-consent and no duplicates | pending | pending | pending | pending |
| MC-04 | MAIL-01, MAIL-03 | Outlook personal account one-month backfill twice | No duplicates, complete provenance | pending | pending | pending | pending |
| MC-05 | STO-02, STO-03, STO-05, STO-07, NFR-03 | WD NAS: ingest, power down, queue uploads, recover, inspect library hardlinks | No loss and no write into bare mount | pending | pending | pending | pending |
| MC-06 | QA-05 | Subscribe in iOS/macOS Calendar and change a deadline | Correct updated event | pending | pending | pending | pending |
| MC-07 | AUTO-03 | Send a due-date notification to a real ntfy client | One notification with working document link | pending | pending | pending | pending |
| MC-08 | ING-03, NFR-04, NFR-05, NFR-09 | Owner runs OCR spike on 50 private files, transcribes ten pages on reference host | At least 95% ingest, readable text, below 10 s/page | pending | pending | pending | pending |
| MC-09 | GUIDE-01, GUIDE-02, GUIDE-03, GUIDE-04, GUIDE-05, GUIDE-06 | New person follows setup and quick start from fresh install | Reaches automation ready with clear next steps | pending | pending | pending | pending |
| MC-10 | WEB-03 | VoiceOver: login, upload, search and chat without mouse | Labels, focus, streaming and citations accessible | pending | pending | pending | pending |
| MC-11 | DOC-06 | Confirm the stated v1 scope excludes page splitting and merging | Backlog scope respected; no unfinished controls exposed | pending | pending | pending | pending |

The automated checks and pending manual checks are combined in [traceability](traceability.md).
