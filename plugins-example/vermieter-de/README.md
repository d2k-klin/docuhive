# Rent and service charges for landlords in Germany (`vermieter-de`)

> **Status: available.** The arrears letter and handing the figures to the tax plugin are planned.

**Overview.** For a private landlord with one or a few flats: who has paid, and the yearly service-charge statement (Nebenkostenabrechnung) for each tenant, built from the bills that are already in your archive.

> **This plugin does not give legal advice.** It divides the costs you enter by the keys you choose. Whether a cost may be passed on to a tenant follows from your tenancy agreement and the law; when in doubt, ask a landlords' association or a lawyer.

## Who it is for

Private landlords in Germany. Not for property managers with many buildings or owners' associations.

## What it does

- **Properties, flats and tenancies:** size, number of people, rent, monthly advance payment for service charges, start and end.
- **Rent ledger:** what was due and what arrived each month. With the [bank plugin](../bank/README.md) the payments fill in by themselves; without it you tick them off.
- **Arrears:** months still open, on the dashboard. *(planned: a reminder letter)*
- **Service-charge statement** per tenancy and year:
  - the year's cost bills from your archive (water, heating, waste, insurance, property tax, cleaning, caretaker), each assigned to a cost type;
  - divided by the key you chose for that cost type (living space, people, units, meter reading);
  - reduced for a tenant who lived there only part of the year;
  - minus the advance payments received.
  The result is a PDF per tenant with every cost, the key, the tenant's share and the balance. It is stored and locked, together with the bills it rests on.
- **The deadline** for delivering the statement appears in your reminders.
- **For your tax return:** rent received and costs per property for the year, passed on and borne, as a table and a CSV file. *(planned: added to the [tax plugin](../steuer-de/README.md)'s household list)*

## Set it up

1. Add the plugin and switch it on ([how](../README.md#use-a-plugin)).
2. Add yourself under **Settings → Identities**: the statements are written in that name, with your bank account for back payments.
3. Under **Landlord**, add the property, its flats (with their living space) and the tenancies (rent, monthly advance, number of persons). When a tenant moves out or the number of persons changes, enter it with its date.
4. Each cost type has a default key (living space, persons, per flat, the metering company's amount, meter readings, or one flat only). Change it for a property where your tenancy agreements say otherwise.
5. Give the property's bills the category **Housing → Property**. They appear under **Property costs** with a proposed cost type; confirm each. A bill that covers two years is split by days.
6. For heating, enter each tenancy's amount from the metering company's statement.
7. Under **Statements**, choose the tenancy and the year. The draft shows every cost, its key with both numbers, the tenant's share, the advances and the balance, and what is still missing. **Issue** makes the PDF and locks it together with the bills it rests on; send it by mail or post it.

You are reminded before the deadline for the statements (twelve months after the end of the accounting year). Every share is rounded down to the cent: tenants never pay more than a bill together, and vacancies stay with you.

## Make it yours

| File | What it controls |
| --- | --- |
| `rules/cost-types.yaml` | The cost types, their default key, whether they are usually passed on, and the words that point a bill to them |
| `templates/statement.html` | The statement's layout and wording |
| `rules/deadlines.yaml` | When the statement is due, and the reminders |
| `prompts/cost-type.md` | What the AI is asked when a bill matches no cost type by its words |
| `pages/*.yaml` | The screens |

## Limits

- Heating costs by consumption are taken from the heat-cost statement your metering company sends; the plugin does not compute them from meter readings.
- No deposit accounting, no owners' association statements.

## What's here

| Path | What it is |
| --- | --- |
| `plugin.yaml`, `plugin.py` | The plugin |
| `rules/`, `templates/`, `pages/` | What you can customise |
| `statement.py` | The arithmetic: keys, time shares, person-days, splitting bills across years |
| `migrations/` | Its tables: properties, flats, tenancies, persons, keys, bills, consumption, rent ledger, statements |
| `tests/` | A made-up building worked out by hand (`golden-property.yaml`), and the whole journey |
