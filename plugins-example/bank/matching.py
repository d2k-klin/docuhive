"""Which document a payment belongs to: exact rules first, a short list for a person second.

No AI here: a wrong match marks the wrong invoice as paid, so only rules that cannot be
mistaken confirm a match on their own.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher

from docuhive.sdk import DocumentView


@dataclass
class Candidate:
    document_id: str
    amount: Decimal
    date: date | None
    name: str
    iban: str | None
    references: list[str]


@dataclass
class Payment:
    id: int
    booking_date: date
    amount: Decimal
    counterparty: str | None
    counterparty_iban: str | None
    purpose: str


def normalise(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def similar(a: str | None, b: str | None) -> float:
    a, b = normalise(a), normalise(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def candidate(doc: DocumentView, reference_facts: list[str]) -> Candidate | None:
    total = doc.facts.get("amount_total")
    if total is None or doc.facts.get("paid_on") is not None:
        return None
    try:
        amount = Decimal(total.value)
    except ArithmeticError:
        return None
    iban = doc.facts.get("iban")
    return Candidate(
        document_id=doc.id,
        amount=amount,
        date=doc.document_date,
        name=doc.correspondent or "",
        iban=iban.value.replace(" ", "").upper() if iban else None,
        references=[doc.facts[f].value for f in reference_facts if f in doc.facts],
    )


def window(payment: Payment, rules: dict) -> tuple[date, date]:
    return (
        payment.booking_date - timedelta(days=int(rules["window_days_after"])),
        payment.booking_date + timedelta(days=int(rules["window_days_before"])),
    )


def _in_window(c: Candidate, payment: Payment, rules: dict) -> bool:
    if c.date is None:
        return True
    start, end = window(payment, rules)
    return start <= c.date <= end


def decide(
    payment: Payment, candidates: list[Candidate], rules: dict
) -> tuple[str, str | None, list[tuple[str, float]]]:
    """(how, document id it is confirmed for or None, ranked suggestions)."""
    amount = abs(payment.amount)
    pool = [c for c in candidates if _in_window(c, payment, rules)]
    purpose = normalise(payment.purpose)
    # 1. The payment text quotes the document's reference, and the amount agrees.
    by_reference = [
        c
        for c in pool
        if c.amount == amount
        and any(len(normalise(r)) >= 4 and normalise(r) in purpose for r in c.references)
    ]
    if len(by_reference) == 1:
        return "reference", by_reference[0].document_id, []
    # 2. Same amount, and the same payee by IBAN or by name, and only one such document.
    threshold = float(rules["name_similarity"])
    iban = (payment.counterparty_iban or "").replace(" ", "").upper()
    exact = [
        c
        for c in pool
        if c.amount == amount
        and ((iban and c.iban == iban) or similar(payment.counterparty, c.name) >= threshold)
    ]
    if len(exact) == 1:
        return "exact", exact[0].document_id, []
    # 3. A short list for a person: amount (also after a discount), name, date, reference bits.
    discounts = [Decimal(1) - Decimal(str(p)) / 100 for p in rules.get("discount_percent", [])]
    scored = []
    for c in pool:
        score = 0.0
        if c.amount == amount:
            score += 0.5
        elif any((c.amount * d).quantize(Decimal("0.01")) == amount for d in discounts):
            score += 0.35
        elif c.amount and abs(c.amount - amount) / c.amount < Decimal("0.05"):
            score += 0.1
        score += 0.3 * similar(payment.counterparty, c.name)
        if any(normalise(r) and normalise(r) in purpose for r in c.references):
            score += 0.2
        if c.date:
            score += 0.05 * max(0.0, 1 - abs((payment.booking_date - c.date).days) / 60)
        if score >= 0.4:
            scored.append((c.document_id, round(score, 3)))
    scored.sort(key=lambda s: -s[1])
    return "suggested", None, scored[:5]
