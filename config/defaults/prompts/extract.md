---
version: 1
---
Extract facts from one document of type "{document_type}" ({document_type_label}).

## Facts to extract
{facts}

## Rules
- Copy values exactly as printed: amounts with their currency symbol or code, dates as printed.
- Use null for any fact that is not in the document. Never guess or compute a value.
- currency (money facts only): ISO 4217 code such as EUR, USD, GBP, CHF, or null if unknown.
- confidence: 0..1 for each fact.
- evidence: for each fact, a short quote (max 120 characters) from the document showing it.

## Document text
{content}
