# Building a DocuHive plugin

> **Status: available**, plugin interface (SDK) version 1. Within version 1, what is described here keeps working.

This guide is for someone who wants to write a plugin or change an existing one. It assumes you can edit a text file; Python is needed only for plugins that have logic. Start with the short example in the [plugins README](README.md#build-your-own-plugin), then come back here for the part you need.

## Contents

1. [The folder](#1-the-folder)
2. [`plugin.yaml`](#2-pluginyaml)
3. [New kinds of documents and values](#3-new-kinds-of-documents-and-values)
4. [Screens](#4-screens)
5. [Logic: `plugin.py`](#5-logic-pluginpy)
6. [Reacting to documents](#6-reacting-to-documents)
7. [Asking the AI](#7-asking-the-ai)
8. [Your own data](#8-your-own-data)
9. [Creating documents, letters and mail](#9-creating-documents-letters-and-mail)
10. [Settings](#10-settings)
11. [Letting people customise your plugin](#11-letting-people-customise-your-plugin)
12. [Testing](#12-testing)
13. [Rules every plugin follows](#13-rules-every-plugin-follows)
14. [When something does not work](#14-when-something-does-not-work)

## 1. The folder

```
my-plugin/
├─ plugin.yaml          required: what the plugin is and what it adds
├─ plugin.py            optional: logic
├─ README.md            for the person using it
├─ pages/               optional: screens, one YAML file each
├─ prompts/             optional: what the AI is asked, one Markdown file each
├─ rules/               optional: tables and rates the logic reads, YAML
├─ templates/           optional: letters and PDF layouts
├─ migrations/          optional: your own database tables, numbered .sql files
├─ custom/              empty; the user's own files go here and survive updates
└─ tests/
```

A plugin may use Python's standard library and what DocuHive already ships (Pydantic, SQLAlchemy, Jinja2, lxml, defusedxml, pikepdf, fpdf2). It may not bring other packages: a plugin must work by copying a folder.

Create the skeleton and check it at any time:

```bash
docuhive plugins new my-plugin
docuhive plugins check my-plugin
```

`check` reads every file and reports problems in plain words with the file and line: an unknown block type on a page, a fact name used on a screen that no document type has, a migration that does not apply.

## 2. `plugin.yaml`

```yaml
id: my-plugin                  # lowercase letters, digits, dashes; never changes
name: My plugin                # shown to people
description: One sentence about what it does for the user.
version: 0.1.0
requires_sdk: ">=1,<2"         # which DocuHive plugin interface it was written for
depends_on: []                 # other plugin ids it needs, e.g. [bank]

capabilities:                  # shown to the administrator before switching on
  - documents:read             # read documents the current user may see
  - documents:write-metadata   # set title, category, tags, values
  - documents:create           # add documents it generates
  - documents:hold             # make a document unchangeable (an issued invoice)
  - ai                         # ask a model, through DocuHive's privacy rules
  - mail:send                  # send mail when a person asks it to
  - network: ["api.example.org"]   # the only hosts it may reach

taxonomy: {}                   # section 3
settings: []                   # section 10
setup_checks: []               # steps for the dashboard's setup card
```

Everything except `id`, `name`, `version` and `requires_sdk` is optional. Ask for the fewest capabilities that work: the list is the first thing an administrator reads.

## 3. New kinds of documents and values

Add categories, document types, values ("facts") and tags under `taxonomy`. They join DocuHive's own; the user's overlay can still rename or disable them.

```yaml
taxonomy:
  categories:
    - { id: vehicle/fuel, label: Fuel }
  document_types:
    - id: fuel_receipt
      label: Fuel receipt
      description: A receipt from a petrol station.
      facts:
        - { name: litres, type: number }
        - { name: amount_total, type: money, required: true }
        - { name: odometer_km, type: number }
  tags: [company-car]
```

Fact types: `money`, `number`, `date`, `string`. A `date` with `remind_days_before: [30, 7]` becomes a reminder without any code. A category with `restricted: true` is only ever read by local AI models.

Once the plugin is on, DocuHive classifies documents into your types, reads your facts from them, shows them on the document page and makes them searchable and answerable in Ask. You did not write code for any of that.

## 4. Screens

A screen is a YAML file in `pages/`. DocuHive draws it with its own components, so it looks and behaves like the rest of the app, on phones too.

```yaml
# pages/fuel.yaml
title: Fuel
nav: { label: Fuel, icon: fuel }      # adds it to the sidebar; leave out for a sub-page
blocks:
  - type: summary
    source: totals                    # a function in plugin.py (section 5)
  - type: table
    source: receipts
    filters:
      - { field: year, type: year }
    columns:
      - { field: date, label: Date, format: date }
      - { field: station, label: Station }
      - { field: litres, label: Litres, format: number }
      - { field: amount, label: Amount, format: money }
    row_link: { document: document_id }
    empty: "No fuel receipts yet. Upload one to see it here."
```

Blocks:

| Type | Shows | Needs |
| --- | --- | --- |
| `summary` | Up to four figures with labels | `source` returning `[{label, value, format}]` |
| `table` | Rows with sorting, filters and paging | `source` or `documents`, `columns` |
| `detail` | Labelled values of one record | `source`, `fields` |
| `form` | Inputs that call an action, with a confirm step. Field types: text, textarea, number, money, date, choice, boolean, and `lines` (a repeating group, such as invoice lines: give it `columns`; the action receives a list of rows) | `fields`, `action` |
| `chart` | Bars or a line over time | `source`, `x`, `y` |
| `documents` | A list of documents with previews | `documents` (a filter) |
| `text` | A paragraph of help | `text` |
| `actions` | Buttons | `actions: [{label, action, confirm}]` |

A table can list documents with no Python at all: give it `documents:` with a filter (category, type, tags, dates, fact values) instead of `source:`.

Two more places a plugin can appear, also as YAML: `pages/_dashboard.yaml` (one card on the dashboard) and `pages/_document.yaml` (a panel on the document page, shown for the document types you name).

Every table and list needs an `empty` text that says what to do next. `docuhive plugins check` refuses a page without one.

**Showing a block only when it applies.** `show_if: is_draft` on any block shows it only when the data source `is_draft` returns something (a non-empty list, a true value) for the page's parameters. The invoice page uses this to offer "Issue" only for drafts and "Record a payment" only for open invoices; it is re-checked after every action.

**Sending.** An action that sends something out of the house is registered with `outgoing=True` and a `preview` function that returns `{"to": [...], "subject": ..., "body": ..., "attachments": [...]}`. When the person presses its button, the page first shows exactly that, with **Send now** and **Cancel**; only **Send now** runs the action. Build the preview and the sending from one helper so they cannot differ. A sending action without a preview, or on a table row, stops the plugin at start.

## 5. Logic: `plugin.py`

One function, `setup`, registers everything. Each registration is a decorator.

```python
from docuhive.sdk import Registry, User, documents


def setup(registry: Registry) -> None:

    @registry.data("receipts")                      # a page's `source: receipts`
    def receipts(user: User, params: dict) -> list[dict]:
        docs = documents.find(user, document_type="fuel_receipt", year=params.get("year"))
        return [
            {
                "document_id": d.id,
                "date": d.document_date,
                "station": d.correspondent,
                "litres": d.fact("litres"),
                "amount": d.fact("amount_total"),
            }
            for d in docs
        ]

    @registry.action("mark-private")                 # a button or a form
    def mark_private(user: User, params: dict) -> str:
        documents.apply_metadata(params["document_id"], tags_add=["private"])
        return "Marked as private."                  # shown to the user
```

`documents.find(user, …)` only ever returns what that user may see. There is no way to ask for "all documents".

What `registry` offers:

| Decorator | For |
| --- | --- |
| `@registry.data(name)` | Rows or figures for a page |
| `@registry.action(name)` | Something a person triggers |
| `@registry.on(event)` | Reacting to a document being stored, changed, trashed or restored |
| `@registry.every(timedelta, name)` | A scheduled job |
| `@registry.tool` | A tool the Ask assistant may call |
| `@registry.setup_check` | A step on the dashboard's setup card |
| `@registry.rebuild` | Rebuilding your tables from documents after a database restore |

## 6. Reacting to documents

```python
@registry.on("document.classified")
def on_classified(event) -> None:
    if event.document_type == "fuel_receipt":
        doc = documents.get(event.document_id)
        ...
```

Events: `document.stored` (read and in the archive, before the AI has looked at it), `document.classified` (the AI has proposed a type and values: `event.document_type`), `document.changed` (a person or the AI changed values; `event.fields` says which, `event.actor` who), `document.trashed`, `document.restored`, `document.quarantined`, `review.accepted` (a person accepted suggestions), and `<plugin id>.<name>` from another plugin your plugin depends on.

A change your plugin makes with `documents.apply_metadata` never overwrites a value a person set, and is shown in the document's history.

Your handler runs as its own background job. If it fails it is retried and shown under **Settings → Jobs**; it never holds up the document or any other plugin. Make it safe to run twice.

## 7. Asking the AI

Put the question in `prompts/`, declare it in `plugin.yaml`, and say what shape the answer has. DocuHive picks the model, applies the privacy rules and the monthly budget, retries, and records the run.

```yaml
# plugin.yaml
capabilities: [documents:read, ai]
ai_tasks:
  - { prompt: station, like: extract }   # uses the model your installation uses for extraction
```

```markdown
<!-- prompts/station.md: {title}, {document_type}, {facts} and {content} come from the document -->
---
version: 1
---
Which petrol station issued this receipt, and is it on a motorway?

{content}
```

```python
from pydantic import BaseModel
from docuhive.sdk import ai


class Station(BaseModel):
    brand: str | None
    is_motorway: bool


def station_of(doc) -> Station:
    return ai.ask("station", Station, document=doc)     # uses prompts/station.md
```

- The answer is always a typed object, never free text you have to parse.
- The task is called `<plugin id>.<prompt>` (here `my-plugin.station`). To give it its own model, add it under `tasks:` in your `routing.yaml`.
- If the document is private, only a local model is used. If there is none, `ai.ask` raises `ai.Unavailable`; show a plain message and carry on.
- Never ask a model to add, compare or convert amounts. Read values with the AI, calculate in Python with `Decimal`.
- A value the AI proposed goes to the user's **Review** list unless your plugin is sure for another reason (it parsed a structured file, or the user set a rule).

To let people ask questions about your plugin's data in **Ask**, register a tool:

```python
@registry.tool
def fuel_cost(user: User, year: int) -> dict:
    """Total fuel cost and litres for a year, with the receipts behind it."""
    ...
    return {"total": total, "currency": "EUR", "documents": [ids]}
```

Return the document ids you used. Ask cites them, and an answer without sources gets a warning.

## 8. Your own data

Most plugins need no tables: documents and their facts are the data. When you do need one (a ledger, a list of customers), add numbered SQL files. DocuHive applies them in order, once, when the plugin is switched on or updated.

```sql
-- migrations/001_trips.sql
CREATE TABLE trips (
    id          bigserial PRIMARY KEY,
    owner_id    bigint NOT NULL,
    document_id text REFERENCES documents(id),
    day         date NOT NULL,
    km          numeric NOT NULL
);
```

Tables live in the plugin's own database schema, so names cannot clash. Read and write them through `registry.db`:

```python
with registry.db.session() as s:
    s.execute(text("INSERT INTO trips (owner_id, day, km) VALUES (:o, :d, :k)"), {...})
```

Two rules:

- **Every row has an owner**, and every query filters by the current user (or by documents that user may see).
- **Say how your data comes back.** The archive can be rebuilt from the vault alone. Either register `@registry.rebuild` to recreate your tables from documents, or set `snapshot: true` in `plugin.yaml` and DocuHive saves a copy of your tables into the vault each night.

## 9. Creating documents, letters and mail

A plugin that produces something the user must keep (an invoice, a letter, a statement) adds it to the archive like any upload, so it is stored, searchable and backed up. It is not classified (your plugin says what it is) and it is private unless you pass `shared=True`. The same bytes twice give the same document.

```python
from docuhive.sdk import documents, render, retention

pdf = render.pdf("statement.html", {"tenant": tenant, "rows": rows})   # templates/statement.html
doc_id = documents.create(
    user,
    pdf,
    filename="statement-2026.pdf",
    title="Service charges 2026",
    category="housing/rent",
    derived_from=[d.id for d in cost_documents],   # linked both ways on the document pages
    document_date=date(2026, 12, 31),
    correspondent=tenant.name,
)
documents.hold(doc_id, "Sent to tenant", until=retention.until("letter", 2026))
```

- **Templates** are Jinja2 in a sandbox: they format the values you pass and nothing else, and a missing value is an error rather than an empty line. `render.text("mail.txt", {...})` fills a text template; `render.pdf("letter.html", {...})` prints an HTML template to A4. Pictures and fonts go in `templates/assets/` and are referenced by file name; nothing is fetched from the internet. Templates are the first thing people customise, so keep wording out of your Python.
- **Letters** extend the core layout, which puts the address in the window of a DL or C5/6 envelope (DIN 5008): `{% extends "_letter.html" %}` and fill `body` (and `sender`, `info`, `footer` if you like). Pass `sender_line`, `recipient` (a list of lines), `place`, `date` and `subject`.
- **E-invoices** inside a PDF: `render.pdf(..., pdfa=True)` makes PDF/A-3b, and `render.attach(pdf, "factur-x.xml", xml)` embeds the XML.
- **Locking** (`documents:hold`): `documents.hold(id, reason, fields=None, until=None)` makes the whole document, or only the listed fields (`"title"`, `"facts.amount_total"`, `"facts"`), unchangeable for everyone until the date or until an administrator lifts it. Use `retention.until("booking_document" | "books" | "letter" | "tax_filing", year)` for the legal keeping periods instead of counting years yourself.
- **Identities**: `profiles.list(user)` and `profiles.get(user, id)` give the name, address, tax numbers and bank account the person entered under Settings → Identities. A setting of type `profile` lets the person pick one.
- **Mail** (`mail:send`): `mail.send(user, profile_id, to, subject, body_text, attachments=[doc_ids])` sends as that identity. It works only inside a page action the person pressed (register it with `outgoing=True` and a `preview`, so the page shows what will be sent first), never from a job or a listener. The sent mail is stored as a document and it and its attachments are locked.
- **People** (`users:find`): `users.find(username)` gives the id of an active person, or `None`; `users.names(ids)` gives user names for ids. Nothing else about a person is shared. Use it to let someone share a record (a book, a list) with another person by name.
- **Guest links**: `guest_links.create(user, label, document_ids, days)` gives a read-only link for someone without an account, such as a tax advisor, for at most 30 days. Also only from a page action; the installation must have guest links switched on.

## 10. Settings

```yaml
settings:
  - { key: company_car, type: boolean, label: I use a company car, default: false }
  - { key: plate, type: string, label: Number plate, show_if: company_car }
  - { key: api_key, type: secret, label: Fuel card API key, help: "From your fuel card's website." }
```

DocuHive draws the form under **Settings → Plugins**. Read values with `registry.settings.get("plate")`. A `secret` is stored encrypted and is never shown again after saving. Types: `string`, `number`, `boolean`, `date`, `choice`, `secret`, `profile` (one of the user's saved identities: name, address, tax number, bank details).

A missing required setting can be a setup step:

```yaml
setup_checks:
  - { id: plate, title: Number plate, when_missing: plate, action: settings }
```

## 11. Letting people customise your plugin

People will change your plugin without wanting to maintain a copy of it. Make that easy:

- Put **wording** in `templates/`, **tables and rates** in `rules/`, **AI questions** in `prompts/`, **screens** in `pages/`. Anything in those folders can be replaced by a file of the same name in `custom/`.
- Load them through the registry, which looks in `custom/` first: `registry.rules("accounts.yaml")`, `registry.template("letter.md")`.
- Give every rules file a comment at the top saying what it controls, and list the files in your README under "Make it yours".
- Prefer a setting to a file, and a file to code.

## 12. Testing

```python
# tests/test_fuel.py
from datetime import date
from pathlib import Path

import pytest
from docuhive.sdk.testing import Archive

pytestmark = pytest.mark.integration
PLUGIN = Path(__file__).resolve().parents[1]


def test_fuel_total():
    with Archive(PLUGIN) as archive:          # your plugin, switched on, in an empty archive
        alice, bob = archive.user("alice"), archive.user("bob")
        archive.add(alice, document_type="fuel_receipt", date=date(2026, 3, 1),
                    facts={"litres": "40", "amount_total": ("72.00", "EUR")})
        fuel_cost = archive.tool("my-plugin", "fuel_cost")
        assert fuel_cost(alice, year=2026)["total"] == "72.00"
        assert fuel_cost(bob, year=2026)["documents"] == []     # bob sees nothing of alice's
```

- `archive.add(...)` creates a stored document; `archive.emit("document.classified", document_id=…, document_type=…)` and `archive.run_jobs()` run your listeners as the worker would.
- The archive is a real, disposable database, so your SQL and your migrations are tested too. Start one once with `docker compose -f deploy/compose.test.yml up -d` and set `DOCUHIVE_TEST_DATABASE_URL=postgresql+psycopg://docuhive_test:docuhive_test@127.0.0.1:55432/docuhive_test`. Its contents are deleted by every test.
- Tests never need the network or an AI key, and never reach a real model: the AI is off in the test archive. To test the AI path, script its answers: `Archive(PLUGIN, ai={"Copy what is printed": {...}})` answers every question whose prompt contains that text with the given output (a list gives one answer per call, so you can test that a wrong first answer is refused).
- `archive.run_jobs(queues=("default", "ocr"))` also stores documents your plugin created, so you can check them in the vault.
- Use only made-up documents. Never put a real invoice, letter or bank statement in a plugin folder.
- Test that another user sees nothing of yours: every data function and tool must return nothing for `archive.user("bob")`.

Run them with `docuhive plugins test my-plugin`.

## 13. Rules every plugin follows

1. Show a user only what that user may see.
2. Ask the AI only through `ai.ask` and Ask tools.
3. Calculate amounts with `Decimal`, never with a model, never with floating point.
4. Send nothing (mail, letters, filings) without a person's click and a preview.
5. Keep anything the user must keep as a document in the archive.
6. Work after a restart, after being switched off and on, and when a job runs twice.
7. Say what went wrong in words a person can act on.
8. Ship no real documents and no secrets.

## 14. When something does not work

| You see | Likely cause | What to do |
| --- | --- | --- |
| The plugin is not listed under Settings → Plugins | The folder is not in your plugins folder, or DocuHive was not restarted | `docuhive plugins list` shows where it looks |
| "Needs a newer DocuHive" | `requires_sdk` is newer than your installation | Update DocuHive, or use an older version of the plugin |
| "Could not start", with an error | `setup` raised | The message is on the Plugins page; `docuhive plugins check` usually finds it first |
| A page is empty | The data function returned nothing for this user | Check the filter by owner; try as the document's owner |
| The AI is never asked | The document is private and no local model is set up | Settings → AI |
| Your change to `rules/` has no effect | A file of the same name exists in `custom/` | `docuhive plugins files my-plugin` |
