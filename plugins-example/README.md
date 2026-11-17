# DocuHive plugins

> **Status: available** in DocuHive 0.9. The example plugins' own pages say what each does today and what is still planned.

**Overview.** DocuHive keeps your documents. A plugin makes them do a job: prepare your VAT return, match payments to invoices, remind you to cancel a contract. This folder holds ten example plugins you can use as they are, change to fit you, or copy as the start of your own.

## Who plugins are for

| You are | Plugins that fit |
| --- | --- |
| A household | [Official letters and ID documents](behoerden/README.md), [Contracts](vertraege/README.md), [Bank](bank/README.md), [Inventory](inventar/README.md), [Home and craftsmen](handwerk/README.md), [Health claims](gesundheit/README.md), the private part of [Tax (Germany)](steuer-de/README.md) |
| Self-employed | [Tax (Germany)](steuer-de/README.md), [Bank](bank/README.md), [Contracts](vertraege/README.md) |
| A small company | [Tax (Germany)](steuer-de/README.md) for invoices, receipts and VAT, with the hand-over to your tax advisor; [Bank](bank/README.md); [Inventory](inventar/README.md) |
| A private landlord | [Landlord (Germany)](vermieter-de/README.md), [Bank](bank/README.md), [Home and craftsmen](handwerk/README.md) |
| Coming from Paperless-ngx | [Import from Paperless-ngx](paperless-import/README.md) |

## The examples

| Folder | What it does | Works without the others |
| --- | --- | --- |
| [`steuer-de/`](steuer-de/README.md) | Bookkeeping and tax preparation for Germany: receipts in, invoices out, VAT and income figures per month, quarter and year, ELSTER and your tax advisor | Yes; better with `bank` |
| [`bank/`](bank/README.md) | Bank statements become payments, matched to your invoices and receipts | Yes |
| [`vertraege/`](vertraege/README.md) | Every contract with its cost and its notice date, and a cancellation letter ready to send | Yes; better with `bank` |
| [`vermieter-de/`](vermieter-de/README.md) | Rent ledger and the yearly service-charge statement for each tenant | Yes; better with `bank` |
| [`inventar/`](inventar/README.md) | Your receipts become an inventory with warranties and a list for your insurer | Yes |
| [`behoerden/`](behoerden/README.md) | Official letters with a deadline to answer, an objection letter ready, and when ID documents run out | Yes |
| [`handwerk/`](handwerk/README.md) | Craftsman invoices: the labour you can deduct (§ 35a), warranty on the work, and upkeep reminders | Yes; better with `bank` and `steuer-de` |
| [`gesundheit/`](gesundheit/README.md) | Medical bills to submit, the insurer's statement matched to them, your own share for the tax return | Yes; better with `steuer-de` |
| [`paperless-import/`](paperless-import/README.md) | Brings a Paperless-ngx archive into DocuHive with its titles, dates, correspondents and tags | Yes |
| [`schule/`](schule/README.md) | Letters from school that need an answer: the smallest example, to read first | Yes |

They are examples in the full sense: complete enough to use every day, and written to be read and changed.

## Use a plugin

