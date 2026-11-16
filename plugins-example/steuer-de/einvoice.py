"""Structured e-invoices (EN 16931): XRechnung as UBL or CII, and ZUGFeRD / Factur-X PDFs.

The figures are data, so they are read exactly and need no AI and no review. Each field
names its EN 16931 business term (BT) so the mapping can be checked against the standard.
"""

import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from defusedxml import ElementTree

EMBEDDED = ("factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml", "zugferd.xml")


class NotAnEInvoice(ValueError):
    pass


@dataclass
class VatLine:
    category: str  # BT-118: S standard, Z zero, E exempt, AE reverse charge, K intra-EU, G export
    rate: Decimal  # BT-119
    base: Decimal  # BT-116
    tax: Decimal  # BT-117


@dataclass
class EInvoice:
    syntax: str  # "cii" or "ubl"
    number: str  # BT-1
    issue_date: date  # BT-2
    type_code: str  # BT-3: 380 invoice, 381 credit note
    currency: str  # BT-5
    seller: str  # BT-27
    seller_vat_id: str | None  # BT-31
    buyer: str | None  # BT-44
    service_date: date | None  # BT-72, or the end of the period BT-74
    due_date: date | None  # BT-9
    net: Decimal  # BT-109
    tax: Decimal  # BT-110
    gross: Decimal  # BT-112
    payable: Decimal  # BT-115
    iban: str | None  # BT-84
    vat: list[VatLine] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def credit_note(self) -> bool:
        return self.type_code in {"381", "261", "396"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first(el, path: str):  # type: ignore[no-untyped-def]
    for step in path.split("/"):
        if el is None:
            return None
        el = next((c for c in el if _local(c.tag) == step), None)
    return el


def _all(el, path: str) -> list:  # type: ignore[no-untyped-def]
    *parents, last = path.split("/")
    for step in parents:
        el = _first(el, step)
    return [c for c in el if _local(c.tag) == last] if el is not None else []


def _text(el, path: str) -> str | None:  # type: ignore[no-untyped-def]
    found = _first(el, path)
    return found.text.strip() if found is not None and found.text and found.text.strip() else None


def _money(el, path: str) -> Decimal:  # type: ignore[no-untyped-def]
    raw = _text(el, path)
    return Decimal(raw) if raw else Decimal(0)


def _cii_date(el, path: str) -> date | None:  # type: ignore[no-untyped-def]
    raw = _text(el, f"{path}/DateTimeString")
    if not raw:
        return None
    raw = raw.replace("-", "")
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))


def _iso(raw: str | None) -> date | None:
    return date.fromisoformat(raw[:10]) if raw else None


def read_cii(root) -> EInvoice:  # type: ignore[no-untyped-def]
    doc = _first(root, "ExchangedDocument")
    tx = _first(root, "SupplyChainTradeTransaction")
    agreement = _first(tx, "ApplicableHeaderTradeAgreement")
    delivery = _first(tx, "ApplicableHeaderTradeDelivery")
    settlement = _first(tx, "ApplicableHeaderTradeSettlement")
    totals = _first(settlement, "SpecifiedTradeSettlementHeaderMonetarySummation")
    if doc is None or settlement is None or totals is None:
        raise NotAnEInvoice("The CII document has no invoice header or totals")
    seller = _first(agreement, "SellerTradeParty")
    currency = _text(settlement, "InvoiceCurrencyCode") or "EUR"
    vat_id = None
    for registration in _all(seller, "SpecifiedTaxRegistration"):
        reg = _first(registration, "ID")
        if reg is not None and reg.get("schemeID") == "VA" and reg.text:
            vat_id = reg.text.strip()
            break
    tax_total = Decimal(0)
    for amount in _all(totals, "TaxTotalAmount"):  # one per currency; take the invoice's
        if amount.text and amount.get("currencyID", currency) == currency:
            tax_total = Decimal(amount.text.strip())
            break
    invoice = EInvoice(
        syntax="cii",
        number=_text(doc, "ID") or "",
        issue_date=_cii_date(doc, "IssueDateTime") or date.min,
        type_code=_text(doc, "TypeCode") or "380",
        currency=currency,
        seller=_text(seller, "Name") or "",
        seller_vat_id=vat_id,
        buyer=_text(agreement, "BuyerTradeParty/Name"),
        service_date=_cii_date(delivery, "ActualDeliverySupplyChainEvent/OccurrenceDateTime")
        or _cii_date(settlement, "BillingSpecifiedPeriod/EndDateTime"),
        due_date=_cii_date(settlement, "SpecifiedTradePaymentTerms/DueDateDateTime"),
        net=_money(totals, "TaxBasisTotalAmount"),
        tax=tax_total,
        gross=_money(totals, "GrandTotalAmount"),
        payable=_money(totals, "DuePayableAmount"),
        iban=_text(
            settlement,
            "SpecifiedTradeSettlementPaymentMeans/PayeePartyCreditorFinancialAccount/IBANID",
        ),
    )
    for t in _all(settlement, "ApplicableTradeTax"):
        invoice.vat.append(
            VatLine(
                category=_text(t, "CategoryCode") or "S",
                rate=_money(t, "RateApplicablePercent"),
                base=_money(t, "BasisAmount"),
                tax=_money(t, "CalculatedAmount"),
            )
        )
    return invoice


