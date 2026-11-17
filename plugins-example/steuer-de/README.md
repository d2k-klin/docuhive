# Tax and bookkeeping for Germany (`steuer-de`)

> **Status: parts 1 and 2 of 3 are available.** Books, receipts and incoming e-invoices, bookings, VAT advance return figures, the EÜR, deadlines, and writing your own invoices with e-invoices work today. Filing through ELSTER is planned and marked *(planned)* below. The rule files have not yet been reviewed by a tax advisor; every figure says so.

**Overview.** Turns the receipts and invoices in your archive into the figures the tax office wants: every month or quarter for VAT, every year for your income, with each figure traceable to its documents. It writes your invoices, files with ELSTER when you tell it to, and hands a clean year to your tax advisor.

> **This plugin does not give tax advice.** It applies the settings you choose and calculates. It cannot tell you what you may deduct or which rules apply to your situation. For that, ask a tax advisor (Steuerberater) or a Lohnsteuerhilfeverein. You are responsible for what you file.

## Who it is for

| You are | What you get | What stays with your advisor or other software |
| --- | --- | --- |
| **Self-employed or a freelancer** using income-surplus accounting (EÜR) | Receipts booked, invoices written, VAT advance returns, the yearly VAT return and the EÜR, filed through ELSTER | Your income tax return as a whole |
| **A small business owner under the small-business rule** (Kleinunternehmer, § 19 UStG) | Invoices with the right wording, receipts booked, the EÜR, a warning before you cross the turnover limits | — |
| **A small company** (GmbH, UG) or anyone who keeps double-entry books | Invoices, incoming receipts captured and pre-booked, VAT advance returns, payment matching, and an export your advisor's software imports | The books themselves, the balance sheet, the E-Bilanz, corporation and trade tax, payroll |
| **A household** | The receipts a private return uses, collected through the year and listed by section of the return, with deadlines | The return itself: you type the totals into ELSTER or give the list to your advisor |

## What it does

### Receipts and incoming invoices

- **E-invoices are read exactly.** An XRechnung, or a ZUGFeRD/Factur-X PDF, carries its figures as data. The plugin reads supplier, number, dates, net, VAT per rate and total directly, with no guessing and nothing to check. Every business in Germany has had to be able to receive these since 2025.
- **Paper and plain PDFs are read by the AI and checked by arithmetic.** Net plus VAT must equal the total for each rate, to the cent, or the receipt goes to your review list instead of your books.
- **It learns how you book.** The first receipt from a supplier asks you once for the account and the VAT treatment. After that it is your rule, applied the same way every time, and shown on the receipt.

### Your invoices

- Customers, quotes, invoices, credit notes and recurring invoices. Lines are typed in on the invoice; a list of saved items is planned.
- Numbers are given when you *issue* an invoice, in sequence with no gaps. A draft has no number.
- Before issuing, the plugin checks that everything the VAT law requires on an invoice is there, including the wording for the small-business rule, reverse charge and sales to other EU countries.
- Every invoice is produced as a PDF and as an e-invoice from the same data: a ZUGFeRD / Factur-X PDF (EN 16931) by default, the XRechnung format for public authorities, or a plain PDF for consumers, chosen per customer. Before an invoice is stored, the plugin reads its own e-invoice back and compares it with the invoice to the cent. Issuing e-invoices becomes mandatory for larger businesses from 2027 and for the rest from 2028.
- Issued invoices are booked as income right away; when they are paid, they count in the year the money arrived.
- An issued invoice cannot be changed. A mistake is corrected with a credit note and a new invoice.
- Send it by mail from DocuHive; the invoice's history shows when and to whom.
- Open invoices, due dates, and reminder letters in three steps, which you send when you decide to. Payments are recorded by hand, or found on your statements by the bank plugin. Interest for late payment is not calculated.

Set up once: under **Tax → Books**, choose the identity the book belongs to (name, address, tax number and bank account come from **Settings → Identities**), then add customers under **Customers**.

### Month, quarter, year

- **VAT advance return (Umsatzsteuer-Voranmeldung)** for each month or quarter, laid out in the order of the official form, with how many bookings feed each field. **Bookings** lists them, filtered by year or name.
- The **yearly VAT return** (the year appears under VAT returns, with the advance returns already paid and what is left) and the **EÜR**, from the same books. Each period page also lists the bookings behind its figures and the form field each one feeds.
- **A period is closed when you say so.** Closing freezes its bookings and locks its receipts and invoices for the eight years they must be kept; later corrections go into a later period, not into history.
- **"What is missing" list** before you close: invoices and receipts without a booking, bookings still to confirm, bookings unpaid for 60 days, and a link to the bank plugin's payments without a document.
- **Small-business rule**: your turnover against both limits on the dashboard, with a warning at 80 % of this year's limit. It explains; your advisor decides.
- **Deadlines** for each return appear in your reminders and your calendar.

### ELSTER and the tax office *(level 1 available; levels 2 and 3 planned)*

You choose how far the plugin goes:

