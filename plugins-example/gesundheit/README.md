# Health claims (`gesundheit`)

> **Status: available.**

**Overview.** With private or supplementary health insurance, or Beihilfe, every doctor's bill is money you get back only if you send it in. This plugin lists your medical bills, reminds you to submit them, notices when nothing came back, reads the insurer's statement and matches it to your bills. What you paid yourself goes to your tax return.

## Who it is for

Households with private health insurance, supplementary insurance (dental, hospital, glasses) or Beihilfe. With statutory insurance only, it still collects pharmacy receipts and co-payments for the tax return.

## What it does

- **Bills to submit:** every medical bill (doctor, dentist, hospital, therapist, pharmacy, optician) becomes a claim. Mark several as **Submitted** at once.
- **Reminders** when a bill has not been submitted, or nothing came back, after 30 days (change the number in the plugin's settings).
- **The insurer's statement** is read line by line and matched to your bills by bill number, else by amount and date. A line that fits two bills or none waits on the page for you to match.
- **Keep as my own cost:** small bills you pay yourself, for example to keep a premium refund for a year without claims.
- **Per year:** what you were billed, what came back, and your own share. With the [tax plugin](../steuer-de/README.md), the own share appears on its **Household tax** page.
- **Private by design:** health documents are only read by a local AI model, never a cloud one.
- **Ask:** "Which doctor's bills are still waiting for money?"

## Set it up

1. Add the plugin and switch it on ([how](../README.md#use-a-plugin)).
2. Upload medical bills as they come. They appear under **Health claims** as **To submit**.
3. After sending bills to your insurer, select them and press **Submitted**.
4. Upload the insurer's statement when it arrives; the bills it covers turn **Paid back**.

## Make it yours

| What | Where |
| --- | --- |
| Days before a reminder | **Settings → Plugins → Health claims** |
| What the AI reads from a statement | `prompts/reimbursement.md` |
| The screens | `pages/*.yaml` |

Put your version of a file in `custom/`; updates never touch it.

## Limits

- The own share counts bills in the year of the treatment. For the tax return the year you paid counts; with bills paid the same year, that is the same.
- Whether health costs reduce your tax depends on your income (the reasonable burden, zumutbare Belastung); the tax office works that out.

## What's here

| Path | What it is |
| --- | --- |
| `plugin.yaml` | The medical bill and reimbursement notice types, the reminder setting |
| `plugin.py` | Claims, reading statements, matching, the own share, the Ask tool |
| `migrations/` | Claims and unmatched statement lines |
| `prompts/`, `pages/` | What you can change |
| `tests/` | Its tests |
