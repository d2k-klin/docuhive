---
version: 1
---
Decide whether this email contains a document worth archiving in a personal document archive
(invoices, receipts, contracts, statements, payslips, insurance or tax letters, tickets,
official letters). Newsletters, adverts, chats and notifications without a document are not.

You only see the envelope and a text snippet, never the attachment content.

From: {email_from}
Subject: {subject}
Received: {received}
Labels: {labels}
Attachments (name, type, size):
{attachments}

Text snippet:
{snippet}

Answer:
- archive: true if at least one attachment (or the email body itself) is such a document.
- attachments: the file names to import (a subset of the list above; leave out logos etc.).
- archive_body: true only if the email body itself is the document (e.g. an HTML receipt).
- doc_hint: the most likely document type id ({document_types}), or null.
- reason: one short sentence.
- confidence: 0..1.
