# Contracts and cancellations (`vertraege`)

> **Status: available.** Finding regular payments that have no contract (with the bank plugin) is planned.

**Overview.** Finds the contracts in your archive (electricity, phone, insurance, gym, software, leases) and turns them into one list: what each costs, when it renews, and the last day you can give notice. When you want out, the cancellation letter is ready.

## Who it is for

Households and businesses alike. Anyone who has ever paid another year for something because the notice date passed.

## What it does

- **One list of contracts** with provider, what it is, your customer number, the cost per month and per year, the end of the current term, and the last day for notice.
- **Reminders** before each notice date, in the app, on your phone and in your calendar.
- **What you pay in total**, per month, by kind of contract.
- **A cancellation letter** with your details, the contract's details and the right date, as a PDF you sign and post, or send by mail from DocuHive. The letter is stored with the contract, and so is the provider's confirmation when it arrives.
- **Price changes:** a new invoice or letter with a different amount for a known contract shows up as a note on that contract.
- **With the [bank plugin](../bank/README.md):** what you really paid to each provider in the last 12 months. *(planned: regular payments for which the archive has no contract)*
- **Ask:** "Which contracts can I cancel in the next three months?"

## Set it up

1. Add the plugin and switch it on ([how](../README.md#use-a-plugin)).
2. Add yourself or your business under **Settings → Identities**: the letters are written in that name.
3. Open **Contracts**. New contracts appear once they are read; a contract uploaded twice (a scan and an e-mail) is one contract with two documents.
4. Open a contract and check the dates once. Anything you correct is yours from then on; the AI will not change it. Contracts marked **Dates missing** need the end of the term and the notice period.

### Cancelling

1. Open the contract, enter the provider's address if it is missing, and choose **Prepare the letter** (with a special reason or a date if you want). The letter is created as a document you can check.
2. Post it and press **I posted the letter**, or send it by mail from your identity.
3. You are reminded after two weeks if no confirmation has arrived. When the provider's confirmation is uploaded, the contract shows as ended.

The archive's own reminder for the notice date uses the contract's dates, so you get one reminder per contract, before the last day for notice.

## Make it yours

| File | What it controls |
| --- | --- |
| `templates/cancellation.de.html`, `templates/cancellation.en.html` | The cancellation letter, in a window-envelope layout. The language is a plugin setting |
| `templates/cancellation-mail.txt` | The text of the mail the letter is attached to |
| `rules/kinds.yaml` | Kinds of contract, which categories count as each, and the special reasons for cancelling |
| `prompts/contract-terms.md`, `prompts/cancellation-confirmation.md` | What the AI is asked when reading a contract or a confirmation |
| `pages/*.yaml` | The screens |

## Limits

- The plugin reads what the contract says. It does not know whether a clause is valid or whether a shorter notice period applies by law.
- It never sends a cancellation by itself.

## What's here

| Path | What it is |
| --- | --- |
| `plugin.yaml`, `plugin.py` | The plugin |
| `rules/`, `templates/`, `prompts/`, `pages/` | What you can customise |
| `dates.py` | Notice dates, terms and renewals (month ends stay month ends) |
| `migrations/` | Its tables: contracts, their documents, price changes |
| `tests/` | The date table, and the whole journey on made-up contracts |
