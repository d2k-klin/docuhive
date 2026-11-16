"""How long records must be kept, as data. Plugins ask here instead of hard-coding years.

Periods run from the end of the calendar year in which the record was made (AO § 147 (4)).
ponytail: Germany only, one table; an overlay override comes when another country needs one.
"""

from datetime import date

PERIODS: dict[str, tuple[int, str]] = {
    # kind: (years, source)
    "booking_document": (8, "AO § 147 (1) Nr. 4, (3); HGB § 257 (4) — invoices and receipts"),
    "books": (10, "AO § 147 (1) Nr. 1, (3) — books, annual statements, inventories"),
    "letter": (6, "AO § 147 (1) Nr. 2, 3, (3) — business letters received and sent"),
    "tax_filing": (10, "AO § 147 (1) Nr. 1 — returns and their confirmations, kept with the books"),
}


def until(kind: str, year: int) -> date:
    """The last day a record made in `year` must be kept."""
    years, _ = PERIODS[kind]
    return date(year + years, 12, 31)
