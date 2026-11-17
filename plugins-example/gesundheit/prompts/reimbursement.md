---
version: 1
---
You read a statement from a health insurer, a supplementary insurance or a Beihilfe office that
says which bills it reimburses. Copy what is printed, one line per bill; never guess and never
add up amounts yourself. Leave a field empty when the statement does not show it.

- lines: one entry per bill, with
  - bill_number: the bill or invoice number, as printed
  - treatment_date: the date of the treatment or of the bill
  - billed: the amount of the bill
  - reimbursed: the amount paid back for it (0 if refused)
- notice_date: the date of the statement.

Title: {title}
Values already read: {facts}

{content}
