# Home and craftsmen (`handwerk`)

> **Status: available.**

**Overview.** Every invoice for work in your home is worth twice: part of the labour comes off your income tax, and the work is under warranty for years. This plugin reads both from your craftsman invoices and keeps the regular upkeep of your home (heating service, chimney sweep, smoke detectors) on a schedule with reminders.

## Who it is for

Home owners and tenants in Germany. Landlords use it for their own home; the [landlord plugin](../vermieter-de/README.md) covers rented flats.

## What it does

- **Craftsman invoices** by year, with labour and material read from the invoice, the kind of work and who did it.
- **Tax reduction (§ 35a EStG), as an estimate:** 20 % of the labour (with the VAT on it), up to 1,200 € a year for craftsman services and 4,000 € for household services such as cleaning or gardening. Material and invoices paid in cash do not count. With the [bank plugin](../bank/README.md), the year the money left your account counts and only transfers are counted.
- **With the [tax plugin](../steuer-de/README.md):** the reduction appears on its **Household tax** page.
- **Warranty on the work:** five years for building work (roof, windows, heating installed), two years for other work, with a reminder 60 days before it ends.
- **Upkeep:** recurring tasks with the next date and reminders two weeks before and on the day. Add the usual ones with a click; an invoice for one of them (the chimney sweep's) marks it done.
- **On the document page:** the labour, the share that counts and the warranty end of each invoice.
- **Ask:** "How much craftsman labour can I claim for 2026?", "Is the new roof still under warranty?"

It calculates from the rules below; it does not give tax advice.

## Set it up

1. Add the plugin and switch it on ([how](../README.md#use-a-plugin)).
2. Upload craftsman invoices. They appear under **Craftsmen** with labour and material; correct a figure on the document page and it stays yours.
3. Open **Upkeep** and add the tasks that apply to your home.

## Make it yours

| File | What it controls |
| --- | --- |
| `rules/35a.yaml` | The share and caps of the tax reduction, per year |
| `rules/warranty.yaml` | Warranty years per kind of work |
| `rules/maintenance.yaml` | The usual upkeep tasks and their intervals |
| `prompts/labour.md` | What the AI reads from an invoice |
| `pages/*.yaml` | The screens |

Put your version in `custom/`; updates never touch it.

## Limits

- Without the bank plugin the invoice date stands in for the day you paid, and whether you paid by transfer is not checked.
- Work on a new building and subsidised work (KfW, BAFA) do not count for § 35a; the plugin does not know about subsidies.

## What's here

| Path | What it is |
| --- | --- |
| `plugin.yaml` | The craftsman invoice type and its values |
| `plugin.py` | Reading invoices, the reduction, upkeep, the Ask tool |
| `migrations/` | The upkeep table |
| `rules/`, `prompts/`, `pages/` | What you can change |
| `tests/` | Its tests |
