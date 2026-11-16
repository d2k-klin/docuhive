# ruff: noqa: E501 - XML samples are kept readable as one element per line
"""Made-up e-invoices in both syntaxes. No real business appears here."""

CII = """<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
  xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
  xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
 <rsm:ExchangedDocument><ram:ID>RE-2026-0042</ram:ID><ram:TypeCode>380</ram:TypeCode>
  <ram:IssueDateTime><udt:DateTimeString format="102">20260302</udt:DateTimeString></ram:IssueDateTime></rsm:ExchangedDocument>
 <rsm:SupplyChainTradeTransaction>
  <ram:ApplicableHeaderTradeAgreement>
   <ram:SellerTradeParty><ram:Name>Bürobedarf Beispiel GmbH</ram:Name>
    <ram:SpecifiedTaxRegistration><ram:ID schemeID="FC">12/345/67890</ram:ID></ram:SpecifiedTaxRegistration>
    <ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">DE123456789</ram:ID></ram:SpecifiedTaxRegistration></ram:SellerTradeParty>
   <ram:BuyerTradeParty><ram:Name>Freiberuf Muster</ram:Name></ram:BuyerTradeParty></ram:ApplicableHeaderTradeAgreement>
  <ram:ApplicableHeaderTradeDelivery><ram:ActualDeliverySupplyChainEvent><ram:OccurrenceDateTime>
   <udt:DateTimeString format="102">20260227</udt:DateTimeString></ram:OccurrenceDateTime></ram:ActualDeliverySupplyChainEvent></ram:ApplicableHeaderTradeDelivery>
  <ram:ApplicableHeaderTradeSettlement><ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
   <ram:SpecifiedTradeSettlementPaymentMeans><ram:TypeCode>58</ram:TypeCode>
    <ram:PayeePartyCreditorFinancialAccount><ram:IBANID>DE89370400440532013000</ram:IBANID></ram:PayeePartyCreditorFinancialAccount></ram:SpecifiedTradeSettlementPaymentMeans>
   <ram:ApplicableTradeTax><ram:CalculatedAmount>19.00</ram:CalculatedAmount><ram:TypeCode>VAT</ram:TypeCode>
    <ram:BasisAmount>100.00</ram:BasisAmount><ram:CategoryCode>S</ram:CategoryCode><ram:RateApplicablePercent>19</ram:RateApplicablePercent></ram:ApplicableTradeTax>
   <ram:ApplicableTradeTax><ram:CalculatedAmount>3.50</ram:CalculatedAmount><ram:TypeCode>VAT</ram:TypeCode>
    <ram:BasisAmount>50.00</ram:BasisAmount><ram:CategoryCode>S</ram:CategoryCode><ram:RateApplicablePercent>7</ram:RateApplicablePercent></ram:ApplicableTradeTax>
   <ram:SpecifiedTradePaymentTerms><ram:DueDateDateTime><udt:DateTimeString format="102">20260316</udt:DateTimeString></ram:DueDateDateTime></ram:SpecifiedTradePaymentTerms>
   <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    <ram:LineTotalAmount>150.00</ram:LineTotalAmount><ram:TaxBasisTotalAmount>150.00</ram:TaxBasisTotalAmount>
    <ram:TaxTotalAmount currencyID="EUR">22.50</ram:TaxTotalAmount><ram:GrandTotalAmount>172.50</ram:GrandTotalAmount>
    <ram:DuePayableAmount>172.50</ram:DuePayableAmount></ram:SpecifiedTradeSettlementHeaderMonetarySummation>
  </ram:ApplicableHeaderTradeSettlement></rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>
"""

UBL = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
 <cbc:ID>2026-118</cbc:ID><cbc:IssueDate>2026-03-05</cbc:IssueDate><cbc:DueDate>2026-03-19</cbc:DueDate>
 <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode><cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
 <cac:InvoicePeriod><cbc:StartDate>2026-02-01</cbc:StartDate><cbc:EndDate>2026-02-28</cbc:EndDate></cac:InvoicePeriod>
 <cac:AccountingSupplierParty><cac:Party><cac:PartyName><cbc:Name>Cloud Beispiel</cbc:Name></cac:PartyName>
  <cac:PartyTaxScheme><cbc:CompanyID>IE9876543X</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>
  <cac:PartyLegalEntity><cbc:RegistrationName>Cloud Beispiel Ltd</cbc:RegistrationName></cac:PartyLegalEntity></cac:Party></cac:AccountingSupplierParty>
 <cac:AccountingCustomerParty><cac:Party><cac:PartyLegalEntity><cbc:RegistrationName>Freiberuf Muster</cbc:RegistrationName></cac:PartyLegalEntity></cac:Party></cac:AccountingCustomerParty>
 <cac:TaxTotal><cbc:TaxAmount currencyID="EUR">0.00</cbc:TaxAmount>
  <cac:TaxSubtotal><cbc:TaxableAmount currencyID="EUR">200.00</cbc:TaxableAmount><cbc:TaxAmount currencyID="EUR">0.00</cbc:TaxAmount>
   <cac:TaxCategory><cbc:ID>AE</cbc:ID><cbc:Percent>0</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:TaxCategory></cac:TaxSubtotal></cac:TaxTotal>
 <cac:LegalMonetaryTotal><cbc:LineExtensionAmount currencyID="EUR">200.00</cbc:LineExtensionAmount>
  <cbc:TaxExclusiveAmount currencyID="EUR">200.00</cbc:TaxExclusiveAmount><cbc:TaxInclusiveAmount currencyID="EUR">200.00</cbc:TaxInclusiveAmount>
  <cbc:PayableAmount currencyID="EUR">200.00</cbc:PayableAmount></cac:LegalMonetaryTotal>
</Invoice>
"""


def zugferd_pdf(xml: str) -> bytes:
    """A one-page PDF carrying the invoice XML as factur-x.xml, as ZUGFeRD does."""
    import io

    import pikepdf

    pdf = pikepdf.new()
    pdf.add_blank_page()
    pdf.attachments["factur-x.xml"] = pikepdf.AttachedFileSpec(
        pdf, xml.encode(), mime_type="text/xml"
    )
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()