def read_ubl(root) -> EInvoice:  # type: ignore[no-untyped-def]
    credit = _local(root.tag) == "CreditNote"
    seller = _first(root, "AccountingSupplierParty/Party")
    totals = _first(root, "LegalMonetaryTotal")
    if totals is None:
        raise NotAnEInvoice("The UBL document has no totals")
    tax_totals = _all(root, "TaxTotal")
    currency = _text(root, "DocumentCurrencyCode") or "EUR"
    tax_total = Decimal(0)
    for t in tax_totals:
        amount = _first(t, "TaxAmount")
        if amount is not None and amount.text and amount.get("currencyID", currency) == currency:
            tax_total = Decimal(amount.text.strip())
            break
    invoice = EInvoice(
        syntax="ubl",
        number=_text(root, "ID") or "",
        issue_date=_iso(_text(root, "IssueDate")) or date.min,
        type_code=_text(root, "CreditNoteTypeCode" if credit else "InvoiceTypeCode")
        or ("381" if credit else "380"),
        currency=currency,
        seller=_text(seller, "PartyLegalEntity/RegistrationName")
        or _text(seller, "PartyName/Name")
        or "",
        seller_vat_id=next(
            (
                _text(s, "CompanyID")
                for s in _all(seller, "PartyTaxScheme")
                if _text(s, "TaxScheme/ID") == "VAT"
            ),
            None,
        ),
        buyer=_text(root, "AccountingCustomerParty/Party/PartyLegalEntity/RegistrationName"),
        service_date=_iso(_text(root, "Delivery/ActualDeliveryDate"))
        or _iso(_text(root, "InvoicePeriod/EndDate")),
        due_date=_iso(_text(root, "DueDate")) or _iso(_text(root, "PaymentMeans/PaymentDueDate")),
        net=_money(totals, "TaxExclusiveAmount"),
        tax=tax_total,
        gross=_money(totals, "TaxInclusiveAmount"),
        payable=_money(totals, "PayableAmount"),
        iban=_text(root, "PaymentMeans/PayeeFinancialAccount/ID"),
    )
    for t in tax_totals:
        for sub in _all(t, "TaxSubtotal"):
            invoice.vat.append(
                VatLine(
                    category=_text(sub, "TaxCategory/ID") or "S",
                    rate=_money(sub, "TaxCategory/Percent"),
                    base=_money(sub, "TaxableAmount"),
                    tax=_money(sub, "TaxAmount"),
                )
            )
    return invoice


def check(invoice: EInvoice) -> list[str]:
    """The arithmetic EN 16931 requires, to the cent."""
    problems = []
    if sum((v.base for v in invoice.vat), Decimal(0)) != invoice.net:
        problems.append("The VAT breakdown's bases do not add up to the net total")
    if sum((v.tax for v in invoice.vat), Decimal(0)) != invoice.tax:
        problems.append("The VAT breakdown does not add up to the VAT total")
    if invoice.net + invoice.tax != invoice.gross:
        problems.append("Net plus VAT is not the gross total")
    for v in invoice.vat:
        expected = (v.base * v.rate / 100).quantize(Decimal("0.01"))
        if abs(expected - v.tax) > Decimal("0.01"):
            problems.append(f"VAT at {v.rate} % on {v.base} should be {expected}, not {v.tax}")
    if not invoice.number:
        problems.append("No invoice number")
    return problems


