---
name: document-editing
description: "Build or change how users view and edit a document's metadata in DocuHive: title, category, document type, correspondent, tags, dates, extracted facts (amounts, due dates), sharing, notes, bulk edit, AI-vs-user provenance badges, manual-field locks and unlocking, undo, re-run AI, vocabulary merge, and the apply_metadata contract. Use when touching the document detail page, bulk edit, tag/category pickers, the review queue's edit controls, or PATCH /api/documents."
---

# Document editing

Users must be able to correct anything the AI decided, quickly, and trust that **their** corrections stick. Every edit goes through `documents.apply_metadata(actor="user:<id>")`, which writes the DB, `meta.json` and the audit log, and locks the field against AI overwrite (`manual_fields`).

## Where editing happens

| Place | What | Owner |
|-------|------|-------|
| Document detail `/documents/[id]` | inline edit of every field, facts editor, notes, share toggle, history | OA |
| Bulk edit (documents list, select → "Edit") | category, type, correspondent, add/remove tags, shared | OA |
| Upload / capture result | optional category and tags at upload time | OA |
| Review queue `/review` | accept, edit-then-accept, reject AI suggestions | CL |
| Vocabulary `/vocabulary` | rename and merge tags/correspondents | OA |

## Controls (all follow the docuhive-ui skill: same height, same look)

| Field | Control | Behaviour |
|-------|---------|-----------|
| Title | text input, inline (click to edit, Enter saves, Esc cancels) | trimmed, max 120 |
| Category | **tree combobox** from `/api/taxonomy` (search matches label and path, showing "Utilities › Electricity") | only taxonomy ids. A proposal of a new one goes to review/term |
| Document type | select from the taxonomy | changing it re-runs **extract** (facts for the new type) |
| Correspondent | combobox with typeahead (`/api/vocabulary/correspondents?q=`), with "Create "…"" as the last item | normalised server-side |
| Tags | tag input: typeahead chips, Enter or comma adds, Backspace removes the last | new tags created on save |
| Document date | native date input | |
| Facts | a typed row per fact from the document type's schema: money = amount input (`inputmode="decimal"`, locale-aware parse) + currency select, date = date input, string/number/iban = text input with validation | invalid values are blocked with an inline error |
| Shared | switch "Visible to household" | owner only |
| Notes | textarea + list, newest first | |

## Provenance & locks (the trust model)

- Next to each field there is a small badge showing who set it:
  - **"AI"** (with confidence on hover, and a click opens "How was this made?")
  - **"You"** (`manual_fields`)
  - nothing (default/filename)
- **"You"-set fields are locked** against AI. The badge menu has "Let AI manage this again" → `PATCH` with `unlock_fields: [field]` (removes the field from `manual_fields`, then enqueues re-classify/extract for that document).
- Pending AI suggestions for a field show inline under it: "AI suggests: Utilities › Gas (0.72)", with Accept and Dismiss. They are the same items as in the review queue.

## Saving, feedback, undo

- **Optimistic UI:** the field updates immediately, a quiet "Saved" tick shows for 1.5 s, and on failure it reverts with the error copy (guided-experience skill).
- **Undo:** every save shows a toast "Category changed to Utilities › Electricity · Undo" for 8 s. Undo sends the previous values (kept client-side, and also in `audit_log`) with `actor=user`.
- **History:** a collapsible "History" section on the detail page (from `audit_log`: who, when, field, from → to; AI entries link to their run).
- **Bulk edit:** a preview line ("Change category of 23 documents"), then one job per 50 documents with a progress toast. Undo is offered for bulk too (it restores each document's previous values from the audit log).

## What editing does **not** do

- It never moves or renames files in the vault (immutable). The library view (folders) updates on its next sync. Say so in the help text of the category field: "Folders on your NAS update within an hour."
- It never edits document content. Split/merge pages is backlog.

## Re-run AI

The "Re-run AI" button on the detail page (CL's `DocumentAIPanel`) → `/api/review/reclassify` for this document. Locked fields stay as they are, and new suggestions appear inline and in review.

## API contract reminders

- `PATCH /api/documents/{id}`: `MetadataPatch` + `shared` + `unlock_fields`. Owner only. Returns the updated `DocumentView` + `ApplyResult`.
- `POST /api/documents/bulk`: `{ids, patch}`, max 500.
- Tags: `tags_add` / `tags_remove` (never send the whole list, to avoid lost updates).
- Facts: send only the changed keys. `null` deletes one.

## Keyboard

- On the detail page: `e` edits the title, `c` category, `t` tags, `d` date, `s` toggles shared, `u` undoes the last change, `Esc` cancels editing.
- In the list: `x` selects a row, `Shift+x` selects a range, `b` opens bulk edit.

## Tests

- **Unit:** the money and date parsers (de/en formats), the tag input add/remove, undo payload construction.
- **E2E:**
  - edit the category → reload → it persists and shows the "You" badge
  - re-run AI → the category is unchanged and a suggestion is shown for an unlocked field
  - "Let AI manage" → the next classify can change it
  - bulk edit of 3 documents + undo restores them
- **API:** a non-owner gets `404` on PATCH. An invalid category id → `422` with a clear message (validated against the taxonomy by the API before calling `apply_metadata`).

## Done when

Every field is editable with the standard controls. User edits stick (lock badge) and can be unlocked. Every change can be undone and is visible in History. Bulk edit works with progress and undo.
