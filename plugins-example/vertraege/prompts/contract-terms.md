---
version: 1
---
You read a contract or a contract confirmation. Copy what is printed; never guess. Leave a field
empty when the document does not state it.

- provider: the company the contract is with.
- provider_address: the provider's postal address for letters, one line per item (name, street, postcode and city).
- product: the tariff or product name.
- customer_number, contract_number: as printed.
- start_date: when the contract starts.
- term_end: the end of the current term, if a date is printed.
- minimum_term_months: the minimum term in months, if stated.
- renewal_months: by how many months it renews when not cancelled (12 for "verlängert sich um ein Jahr").
- notice_amount and notice_unit: the notice period, for example 3 and "months", 14 and "days", 6 and "weeks".
- notice_to: "term_end" (to the end of the term), "month_end", "quarter_end" or "any_day".
- price and price_period: the regular price and whether it is per month, quarter, year or once.

Title: {title}
Values already read: {facts}

{content}
