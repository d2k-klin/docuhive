# ruff: noqa: E501  (template text reads better unwrapped)
"""Generate the synthetic eval set: 40 German/English documents with labels. Seeded, no real data.

    uv run python evals/synthetic/generate.py        # rewrites docs/, labels.yaml, search.yaml, qa.yaml
All names, addresses and numbers are invented. IBANs are valid-checksum test values.
"""

import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import yaml

OUT = Path(__file__).parent
rng = random.Random(20261103)

UTILITIES = [  # (category, correspondent, de word, en word)
    ("utilities/electricity", "Stadtwerke Musterstadt", "Stromrechnung", "Electricity bill"),
    ("utilities/gas-heating", "Gaswerk Nordstadt", "Gasrechnung", "Gas bill"),
    (
        "utilities/internet-phone",
        "NetzFunk Telekom GmbH",
        "Rechnung Internet & Telefon",
        "Broadband invoice",
    ),
    ("utilities/water", "Wasserverband Talheim", "Wasserrechnung", "Water bill"),
]
IBANS = ["DE89370400440532013000", "DE02120300000000202051", "DE12500105170648489890"]
MONTHS_DE = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]


def de_money(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def de_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def noise(text: str) -> str:
    """OCR-like noise: a few character confusions, page footer, occasional page break."""
    chars = list(text)
    for _ in range(len(chars) // 400):
        i = rng.randrange(len(chars))
        chars[i] = {"l": "1", "O": "0", "e": "c", "i": "l"}.get(chars[i], chars[i])
    text = "".join(chars)
    if rng.random() < 0.4:
        text = text.replace("\n\n", "\n\nSeite 1 von 2\n\f\n", 1)
    return (
        text + "\n\n— Diese Rechnung wurde maschinell erstellt. —" if rng.random() < 0.3 else text
    )


docs: list[dict] = []


def add(doc_id: str, text: str, expect: dict, restricted: bool = False) -> None:
    (OUT / "docs" / f"{doc_id}.txt").write_text(noise(text), encoding="utf-8")
    docs.append(
        {"id": doc_id, "file": f"docs/{doc_id}.txt", "expect": expect, "restricted": restricted}
    )


def invoices() -> None:
    n = 0
    for cat, corr, de, en in UTILITIES:
        for month in (1, 2, 4, 7, 9, 11) if cat == "utilities/electricity" else (3, 6, 9):
            n += 1
            lang = "de" if n % 3 else "en"
            issued = date(2025, month, rng.randint(1, 5))
            due = issued + timedelta(days=14)
            amount = Decimal(rng.randint(3000, 15000)) / 100
            iban = IBANS[n % len(IBANS)]
            if lang == "de":
                text = (
                    f"{corr}\nKundenservice · Musterstraße 1 · 12345 Musterstadt\n\n"
                    f"{de} {MONTHS_DE[month - 1]} {issued.year}\nRechnungsnummer: R-{issued:%Y%m}-{n:03}\n"
                    f"Rechnungsdatum: {de_date(issued)}\n\nAbrechnungszeitraum {MONTHS_DE[month - 1]}\n"
                    f"Nettobetrag {de_money(amount / Decimal('1.19'))} €\nMwSt. 19 %\n"
                    f"Gesamtbetrag: {de_money(amount)} €\n\nBitte überweisen Sie bis zum {de_date(due)} "
                    f"auf IBAN {iban[:4]} {iban[4:8]} {iban[8:12]} {iban[12:16]} {iban[16:20]} {iban[20:]}."
                )
            else:
                text = (
                    f"{corr}\n\n{en} — {issued:%B %Y}\nInvoice no. R-{issued:%Y%m}-{n:03}\n"
                    f"Invoice date: {issued:%B} {issued.day}, {issued.year}\n\n"
                    f"Total amount: EUR {amount:.2f}\nPlease pay by {due:%B} {due.day}, {due.year}.\n"
                    f"IBAN {iban}"
                )
            add(
                f"inv-{n:03}",
                text,
                {
                    "category": cat,
                    "document_type": "invoice",
                    "correspondent": corr,
                    "document_date": issued.isoformat(),
                    "language": lang,
                    "tags": [],
                    "facts": {
                        "amount_total": {"value": f"{amount:.2f}", "currency": "EUR"},
                        "due_date": due.isoformat(),
                        "iban": iban,
                    },
                },
            )


def receipts() -> None:
    for n, (shop, item, cur) in enumerate(
        [
            ("Bäckerei Sonnenschein", "Brötchen, Kaffee", "EUR"),
            ("Elektro Markt Berlin", "USB-C Kabel, Ladegerät", "EUR"),
            ("Corner Books London", "Paperback novel", "GBP"),
            ("Café Lago Zürich", "Cappuccino, Gipfeli", "CHF"),
        ],
        start=1,
    ):
        d = date(2025, rng.randint(1, 12), rng.randint(1, 28))
        amount = Decimal(rng.randint(250, 9000)) / 100
        lang = "en" if cur == "GBP" else "de"
        sym = {"EUR": "€", "GBP": "£", "CHF": "CHF"}[cur]
        text = (
            f"{shop}\n{'Kassenbon' if lang == 'de' else 'Receipt'}\n{de_date(d)} 10:{n}2\n\n"
            f"{item}\n{'SUMME' if lang == 'de' else 'TOTAL'} {sym} {amount:.2f}\n"
            f"{'Vielen Dank für Ihren Einkauf!' if lang == 'de' else 'Thank you!'}"
        )
        add(
            f"rcp-{n:03}",
            text,
            {
                "category": "purchases/receipts",
                "document_type": "receipt",
                "correspondent": shop,
                "document_date": d.isoformat(),
                "language": lang,
                "tags": [],
                "facts": {
                    "amount_total": {"value": f"{amount:.2f}", "currency": cur},
                    "purchase_date": d.isoformat(),
                },
            },
        )


def other_types() -> None:
    for n, month in enumerate((3, 6, 9, 12), start=1):
        d = date(2025, month, 28)
        gross = Decimal(rng.randint(380000, 520000)) / 100
        net = (gross * Decimal("0.62")).quantize(Decimal("0.01"))
        add(
            f"pay-{n:03}",
            (
                f"Beispiel Software GmbH\nEntgeltabrechnung {MONTHS_DE[month - 1]} 2025\n"
                f"Personalnummer 4711\n\nGesamtbrutto {de_money(gross)} EUR\n"
                f"Lohnsteuer, Solidaritätszuschlag, Sozialversicherung\n"
                f"Auszahlungsbetrag (netto) {de_money(net)} EUR\nAusgestellt am {de_date(d)}"
            ),
            {
                "category": "income/payslips",
                "document_type": "payslip",
                "correspondent": "Beispiel Software GmbH",
                "document_date": d.isoformat(),
                "language": "de",
                "tags": [],
                "facts": {
                    "gross": {"value": f"{gross:.2f}", "currency": "EUR"},
                    "net": {"value": f"{net:.2f}", "currency": "EUR"},
                    "period_month": date(2025, month, 1).isoformat(),
                },
            },
        )
    for n, (corr, what, end, notice, monthly, lang) in enumerate(
        [
            (
                "Stadtwerke Musterstadt",
                "Stromliefervertrag Ökostrom",
                date(2027, 3, 31),
                90,
                "79.00",
                "de",
            ),
            (
                "NetzFunk Telekom GmbH",
                "Mobilfunkvertrag Allnet",
                date(2026, 12, 31),
                30,
                "24.99",
                "de",
            ),
            ("FitHall Studios", "Gym membership agreement", date(2026, 8, 31), 60, "39.90", "en"),
            (
                "Wohnbau Musterstadt eG",
                "Mietvertrag Wohnung 3.OG links",
                date(2028, 1, 31),
                90,
                "980.00",
                "de",
            ),
        ],
        start=1,
    ):
        start_d = date(end.year - 2, end.month, 1)
        if lang == "de":
            text = (
                f"{corr}\n{what}\nVertragsnummer V-{1000 + n}\n\nVertragsbeginn: {de_date(start_d)}\n"
                f"Vertragsende: {de_date(end)}\nKündigungsfrist: {notice} Tage\n"
                f"Monatlicher Betrag: {de_money(Decimal(monthly))} €\nUnterzeichnet am {de_date(start_d)}"
            )
        else:
            text = (
                f"{corr}\n{what}\nContract no. V-{1000 + n}\n\nStart: {start_d.isoformat()}\n"
                f"End: {end.isoformat()}\nNotice period: {notice} days\n"
                f"Monthly fee: EUR {monthly}\nSigned {start_d.isoformat()}"
            )
        cat = (
            "housing/rent"
            if "Miet" in what
            else "utilities/electricity"
            if "Strom" in what
            else "utilities/internet-phone"
            if "Mobil" in what
            else "legal"
        )
        add(
            f"con-{n:03}",
            text,
            {
                "category": cat,
                "document_type": "contract",
                "correspondent": corr,
                "document_date": start_d.isoformat(),
                "language": lang,
                "tags": [],
                "facts": {
                    "end_date": end.isoformat(),
                    "notice_period_days": str(notice),
                    "monthly_cost": {"value": monthly, "currency": "EUR"},
                    "contract_number": f"V-{1000 + n}",
                },
            },
        )
    for n, (cat, kind, premium, interval) in enumerate(
        [
            ("insurance/vehicle", "Kfz-Haftpflicht", "412.80", "yearly"),
            ("insurance/home", "Privathaftpflicht", "6.90", "monthly"),
            ("insurance/health", "Krankenversicherung", "512.40", "monthly"),
        ],
        start=1,
    ):
        renew = date(2026, rng.randint(1, 12), 1)
        add(
            f"ins-{n:03}",
            (
                f"Versicherung Nord AG\nVersicherungsschein {kind}\nPolice Nr. VN-{77000 + n}\n\n"
                f"Beitrag: {de_money(Decimal(premium))} € "
                f"{'jährlich' if interval == 'yearly' else 'monatlich'}\n"
                f"Hauptfälligkeit / Verlängerung: {de_date(renew)}\nAusgestellt am 02.01.2025"
            ),
            {
                "category": cat,
                "document_type": "insurance-policy",
                "correspondent": "Versicherung Nord AG",
                "document_date": "2025-01-02",
                "language": "de",
                "tags": [],
                "facts": {
                    "policy_number": f"VN-{77000 + n}",
                    "renewal_date": renew.isoformat(),
                    "premium": {"value": premium, "currency": "EUR"},
                    "premium_interval": interval,
                },
            },
            restricted=cat == "insurance/health",
        )
    add(
        "tax-001",
        (
            "Finanzamt Musterstadt\nBescheid für 2024 über Einkommensteuer\nVom 15.07.2025\n\n"
            "Festgesetzt werden: Einkommensteuer\nNachzahlung: 1.234,00 €\n"
            "Bitte zahlen Sie bis zum 18.08.2025."
        ),
        {
            "category": "finance/tax",
            "document_type": "tax-document",
            "correspondent": "Finanzamt Musterstadt",
            "document_date": "2025-07-15",
            "language": "de",
            "tags": ["tax-relevant"],
            "facts": {
                "tax_year": "2024",
                "due_date": "2025-08-18",
                "amount_due": {"value": "1234.00", "currency": "EUR"},
            },
        },
    )
    add(
        "let-001",
        (
            "Deutsche Rentenversicherung Musterland\nIhre Renteninformation\n12.05.2025\n\n"
            "Sehr geehrte Damen und Herren, wir informieren Sie über die Änderung Ihrer "
            "Rentenanwartschaft. Die Regelaltersrente beginnt nach heutigem Stand 2051."
        ),
        {
            "category": "income/benefits",
            "document_type": "letter",
            "correspondent": "Deutsche Rentenversicherung Musterland",
            "document_date": "2025-05-12",
            "language": "de",
            "tags": [],
            "facts": {},
        },
    )
    add(
        "let-002",
        (
            "Stadt Musterstadt Bürgeramt\nBenachrichtigung über die Ummeldung\n02.09.2025\n\n"
            "Ihre Anmeldung der neuen Wohnung wurde bestätigt. Bitte bewahren Sie dieses "
            "Schreiben auf."
        ),
        {
            "category": "government/official",
            "document_type": "letter",
            "correspondent": "Stadt Musterstadt Bürgeramt",
            "document_date": "2025-09-02",
            "language": "de",
            "tags": [],
            "facts": {},
        },
    )
    add(
        "cert-001",
        (
            "Beispiel Software GmbH\nEmployment reference\nJune 30, 2025\n\n"
            "We confirm that the employee worked with us as a software developer and "
            "always performed to our full satisfaction."
        ),
        {
            "category": "employment",
            "document_type": "certificate",
            "correspondent": "Beispiel Software GmbH",
            "document_date": "2025-06-30",
            "language": "en",
            "tags": [],
            "facts": {},
        },
    )
    add(
        "id-001",
        (
            "BUNDESREPUBLIK DEUTSCHLAND\nPERSONALAUSWEIS\nDokumentnummer L01X00T47\n"
            "Gültig bis 30.06.2031\nStadt Musterstadt Bürgeramt\nAusgestellt 01.07.2021"
        ),
        {
            "category": "government/identity",
            "document_type": "id-document",
            "correspondent": "Stadt Musterstadt Bürgeramt",
            "document_date": "2021-07-01",
            "language": "de",
            "tags": [],
            "facts": {"document_number": "L01X00T47", "expiry_date": "2031-06-30"},
        },
        restricted=True,
    )
    add(
        "med-001",
        (
            "Praxis Dr. Beispiel · Allgemeinmedizin\nBefundbericht\n03.03.2025\n\n"
            "Diagnose: unauffälliger Befund. Kontrolle in 12 Monaten empfohlen."
        ),
        {
            "category": "health",
            "document_type": "medical-report",
            "correspondent": "Praxis Dr. Beispiel",
            "document_date": "2025-03-03",
            "language": "de",
            "tags": [],
            "facts": {},
        },
        restricted=True,
    )
    for n, (shop, product, end) in enumerate(
        [
            ("TechHaus Online", "Laptop ProBook 14", date(2027, 2, 14)),
            ("Elektro Markt Berlin", "Waschmaschine WM 800", date(2028, 5, 2)),
        ],
        start=1,
    ):
        add(
            f("war", n),
            (
                f"{shop}\nGarantiezertifikat\nProdukt: {product}\nKaufdatum: "
                f"{de_date(date(end.year - 2, end.month, end.day))}\n"
                f"Garantie bis: {de_date(end)}"
            ),
            {
                "category": "purchases/warranties",
                "document_type": "warranty",
                "correspondent": shop,
                "document_date": date(end.year - 2, end.month, end.day).isoformat(),
                "language": "de",
                "tags": [],
                "facts": {"warranty_end": end.isoformat()},
            },
        )
    for n in range(1, 3):
        d = date(2025, 3 * n, 31 if n == 1 else 30)
        bal = Decimal(rng.randint(100000, 900000)) / 100
        add(
            f("bnk", n),
            (
                f"Musterbank AG\nKontoauszug Nr. {n}/2025\nIBAN DE89 3704 0044 0532 0130 00\n"
                f"Zeitraum {de_date(date(d.year, d.month - 2, 1))} - {de_date(d)}\n\n"
                f"Neuer Kontostand: {de_money(bal)} EUR"
            ),
            {
                "category": "finance/banking",
                "document_type": "bank-statement",
                "correspondent": "Musterbank AG",
                "document_date": d.isoformat(),
                "language": "de",
                "tags": [],
                "facts": {
                    "closing_balance": {"value": f"{bal:.2f}", "currency": "EUR"},
                    "period_end": d.isoformat(),
                    "account_iban": "DE89370400440532013000",
                },
            },
        )


def f(prefix: str, n: int) -> str:
    return f"{prefix}-{n:03}"


def main() -> None:
    for p in (OUT / "docs").glob("*.txt"):
        p.unlink()
    invoices()
    receipts()
    other_types()
    assert len(docs) == 40, len(docs)
    (OUT / "labels.yaml").write_text(yaml.safe_dump(docs, sort_keys=False, allow_unicode=True))
    elec = [
        d["id"]
        for d in docs
        if d["expect"]["category"] == "utilities/electricity"
        and d["expect"]["document_type"] == "invoice"
    ]
    search = [
        {"query": "Stromrechnung", "expect": elec, "k": 10},
        {"query": "electricity invoice", "expect": elec, "k": 10},
        {"query": "Brief über meine Rentenänderung", "expect": ["let-001"], "k": 5},
        {"query": "Kündigungsfrist Mietvertrag", "expect": ["con-004"], "k": 5},
        {"query": "Kfz Versicherung Police", "expect": ["ins-001"], "k": 5},
        {"query": "Garantie Waschmaschine", "expect": ["war-002"], "k": 5},
        {"query": "Steuerbescheid Nachzahlung", "expect": ["tax-001"], "k": 5},
        {
            "query": "Gehaltsabrechnung",
            "expect": [d["id"] for d in docs if d["id"].startswith("pay-")],
            "k": 10,
        },
    ]
    (OUT / "search.yaml").write_text(yaml.safe_dump(search, sort_keys=False, allow_unicode=True))
    total = sum(
        Decimal(d["expect"]["facts"]["amount_total"]["value"]) for d in docs if d["id"] in elec
    )
    qa = [
        {
            "question": "How much did I pay for electricity in 2025?",
            "expect_citations": elec,
            "expect_number": {"value": float(total), "tolerance": 0.01},
        },
        {"question": "Wann endet mein Stromvertrag?", "expect_citations": ["con-001"]},
        {
            "question": "Welche Kündigungsfrist hat mein Mietvertrag?",
            "expect_citations": ["con-004"],
            "expect_number": {"value": 90, "tolerance": 0},
        },
    ]
    (OUT / "qa.yaml").write_text(yaml.safe_dump(qa, sort_keys=False, allow_unicode=True))
    print(f"wrote {len(docs)} documents")


if __name__ == "__main__":
    main()