def parse_xml(data: bytes) -> EInvoice:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        raise NotAnEInvoice(f"The XML could not be read: {error}") from None
    name = _local(root.tag)
    if name == "CrossIndustryInvoice":
        invoice = read_cii(root)
    elif name in {"Invoice", "CreditNote"}:
        invoice = read_ubl(root)
    else:
        raise NotAnEInvoice(f"{name} is not an invoice")
    invoice.problems = check(invoice)
    return invoice


def embedded_xml(pdf: bytes) -> bytes | None:
    """The invoice XML a ZUGFeRD / Factur-X PDF carries as an attachment."""
    import pikepdf

    try:
        with pikepdf.open(io.BytesIO(pdf)) as document:
            files = document.attachments
            for name in files:
                if name.lower() in EMBEDDED or name.lower().endswith(".xml"):
                    return files[name].get_file().read_bytes()
    except pikepdf.PdfError:
        return None
    return None


def find(original: bytes) -> EInvoice | None:
    """The e-invoice in a document's original file, or None when it carries none."""
    head = original.lstrip()[:200]
    if head.startswith(b"%PDF"):
        xml = embedded_xml(original)
        return parse_xml(xml) if xml else None
    if head.startswith(b"<") or head.startswith(b"\xef\xbb\xbf<"):
        try:
            return parse_xml(original)
        except NotAnEInvoice:
            return None
    return None


# Writing -------------------------------------------------------------------------------------
# Our invoices as CII (UN/CEFACT Cross Industry Invoice D16B), EN 16931 profile. XRechnung uses
# the same syntax with its own guideline id and a few more mandatory fields. Element order follows
# the schema; the official validator runs over generated invoices in CI.

RSM = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
UDT = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"
GUIDELINES = {
    "zugferd": "urn:cen.eu:en16931:2017",
    "xrechnung": "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0",
}


