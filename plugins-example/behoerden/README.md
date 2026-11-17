# Official letters and ID documents (`behoerden`)

> **Status: available.**

**Overview.** Letters from the tax office, a fine office, the pension or health insurer or another authority often give you a month, sometimes two weeks, to answer or object. Miss it and the decision stands. This plugin finds those letters, works out the last day, reminds you, and writes the objection when you need one. It also keeps an eye on when passports, ID cards and driving licences run out.

## Who it is for

Everyone who gets official post, and small businesses with tax and authority letters.

## What it does

- **Official letters to answer**, soonest first, with who sent them, the kind of letter, the reference and an amount to pay.
- **The deadline**, as printed, or worked out when the letter only says "within one month": the date of the letter plus four days for the post, then the period, moved past weekends and nationwide public holidays. Reminders 14, 7 and 2 days before, in the app, on your phone and in your calendar.
- **An objection letter** (Einspruch for tax and fines, Widerspruch for other authorities) in your name, with the letter's date and reference, your reasons or "reasons to follow", and if you like a request not to collect the amount until it is decided. It is a draft in your archive, linked to the letter; you sign and post it or send it through the authority's portal.
- **ID documents** by holder and expiry, marked **Renew soon** six months before. DocuHive itself reminds you six and two months ahead.
- **On the dashboard:** letters to answer and the next deadline; ID documents to renew.
- **Ask:** "Which official letters do I still have to answer?"

This plugin works out dates from the rules below. It does not give legal advice; when much is at stake, ask a lawyer or tax advisor.

## Set it up

1. Add the plugin and switch it on ([how](../README.md#use-a-plugin)).
2. Add yourself under **Settings → Identities**: objections are written in that name and address.
3. Upload official letters as they arrive (or let the mail connector bring them). They appear under **Official letters**.
4. Check each deadline against the letter once. A date on the envelope of a formal service (Zustellung) counts instead of the letter date; enter it as the deadline on the document if the plugin could not read it.
5. Upload your passports and ID cards and set **whose** each is on the document page.

## Make it yours

| File | What it controls |
| --- | --- |
| `rules/deadlines.yaml` | Days the post takes, kinds of letters and the name of their objection |
| `templates/objection.html` | The objection letter's wording |
| `prompts/deadline.md` | What the AI reads from a letter |
| `pages/*.yaml` | The screens |

Put your version in `custom/`; updates never touch it.

## Limits

- State holidays are not counted, so a computed deadline can be one day early. That is the safe side.
- Fines and court letters are usually served formally: the deadline runs from the date on the envelope, which the letter itself does not show.
- Nothing is sent from DocuHive: authorities need a signature or their own portal.

## What's here

| Path | What it is |
| --- | --- |
| `plugin.yaml` | The official notice type, its values, and whose ID document it is |
| `plugin.py` | Reading a notice, the lists, the objection letter, the Ask tool |
| `deadlines.py` | The date rules (pure, tested) |
| `rules/`, `templates/`, `prompts/`, `pages/` | What you can change |
| `tests/` | Its tests |
