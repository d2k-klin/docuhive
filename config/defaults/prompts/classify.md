---
version: 1
---
Classify one document from a personal archive. Choose ONLY from the lists below.

## Categories (id — label: description)
{categories}

## Document types (id — label)
{document_types}

## Allowed tags
{tags}

## Known correspondents (prefer one of these names if it is the same organisation or person)
{correspondents}

## Metadata hints
- Original filename: {filename}
- Source: {source}
- Email subject: {subject}
- Email from: {email_from}
- Hint from email triage: {doc_hint}

## Rules
- title: a short human title in the document's language (max 120 characters), e.g.
  "Stromrechnung November 2025". No file names, no dates in ISO format, no "Scan".
- category and document_type: the single best id from the lists above.
- correspondent: the organisation or person who issued or sent the document, or null.
- tags: only from the allowed tags; an empty list is fine.
- document_date: the issue date printed on the document (YYYY-MM-DD), or null.
- language: ISO 639-1 code of the document text, e.g. "de" or "en".
- confidence: your confidence 0..1 for each of: title, category, document_type,
  correspondent, tags, document_date, language.
- proposed_new_terms: only if nothing in the lists fits well; explain why.
- reasoning: one or two sentences.

## Document text (beginning and end)
{content}