def write_cii(inv: dict, flavour: str = "zugferd") -> bytes:
    """`inv` is the issued invoice: number, type_code, issue_date, currency, seller, buyer,
    service_from/to, due_date, payment_text, lines, breakdown, net, tax, gross, refers_to."""
    from xml.etree.ElementTree import Element, SubElement, register_namespace, tostring

    for prefix, uri in (("rsm", RSM), ("ram", RAM), ("udt", UDT)):
        register_namespace(prefix, uri)

    def add(parent, path: str, value=None, **attrs):  # type: ignore[no-untyped-def]
        node = parent
        for step in path.split("/"):
            ns, name = step.split(":")
            node = SubElement(node, f"{{{ {'rsm': RSM, 'ram': RAM, 'udt': UDT}[ns] }}}{name}")
        for key, val in attrs.items():
            node.set(key, val)
        if value is not None:
            node.text = str(value)
        return node

    def when(parent, path: str, day: date) -> None:
        add(parent, f"{path}/udt:DateTimeString", day.strftime("%Y%m%d"), format="102")

    def money(value: Decimal) -> str:
        return f"{value:.2f}"

    def party(parent, tag: str, p: dict, *, contact: bool = False) -> None:
        node = add(parent, tag)
        add(node, "ram:Name", p["name"])
        if contact:  # BG-6, required by XRechnung
            c = add(node, "ram:DefinedTradeContact")
            add(c, "ram:PersonName", p.get("contact") or p["name"])
            add(c, "ram:TelephoneUniversalCommunication/ram:CompleteNumber", p.get("phone") or "")
            add(c, "ram:EmailURIUniversalCommunication/ram:URIID", p.get("email") or "")
        address = add(node, "ram:PostalTradeAddress")
        add(address, "ram:PostcodeCode", p.get("postcode") or "")
        add(address, "ram:LineOne", p.get("street") or "")
        add(address, "ram:CityName", p.get("city") or "")
        add(address, "ram:CountryID", p.get("country") or "DE")
        if p.get("email"):
            add(node, "ram:URIUniversalCommunication/ram:URIID", p["email"], schemeID="EM")
        if p.get("vat_id"):
            add(node, "ram:SpecifiedTaxRegistration/ram:ID", p["vat_id"], schemeID="VA")
        if p.get("tax_number"):
            add(node, "ram:SpecifiedTaxRegistration/ram:ID", p["tax_number"], schemeID="FC")

    root = Element(f"{{{RSM}}}CrossIndustryInvoice")
    add(
        root,
        "rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID",
        GUIDELINES[flavour],
    )
    doc = add(root, "rsm:ExchangedDocument")
    add(doc, "ram:ID", inv["number"])
    add(doc, "ram:TypeCode", inv["type_code"])
    when(doc, "ram:IssueDateTime", inv["issue_date"])
    for note in inv.get("notes", []):
        add(doc, "ram:IncludedNote/ram:Content", note)
    tx = add(root, "rsm:SupplyChainTradeTransaction")
    for line in inv["lines"]:
        item = add(tx, "ram:IncludedSupplyChainTradeLineItem")
        add(item, "ram:AssociatedDocumentLineDocument/ram:LineID", line["position"])
        add(item, "ram:SpecifiedTradeProduct/ram:Name", line["description"])
        add(
            item,
            "ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount",
            f"{line['net_price']:f}",
        )
        add(
            item,
            "ram:SpecifiedLineTradeDelivery/ram:BilledQuantity",
            f"{line['quantity']:f}",
            unitCode=line["unit"],
        )
        settlement = add(item, "ram:SpecifiedLineTradeSettlement")
        tax = add(settlement, "ram:ApplicableTradeTax")
        add(tax, "ram:TypeCode", "VAT")
        add(tax, "ram:CategoryCode", line["category"])
        add(tax, "ram:RateApplicablePercent", f"{line['rate']:f}")
        add(
            settlement,
            "ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount",
            money(line["net"]),
        )
    agreement = add(tx, "ram:ApplicableHeaderTradeAgreement")
    if inv["buyer"].get("routing_id"):
        add(agreement, "ram:BuyerReference", inv["buyer"]["routing_id"])
    party(agreement, "ram:SellerTradeParty", inv["seller"], contact=flavour == "xrechnung")
    party(agreement, "ram:BuyerTradeParty", inv["buyer"])
    delivery = add(tx, "ram:ApplicableHeaderTradeDelivery")
    when(
        delivery,
        "ram:ActualDeliverySupplyChainEvent/ram:OccurrenceDateTime",
        inv.get("service_to") or inv["issue_date"],
    )
    settle = add(tx, "ram:ApplicableHeaderTradeSettlement")
    add(settle, "ram:InvoiceCurrencyCode", inv["currency"])
    if inv["seller"].get("iban"):
        means = add(settle, "ram:SpecifiedTradeSettlementPaymentMeans")
        add(means, "ram:TypeCode", "58")  # SEPA credit transfer
        add(means, "ram:PayeePartyCreditorFinancialAccount/ram:IBANID", inv["seller"]["iban"])
    for part in inv["breakdown"]:
        tax = add(settle, "ram:ApplicableTradeTax")
        add(tax, "ram:CalculatedAmount", money(part["tax"]))
        add(tax, "ram:TypeCode", "VAT")
        if part.get("reason"):
            add(tax, "ram:ExemptionReason", part["reason"])
        add(tax, "ram:BasisAmount", money(part["base"]))
        add(tax, "ram:CategoryCode", part["category"])
        add(tax, "ram:RateApplicablePercent", f"{part['rate']:f}")
    if inv.get("service_from") and inv.get("service_to"):
        period = add(settle, "ram:BillingSpecifiedPeriod")
        when(period, "ram:StartDateTime", inv["service_from"])
        when(period, "ram:EndDateTime", inv["service_to"])
    terms = add(settle, "ram:SpecifiedTradePaymentTerms")
    if inv.get("payment_text"):
        add(terms, "ram:Description", inv["payment_text"])
    if inv.get("due_date"):
        when(terms, "ram:DueDateDateTime", inv["due_date"])
    totals = add(settle, "ram:SpecifiedTradeSettlementHeaderMonetarySummation")
    add(totals, "ram:LineTotalAmount", money(inv["net"]))
    add(totals, "ram:TaxBasisTotalAmount", money(inv["net"]))
    add(totals, "ram:TaxTotalAmount", money(inv["tax"]), currencyID=inv["currency"])
    add(totals, "ram:GrandTotalAmount", money(inv["gross"]))
    add(totals, "ram:DuePayableAmount", money(inv["gross"]))
    if inv.get("refers_to"):
        ref = add(settle, "ram:InvoiceReferencedDocument")
        add(ref, "ram:IssuerAssignedID", inv["refers_to"]["number"])
        when(ref, "ram:FormattedIssueDateTime", inv["refers_to"]["issue_date"])
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="utf-8")
