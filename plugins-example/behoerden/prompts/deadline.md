---
version: 1
---
You read an official letter: from a tax office, a court, a fine office, a pension or health
insurer, a job centre or another authority. Copy what is printed; never guess. Leave a field
empty when the letter does not state it.

- letter_date: the date of the letter (often "Datum" or next to the reference).
- delivered_on: only if the envelope or a delivery certificate gives the date of formal service
  (Zustellung, "Tag der Zustellung"); otherwise empty.
- deadline: a date printed as the last day to answer or object, if the letter gives one.
- period_amount and period_unit: the period to object or answer when no date is printed, for
  example 1 and "months" for "innerhalb eines Monats nach Bekanntgabe", 2 and "weeks" for
  "innerhalb von zwei Wochen nach Zustellung", 14 and "days".
- reference: the file or reference number (Aktenzeichen, Steuernummer, Geschäftszeichen).
- kind: "tax" (tax assessment), "fine" (Bußgeldbescheid), "social" (pension, health or
  unemployment insurance, benefits), "other_authority", "reminder" (payment reminder) or "other".
- sender_address: the authority's postal address for letters, one line per item (name,
  street or PO box, postcode and city).
- amount_due: an amount the letter asks you to pay, with its currency.

Title: {title}
Values already read: {facts}

{content}
