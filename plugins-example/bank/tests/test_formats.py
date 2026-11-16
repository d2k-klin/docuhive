"""Statement files are read exactly: amounts, signs, dates, names and balances."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from .. import formats, matching
from .samples import CAMT, ING_CSV, MT940

RULES = Path(__file__).resolve().parents[1] / "rules"
CSV_FORMATS = yaml.safe_load((RULES / "csv-formats.yaml").read_text())
MATCHING = yaml.safe_load((RULES / "matching.yaml").read_text())


def test_camt_with_a_batch_and_a_pending_entry():
    statement = formats.parse(CAMT.encode(), CSV_FORMATS)
    assert statement.format == "camt.053" and statement.iban == "DE02120300000000202051"
    assert statement.balanced() is True
    amounts = [t.amount for t in statement.transactions]
    assert amounts == [Decimal("-84.20"), Decimal("1500.00"), Decimal("500.00"), Decimal("-200.00")]
    power = statement.transactions[0]
    assert power.counterparty == "Stadtwerke Beispiel"
    assert power.counterparty_iban == "DE89370400440532013000"
    assert power.end_to_end_id == "RE-2026-0042" and power.bank_reference == "2026030300001"
    assert "RE-2026-0042" in power.purpose
    assert [t.counterparty for t in statement.transactions[1:3]] == [
        "Kunde Eins GmbH",
        "Kunde Zwei",
    ]
    assert statement.transactions[1].bank_reference is None  # a batch item shares the entry's
    assert (statement.period_start, statement.period_end) == (date(2026, 3, 1), date(2026, 3, 31))


def test_mt940():
    statement = formats.parse(MT940.encode("cp1252"), CSV_FORMATS)
    assert statement.format == "mt940" and statement.balanced() is True
    power, income = statement.transactions
    assert (power.amount, power.booking_date) == (Decimal("-84.20"), date(2026, 3, 3))
    assert power.counterparty == "Stadtwerke Beispiel"
    assert power.counterparty_iban == "DE89370400440532013000"
    assert power.end_to_end_id == "RE-2026-0042"
    assert "Rechnung RE-2026-0042" in power.purpose
    assert income.amount == Decimal("2000.00") and income.counterparty == "Kunde Eins GmbH"


def test_bank_csv_in_windows_encoding():
    statement = formats.parse(ING_CSV, CSV_FORMATS)
    assert statement.format == "csv:ing" and statement.iban == "DE02120300000000202051"
    assert [t.amount for t in statement.transactions] == [Decimal("-84.20"), Decimal("2000.00")]
    assert statement.transactions[0].counterparty == "Stadtwerke Beispiel"
    assert statement.balanced() is None  # a CSV states no opening balance


@pytest.mark.parametrize(
    "name", [k for k, v in CSV_FORMATS.items() if isinstance(v, dict) and "sample" in v]
)
def test_every_shipped_csv_format_reads_its_sample(name):
    statement = formats.parse_csv(CSV_FORMATS[name]["sample"], CSV_FORMATS, name)
    assert statement.transactions and all(t.amount for t in statement.transactions)
    assert formats.parse(CSV_FORMATS[name]["sample"].encode(), CSV_FORMATS).format == f"csv:{name}"


def test_fingerprint_is_stable_across_files():
    a = formats.parse(CAMT.encode(), CSV_FORMATS).transactions[1]
    b = formats.parse(CAMT.encode(), CSV_FORMATS).transactions[1]
    assert a.fingerprint() == b.fingerprint()


def test_not_a_statement():
    for data in (b"Dear tenant,\nthe rent rises.\n", b"<html><body>camt</body></html>"):
        with pytest.raises(formats.NotAStatement):
            formats.parse(data, CSV_FORMATS)


def candidate(
    doc_id, amount, *, name="Stadtwerke Beispiel", iban=None, refs=(), day=date(2026, 3, 1)
):
    return matching.Candidate(doc_id, Decimal(amount), day, name, iban, list(refs))


def payment(amount, *, name="Stadtwerke Beispiel", purpose="", iban=None, day=date(2026, 3, 3)):
    return matching.Payment(1, day, Decimal(amount), name, iban, purpose)


def test_matching_rules():
    decide = matching.decide
    pay = payment("-84.20", purpose="Rechnung RE-2026-0042 Strom")
    # The reference decides even when a second invoice has the same amount.
    assert decide(
        pay, [candidate("a", "84.20", refs=["RE-2026-0042"]), candidate("b", "84.20")], MATCHING
    )[:2] == ("reference", "a")
    # Same amount and payee: confirmed only when exactly one document fits.
    assert decide(payment("-84.20"), [candidate("a", "84.20")], MATCHING)[:2] == ("exact", "a")
    how, doc, suggestions = decide(
        payment("-84.20"), [candidate("a", "84.20"), candidate("b", "84.20")], MATCHING
    )
    assert (how, doc) == ("suggested", None) and {s[0] for s in suggestions} == {"a", "b"}
    # By IBAN when the name differs.
    iban = "DE89370400440532013000"
    assert (
        decide(
            payment("-84.20", name="SWB AG", iban=iban),
            [candidate("a", "84.20", iban=iban)],
            MATCHING,
        )[1]
        == "a"
    )
    # A payment 2 % short is only suggested, never confirmed.
    how, doc, suggestions = decide(payment("-98.00"), [candidate("a", "100.00")], MATCHING)
    assert doc is None and suggestions[0][0] == "a"
    # Outside the time window nothing is offered.
    old = candidate("a", "84.20", day=date(2025, 1, 1))
    assert decide(payment("-84.20"), [old], MATCHING) == ("suggested", None, [])
