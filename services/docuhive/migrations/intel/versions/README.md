# `services/docuhive/migrations/intel/versions`

**Overview.** AI, email, chat and reminder schema revisions, applied in order after the platform ones.

## What's here

| Path | What it is |
| --- | --- |
| [`0001_intel.py`](0001_intel.py) | Empty baseline; the following revisions add the AI and email tables |
| [`0002_ai_runs.py`](0002_ai_runs.py) | ai_runs: every model attempt |
| [`0003_review.py`](0003_review.py) | review_items: AI suggestions waiting for a person |
| [`0004_mail.py`](0004_mail.py) | Mail accounts, message ledger, attachments, backfills |
| [`0005_chunks.py`](0005_chunks.py) | doc_chunks with pgvector + HNSW |
| [`0006_chat.py`](0006_chat.py) | chat_sessions, chat_messages, analyses |
| [`0007_notify.py`](0007_notify.py) | notification_channels (Fernet config) + notification_log |
| [`0008_reminders.py`](0008_reminders.py) | reminders: one row per (document, fact, remind_on) |

## Extending

Never edit a merged revision.