1. **Find it.** In the app, open **Settings → Plugins → Marketplace**. Every plugin that comes with DocuHive is there, with what it does and labels such as *Household*, *Business* or *Germany* to filter by.
2. **Install it.** Press **Install**. You see what the plugin is allowed to do (read documents, create documents, use AI, reach an address); choose **Install and switch on**, or **Install only** to switch it on later under **Installed**. Only an administrator can.
3. **Use it.** It starts within seconds, without a restart. Its pages appear in the sidebar.
4. **Finish its setup.** A plugin that needs something from you (your tax number, your bank's name) adds a step to the **Set up your archive** card on the dashboard, and its settings are under **Installed**.

When a newer version comes with a DocuHive update, the marketplace offers **Update**; your own files in its `custom/` folder are kept. If the new version asks to do more, it waits for your approval.

From the command line, the same works with `docuhive plugins add <folder>`, `update`, `enable` and `disable`. A plugin you write yourself can also be placed in the `plugins/` folder of your private overlay.

To stop using a plugin, switch it off under **Installed**. Its screens and jobs disappear at once; its documents and its data stay, and come back if you switch it on again. A plugin that is off can be removed; installing it again brings its data back.

## Make a plugin yours

There are three ways, from easiest to most powerful. Use the first one that does what you need.

### 1. Settings, in the app

Every plugin has a settings form under **Settings → Plugins**: your details, your choices, which of its features are on. No files.

### 2. Your own files, next to the plugin

Each plugin has a `custom/` folder. A file you put there replaces the plugin's file of the same name, and **an update never touches `custom/`**.

| To change | Put your file in | Example |
| --- | --- | --- |
| A letter or a PDF layout | `custom/templates/` | `custom/templates/cancellation.de.html` with your wording |
| Rules and tables (accounts, rates, allocation keys) | `custom/rules/` | `custom/rules/accounts-skr03.yaml` with your own accounts |
| What the AI is asked | `custom/prompts/` | `custom/prompts/booking.md` |
| A screen's columns and filters | `custom/pages/` | `custom/pages/contracts.yaml` without the columns you never use |

The plugin's own README lists every file you can replace and what each one does. To see what a plugin currently uses, and where each file comes from:

```bash
docuhive plugins files steuer-de
```

### 3. Your own copy

When you want different behaviour, not different wording, make the plugin your own:

```bash
docuhive plugins new my-contracts --from vertraege
```

This copies the plugin under a new name. It is now yours: change its code, and it will not be overwritten by an update of the original. Switch the original off and yours on.

### Updating

```bash
docuhive plugins update bank --from plugins-example/bank
```

replaces the plugin's files with the newer ones and keeps `custom/` and all data. If the new version needs a newer DocuHive, the command says so and changes nothing.

## Build your own plugin

A plugin is a folder with one required file. This one adds a list of school letters that still need an answer.

```
schule/
├─ plugin.yaml      what it is and what it adds
├─ plugin.py        only if it needs logic
└─ pages/letters.yaml
```

**`plugin.yaml`**: a name, a new kind of document with one date on it, and a reminder a week before that date.

```yaml
id: schule
name: School
version: 0.1.0
requires_sdk: ">=1,<2"
capabilities: [documents:read]

taxonomy:
  document_types:
    - id: school_letter
      label: School letter
      facts:
        - { name: reply_by, type: date, remind_days_before: [7, 1] }
```

That is already a working plugin. From now on DocuHive recognises school letters, reads the reply date from them, shows it on the document and reminds you.

**`pages/letters.yaml`**: a screen listing the letters, soonest first.

```yaml
title: School letters
nav: { label: School, icon: graduation-cap }
blocks:
  - type: table
    documents: { document_type: school_letter, facts: { reply_by: { from: today } } }
    sort: reply_by
    columns:
      - { field: title, label: Letter, link: document }
      - { field: facts.reply_by, label: Reply by, format: date }
      - { field: correspondent, label: From }
    empty: "No letters waiting for an answer."
```

No code so far. Add **`plugin.py`** only when the plugin has to *do* something:

```python
from docuhive.sdk import Registry, documents


def setup(registry: Registry) -> None:
    @registry.on("document.classified")  # the AI has recognised what kind of document it is
    def tag_school_letters(event) -> None:
        if event.document_type == "school_letter":
            documents.apply_metadata(event.document_id, tags_add=["school"])
```

Try it:

```bash
docuhive plugins new schule          # creates the folder with a working plugin.yaml
docuhive plugins check schule        # checks the files and says what is wrong, in plain words
make dev                             # your plugin reloads when you save
```

The full guide, with every kind of thing a plugin can add, is [BUILDING.md](BUILDING.md).

## What a plugin may and may not do

- **It sees what you see.** A plugin screen shows a user only the documents that user may see anyway.
- **It cannot go around your privacy settings.** A plugin asks the AI through DocuHive, so documents you marked private (health, identity) still never go to a cloud model.
- **It adds up with arithmetic, not with AI.** Amounts and totals are calculated from the values on your documents. The AI may read a value off a document; it never does the sum.
- **It sends nothing by itself.** Anything that leaves the house (an invoice, a letter, a tax return) goes out only when a signed-in person presses the button, after a preview.
- **It is code you run.** A plugin runs inside DocuHive with access to your documents. Install plugins only from people you trust, and read what a plugin says it may do before switching it on.

## What's here

| Path | What it is |
| --- | --- |
| [BUILDING.md](BUILDING.md) | The guide for plugin authors |
| [`steuer-de/`](steuer-de/README.md) | Tax and bookkeeping for Germany |
| [`bank/`](bank/README.md) | Bank statements and payment matching |
| [`vertraege/`](vertraege/README.md) | Contracts and cancellations |
| [`vermieter-de/`](vermieter-de/README.md) | Rent and service charges for private landlords in Germany |
| [`inventar/`](inventar/README.md) | Inventory, warranties and the insurer's list |

## Extending

A new example needs its own folder with a `plugin.yaml`, a `README.md` written for the person using it, tests that run without a network or an AI key, and only synthetic documents. Keep country-specific plugins named with their country (`steuer-de`), so the same idea for another country can sit next to it.