| Level | What happens | What you need |
| --- | --- | --- |
| **1. Figures for the form** | The period page shows each field of the VAT advance return in form order, the amount to pay and the payment reference. You type the figures into Mein ELSTER, upload the transfer confirmation to DocuHive and choose it under **I have filed it**: it is locked with the period and the deadline reminder is cleared. | An ELSTER account |
| **2. Check and file from DocuHive** *(planned)* | The plugin has the tax administration's own software check the return, shows you the official preview, and files it when you confirm. The confirmation is stored and locked. | Your ELSTER certificate file and its PIN, and the ELSTER add-on installed (see [Setting up ELSTER](#setting-up-elster)) |
| **3. Receive** *(planned)* | Assessment notices and messages from your ELSTER mailbox arrive in your archive and are compared with what you filed. | Level 2 |

Under **Tax letters**, as documents you read, sign and send yourself: a request for more time, an objection to a notice (its deadline goes into your reminders), a request to change advance payments. The plugin fills in the formal parts; the reasons are yours, and it never writes them. The same page creates a starting point for your **procedure documentation** (Verfahrensdokumentation), which describes how you capture, book and keep records.

### Your tax advisor

- Every confirmed booking of a year as a CSV file (**Bookings → Download the year as CSV**).
- Per period: one ZIP with the bookings and each booked document as a PDF named by date, sender and number, linked by an index (**VAT returns → the period → For your tax advisor**). The columns are plain; an export in the DATEV format is planned.
- A read-only link to one period's documents for 14 days, when guest links are switched on for your installation.

## Set it up

1. Add the plugin and switch it on ([how](../README.md#use-a-plugin)).
2. Open **Tax** in the sidebar and create a **book**: its kind (self-employed with EÜR, a company that hands over to its advisor, or a household), your VAT status, whether you file VAT monthly or quarterly, when VAT is due (when invoiced or when paid), and the chart of accounts (SKR03 or SKR04).
3. If you are unsure about any of these, they are on your tax office's letters or your advisor knows them. The plugin does not choose them for you.
4. Upload a few receipts. They appear under **Tax inbox** as proposed bookings. Confirm each one, choosing the account the first time; tick **Always book this sender like this** and the next one from that sender is proposed the same way.
5. Invoices and receipts from before you created the book: open the period under **VAT returns** and press **Propose bookings for documents not booked yet**.

### Every month or quarter

1. **Tax inbox**: confirm what is waiting.
2. **VAT returns** → the period: the list **Before you close** shows what is missing. Each form field shows the value to type into Mein ELSTER.
3. Press **Close this period** once you have filed. Its bookings can no longer change; a later correction goes into the current period.
4. **Year (EÜR)** shows the income-surplus statement, counted in the year the money moved.

A household book has no VAT: tag receipts with `tax-work`, `tax-donations`, `tax-medical`, `tax-insurance`, `tax-childcare` or `tax-household-services` and they are listed by section under **Household tax**.

### Setting up ELSTER

Level 1 needs nothing. Levels 2 and 3 need:

- your **ELSTER certificate file** (`.pfx`) from your Mein ELSTER account, uploaded under the plugin's settings. It is stored encrypted. Its PIN is asked for each time you file and is never stored.
- the **ELSTER add-on**, which contains the tax administration's own library for checking and sending returns. It runs only on Intel/AMD machines, not on ARM. The installation guide for the add-on explains how to get it.

Before your first real filing, switch the book to **test mode** and file a return to the tax administration's test office. Nothing sent in test mode counts.

## Make it yours

Everything below can be replaced by a file of the same name in `custom/` ([how](../README.md#2-your-own-files-next-to-the-plugin)).

| File | What it controls |
| --- | --- |
| `rules/accounts-skr03.yaml`, `rules/accounts-skr04.yaml` | The chart of accounts and which EÜR line and VAT field each account feeds |
| `rules/vat-codes.yaml` | VAT treatments (19 %, 7 %, reverse charge, EU, exempt) and their form fields |
| `rules/years/2026.yaml` | Rates, limits, form field numbers and deadlines for the year, each with its legal source |
| `rules/suppliers.yaml` | The usual account for well-known kinds of sender (phone companies, utilities, post), used before the AI is asked |
| `rules/private-tags.yaml` | The tags and sections of the household list |
| `prompts/invoice-fields.md`, `prompts/booking.md` | What the AI is asked |
| `pages/*.yaml` | The screens |

Typical changes: account names the way your advisor uses them; an extra account; a supplier you always book the same way; a household section of your own.

## Limits

- Germany only. No tax calculation for the private return, no balance sheet, no payroll, no cash-register rules, no trade or corporation tax.
- Rates, limits and form fields change every year. Each year's rules are a file the plugin ships; a year without its file cannot be filed, and the plugin says so.
- Filing through ELSTER depends on the tax administration's library and servers. When they are unavailable, level 1 always works.

## What's here

| Path | What it is |
| --- | --- |
| `plugin.yaml`, `plugin.py` | The plugin |
| `rules/`, `templates/`, `prompts/`, `pages/` | What you can customise |
| `einvoice.py` | Reads XRechnung (UBL and CII) and ZUGFeRD / Factur-X invoices exactly |
| `periods.py` | Which period a booking counts in, the form figures, the EÜR, deadlines |
| `migrations/` | Its tables: books, members, bookings, booking rules, periods |
| `tests/` | Tests on made-up invoices, and three made-up businesses whose figures were worked out by hand (`golden-books.yaml`) |
