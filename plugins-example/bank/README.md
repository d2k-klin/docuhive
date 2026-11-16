# Bank statements and payments (`bank`)

> **Status: available.**

**Overview.** Reads the statement files your bank lets you download and turns them into payments, matched to the invoices and receipts in your archive. You see what is paid, what is still open, and which payments have no document.

## Who it is for

- **Households:** what did we pay whom, and is there a document for it.
- **Self-employed and small companies:** which customer invoices are paid, which supplier invoices are still open. The [tax plugin](../steuer-de/README.md) uses the payment dates.
- **Landlords:** which rent arrived ([landlord plugin](../vermieter-de/README.md)).

## What it does

- **Import by upload.** Download your statement from your bank (CAMT.053, MT940 or CSV) and upload it like any document, or drop it into your scanner folder. The plugin reads every line. A statement uploaded twice adds nothing twice.
- **No bank login.** The plugin never asks for your online banking password and does not connect to your bank.
- **Matching.** A payment is matched to a document when the invoice number or customer reference is in the payment text, or when amount, name and date fit exactly one document. Everything else is offered as a short list for you to pick from.
- **Three lists:** payments without a document, documents without a payment, and matched.
- **Ask:** "What did I pay Stadtwerke this year?" is answered from your statements, with the statements as sources.

## Set it up

1. Add the plugin and switch it on ([how](../README.md#use-a-plugin)).
2. Upload a statement. The account is created from the IBAN in it; give it a name under **Bank → Accounts**.
3. For a CSV file, choose your bank's format once. If your bank is not listed, see below.

Statements are private documents by default: only local AI models ever read them.

## Make it yours

| File | What it controls |
| --- | --- |
| `rules/csv-formats.yaml` | How each bank's CSV file is read: which column is the date, the amount, the name, the text. **Add your bank here.** |
| `rules/matching.yaml` | How strict matching is: tolerance in days, which reference patterns count as an invoice number |
| `rules/ignore.yaml` | Payments that never need a document (transfers between your own accounts, cash withdrawals) |
| `pages/*.yaml` | The screens |

Adding a bank's CSV format is a few lines:

```yaml
# custom/rules/csv-formats.yaml
my-bank:
  delimiter: ";"
  date: { column: "Buchungstag", format: "%d.%m.%Y" }
  amount: { column: "Betrag", decimal: "," }
  name: { column: "Name Zahlungsbeteiligter" }
  text: { column: "Verwendungszweck" }
  iban: { column: "IBAN Zahlungsbeteiligter" }
```

## Limits

- Only what is in the files you upload: no live balance, no transfers, no direct debits.
- Card statements and payment services work when they offer one of the formats above.

## What's here

| Path | What it is |
| --- | --- |
| `plugin.yaml`, `plugin.py` | The plugin |
| `rules/`, `pages/` | What you can customise |
| `migrations/` | Its tables: accounts, transactions, matches |
| `tests/` | Tests on made-up statements |
