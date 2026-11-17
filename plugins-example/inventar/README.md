# Inventory, warranties and the insurer's list (`inventar`)

> **Status: available.**

**Overview.** Turns purchase receipts into a list of what you own: where it is, what it cost, and until when it is under warranty. When something breaks, or after a burglary or a fire, the receipt, the warranty and the list for your insurer are one click away.

## Who it is for

- **Households:** warranties you would otherwise forget, and a household-contents list for your insurance.
- **Self-employed and small companies:** a simple list of equipment by room or by person, with what it cost and when it was bought.

## What it does

- **Items from receipts.** When a receipt for something durable arrives (a washing machine, a laptop, a bicycle), the plugin proposes an item: what it is, the price, the purchase date, the shop. You confirm it and say where it is.
- **Everything about one item in one place:** receipt, warranty card, manual, later repair bills.
- **Warranty end dates** as reminders, early enough to act.
- **Lists:** by room, by category, by person; the total value.
- **For your insurer:** a household-contents list as a PDF, and, for a claim, one item with all its documents as a bundle.
- **Listed twice?** On an item, **Merge with another item** keeps it, fills its empty fields from the other entry and takes over its documents.
- **Serial numbers:** photograph the type plate; the number is read and added to the item.
- **For businesses:** each item flagged as a low-value item or a larger asset by your threshold, shown on the item and in the CSV export. With the [tax plugin](../steuer-de/README.md), the year's business items are listed on its **Year (EÜR)** page for your advisor.
- **Ask:** "Is the dishwasher still under warranty?"

## Set it up

1. Add the plugin and switch it on ([how](../README.md#use-a-plugin)).
2. New receipts and invoices for durable goods (from 50 € by default) appear under **Inventory inbox**. Press **Add**, or use the form to give the item a better name and a place ("Kitchen", "Office 2"); places are created as you type them.
3. **Not an item** removes a proposal for good: the same thing from the same shop is not proposed again.
4. A warranty card or manual that names an item's model or serial number is suggested on that item; confirm it with **Belongs to this item**.

Warranty dates come from the document when it states a warranty; otherwise the usual length for the category is **assumed** and labelled so. It is a reminder, not a statement of your rights. You are reminded 30 days before a warranty ends.

## Make it yours

| File | What it controls |
| --- | --- |
| `rules/categories.yaml` | Item categories and the usual warranty length for each |
| `rules/thresholds.yaml` | From what price a receipt becomes a proposal; the business thresholds |
| `templates/contents-list.html` | The list for the insurer |
| `templates/claim-bundle.html` | The cover sheet of a claim bundle |
| `prompts/item.md`, `prompts/type-plate.md` | What the AI is asked about a receipt and a type plate photo |
| `pages/*.yaml` | The screens |

## Limits

- No depreciation and no asset accounting.
- The value shown is what you paid, not what the item is worth today.

## What's here

| Path | What it is |
| --- | --- |
| `plugin.yaml`, `plugin.py` | The plugin |
| `rules/`, `templates/`, `prompts/`, `pages/` | What you can customise |
| `migrations/` | Its tables: items, places, their documents, and what is not an item |
| `tests/` | The whole journey on made-up receipts |
