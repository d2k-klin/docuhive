# User guide

How to use DocuHive day to day: adding documents, finding them, correcting what the AI set, asking questions and keeping track of deadlines. To set DocuHive up, see the [installation guide](setup/installation.md). What each feature does, and how far along it is, is in [features](FEATURES.md).

## Signing in

Your administrator creates your account; there is no sign-up page. Sign in with your user name and password.

**Settings** shows who you are signed in as. Changing your password there signs you out on every device, phones included, and cancels your API tokens. Sign in again with the new password.

## Who sees what

Every document has an owner: the person who added it.

- **Visible to the household**: the default. Everyone in the household can find, read and download it, and ask about it. Only the owner can edit it, share it or move it to the trash.
- **Only the owner**: nobody else sees it, administrators included. It doesn't show up in their lists, searches, answers or reminders.

Change it on the document page under **Details**. Health and identity documents are only ever read by a local AI model, never a cloud one, whatever the sharing setting.

## Adding documents

| Way in | Where | Good for |
| --- | --- | --- |
| Upload | **Upload** | Files on your computer: PDFs, photos, Office files, emails (`.eml`) and HTML |
| Phone | **Capture**, installed on the home screen | Photographing paper, several pages as one document, also offline; see [capture](setup/mobile.md) |
| Scanner folder | `consume/<your user name>/` on the NAS | A scanner that saves to a network folder; see [scanner folder](setup/mobile.md#scanner-folder) |
| Email | **Sources** | Invoices and statements arriving by mail; see [email accounts](setup/mail-accounts.md) |
| Scripts and Shortcuts | **API tokens** | Uploads from other tools; see [token upload](setup/mobile.md#personal-token-upload) |

All of them do exactly the same thing with a file. On **Upload**, drop files on the page or choose them, and optionally set a category and tags. Your choices are locked against the AI. Each file then shows its progress, from **Waiting to be read…** and **Reading text…** to **Stored**. Scans can take several seconds per page.

Three outcomes need you:

- **A file you already have** is recognised by its content and not stored twice. **Already in your archive** links to the existing document.
- **A file DocuHive can't take at all**, such as an empty file, an unsupported type or one over the size limit, is refused straight away with the reason. Nothing is stored; upload a corrected file.
- **A file that fails while being read**, such as an encrypted or damaged PDF or a scan with no readable text, goes to **Quarantine** with the reason. Nothing is lost. **Retry** helps when the failure was temporary, such as a timeout. For an encrypted or damaged file, upload a corrected copy instead. If a retry fails again, ask your administrator to check the logs.

Your original file is always kept unchanged. DocuHive stores a searchable PDF copy next to it.

## Finding documents

- **Documents** lists everything you can see, newest first. Filter by category, type, tag and date range.
- **Search** finds documents by their words, with German and English word forms and small typos, and by their meaning. Matching passages are highlighted.
- **Saved views** keep a filter you use often, such as "Unpaid invoices" or "Car", in the sidebar. **Export** downloads a view's documents as one ZIP file with their PDFs and a spreadsheet (CSV) of their details.
## A document's page

The page shows the PDF preview, the **Details** and the **History**. **Original** downloads the file as it arrived; **PDF** downloads the searchable copy.

### Who set each detail

Each detail shows who set it:

- **The AI**: the badge shows how sure it was. Click the badge for **How was this made?**: the model, the instructions it got, its answer and any retries.
- **Set manually**: a person set it, and the AI will never change it.

### Correcting details

1. Choose **Edit**.
2. Change the title, date, category, type, sender, language or tags, then choose **Save**.
3. Your changes are locked against the AI. To empty a field, clear it and save.
4. To hand a field back to the AI, choose **Let the AI manage this again**.

**Details found in the document** lists what the AI extracted, such as amounts, due dates, contract terms and policy numbers. Amounts and dates are checked before they are shown.

**History** lists every change, who made it and when. There is no undo button yet: to undo a change, edit the field back.

### Trash

**Move to trash** hides the document from lists, searches and answers. **Trash** lists everything you deleted; choose **Restore** to bring a document back with its files. Documents in the trash keep their files, and there is no way yet to remove one for good.

## Editing many documents at once

On **Documents**, tick the documents, or **Select all on this page**. An edit bar appears: choose a category, a tag to add or a tag to remove, then **Apply to … documents**. Each change is recorded in every document's history and locked against the AI.

## The review queue

When the AI isn't sure, or wants to add a tag or sender you don't have yet, it asks instead of guessing. **Review** lists those suggestions per document. Accept or reject each one, or choose **Accept all** or **Reject all**. Accepted values are locked like your own edits.

Until the AI has proven itself on your own documents, all its suggestions wait here. Your administrator can switch on automatic filing for confident suggestions.

## Tidying names

**Vocabulary** lists your tags and senders. Administrators can **Rename** one everywhere, or **Merge** a duplicate, such as "Stadtwerke" and "Stadtwerke GmbH", into one; documents, saved views and knowledge bases follow. Categories and document types come from the taxonomy file, not this page.

**Custom fields** add details DocuHive doesn't know about, such as a licence plate or a warranty end date. The AI fills them like the built-in ones; a date field can create reminders.

**Duplicates** lists documents that are probably the same thing arriving twice, such as an emailed PDF and a paper scan of it. Open both to compare, or choose **Not a duplicate**.

## Asking questions

**Ask** answers questions about your documents in plain language, such as "How much did we pay for electricity in 2025?" or "When can I cancel the gym contract?".

- Every answer links to the documents it used. Open them to check.
- Totals are calculated from the stored amounts, per currency, not estimated by the AI.
- If nothing matches, it says so instead of making something up.

Limit a question to part of your archive with a **knowledge base**: a named set of documents, such as by category, sender, dates or tags, made on **Knowledge bases**. **Analyses** keeps questions you want to re-run as new documents arrive.

Answers only use documents you are allowed to see.

## Deadlines and reminders

**Reminders** lists deadlines found in your documents: due dates, contract ends, notice periods and renewals. Mark one **Done** or **Dismiss** it.

- **Notifications** sends them to your phone or by email; see [notifications](setup/notifications.md).
- **In your calendar** gives a private address your calendar app can subscribe to, with a token that has only the **Calendar feed only** scope.

## Connecting other tools

**API tokens** creates personal tokens for scripts and other tools. Give each token only what it needs, such as upload only, calendar feed only, or read one knowledge base. Treat a token like a password, and delete it when you stop using it.

## For administrators

- **Storage health** shows whether the vault is mounted and each document's files match their checksums. It also shows when the last backup ran.
- The dashboard's **Set up your archive** card lists anything still missing.
- Accounts and recovery are server commands; see the [operations guide](setup/operations.md).

## Not there yet

- An undo button for edits.
- **Similar documents** and **Re-run AI** on the document page: built, but not yet shown there.
- Removing a document from the trash for good.
- Notes on a document.
- A compact menu for phones.
- Letting other AI agents use your knowledge bases (MCP).
