"""Bank statement files: CAMT.053 (XML), MT940 and the banks' own CSV exports.

Every parser returns a `Statement`; amounts are signed `Decimal`s (money in > 0). The sign comes
from the file's credit/debit marker, never from the text.
"""

import csv
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from defusedxml import ElementTree


class NotAStatement(ValueError):
    """The file is not a statement this plugin can read."""


@dataclass
class Transaction:
    booking_date: date
    amount: Decimal
    currency: str
    value_date: date | None = None
    counterparty: str | None = None
    counterparty_iban: str | None = None
    purpose: str = ""
    end_to_end_id: str | None = None
    bank_reference: str | None = None

    def fingerprint(self) -> str:
        if self.bank_reference:
            return "ref:" + self.bank_reference
        parts = [
            self.booking_date.isoformat(),
            str(self.amount),
            (self.counterparty_iban or "").replace(" ", "").upper(),
            " ".join(self.purpose.split()).lower(),
            self.end_to_end_id or "",
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


@dataclass
class Statement:
    format: str
    iban: str | None
    currency: str = "EUR"
    period_start: date | None = None
    period_end: date | None = None
    opening: Decimal | None = None
    closing: Decimal | None = None
    transactions: list[Transaction] = field(default_factory=list)

    def balanced(self) -> bool | None:
        """None when the file states no balances; otherwise whether they add up."""
        if self.opening is None or self.closing is None:
            return None
        return self.opening + sum((t.amount for t in self.transactions), Decimal(0)) == self.closing


def text_of(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def parse(data: bytes, csv_formats: dict) -> Statement:
    text = text_of(data)
    head = text.lstrip()[:2000]
    if head.startswith("<") and "camt.053" in head:
        return parse_camt(data)
    if re.search(r"(?m)^:20:", head) and ":61:" in text:
        return parse_mt940(text)
    return parse_csv(text, csv_formats)


# CAMT.053 -------------------------------------------------------------------------------------


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(el, path: str):  # type: ignore[no-untyped-def]
    """First descendant along a path of local names, ignoring XML namespaces."""
    for step in path.split("/"):
        if el is None:
            return None
        el = next((c for c in el if _local(c.tag) == step), None)
    return el


def _all(el, name: str) -> list:  # type: ignore[no-untyped-def]
    return [c for c in el if _local(c.tag) == name] if el is not None else []


def _text(el, path: str) -> str | None:  # type: ignore[no-untyped-def]
    found = _find(el, path)
    return found.text.strip() if found is not None and found.text else None


def _amount(el) -> tuple[Decimal, str] | None:  # type: ignore[no-untyped-def]
    if el is None or el.text is None:
        return None
    return Decimal(el.text.strip()), el.get("Ccy", "EUR")


def _date(el, path: str) -> date | None:  # type: ignore[no-untyped-def]
    raw = _text(el, f"{path}/Dt") or (_text(el, f"{path}/DtTm") or "")[:10]
    return date.fromisoformat(raw) if raw else None


def parse_camt(data: bytes) -> Statement:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        raise NotAStatement(f"The XML could not be read: {error}") from None
    stmt = _find(root, "BkToCstmrStmt/Stmt")
    if stmt is None:
        raise NotAStatement("No statement in this CAMT file")
    out = Statement(format="camt.053", iban=_text(stmt, "Acct/Id/IBAN"))
    out.currency = _text(stmt, "Acct/Ccy") or "EUR"
    for bal in _all(stmt, "Bal"):
        code = _text(bal, "Tp/CdOrPrtry/Cd")
        found = _amount(_find(bal, "Amt"))
        if found is None:
            continue
        value = found[0] if _text(bal, "CdtDbtInd") == "CRDT" else -found[0]
        if code in ("OPBD", "PRCD") and out.opening is None:
            out.opening, out.period_start = value, _date(bal, "Dt")
        if code == "CLBD":
            out.closing, out.period_end = value, _date(bal, "Dt")
    for entry in _all(stmt, "Ntry"):
        if (_text(entry, "Sts/Cd") or _text(entry, "Sts") or "BOOK") != "BOOK":
            continue  # pending or informational entries are not on the statement
        sign = 1 if _text(entry, "CdtDbtInd") == "CRDT" else -1
        booked = _date(entry, "BookgDt") or out.period_end
        entry_amount = _amount(_find(entry, "Amt"))
        if booked is None or entry_amount is None:
            continue
        details = [tx for d in _all(entry, "NtryDtls") for tx in _all(d, "TxDtls")]
        amounts = [_amount(_find(tx, "AmtDtls/TxAmt/Amt")) for tx in details]
        if len(details) > 1 and all(amounts):  # a batch: one transaction per item
            items = list(zip(details, amounts, strict=True))
        else:
            items = [(details[0] if details else None, entry_amount)]
        party = "Dbtr" if sign > 0 else "Cdtr"
        for tx, (amount, currency) in items:  # type: ignore[misc]
            purpose = " ".join(u.text.strip() for u in _all(_find(tx, "RmtInf"), "Ustrd") if u.text)
            e2e = _text(tx, "Refs/EndToEndId")
            out.transactions.append(
                Transaction(
                    booking_date=booked,
                    value_date=_date(entry, "ValDt"),
                    amount=sign * amount,
                    currency=currency,
                    counterparty=_text(tx, f"RltdPties/{party}/Nm")
                    or _text(tx, f"RltdPties/{party}/Pty/Nm"),
                    counterparty_iban=_text(tx, f"RltdPties/{party}Acct/Id/IBAN"),
                    purpose=purpose or (_text(entry, "AddtlNtryInf") or ""),
                    end_to_end_id=e2e if e2e and e2e != "NOTPROVIDED" else None,
                    # The bank's reference names the whole entry, so only a single item has it.
                    bank_reference=(_text(tx, "Refs/AcctSvcrRef") or _text(entry, "AcctSvcrRef"))
                    if len(items) == 1
                    else None,
                )
            )
    return out


# MT940 ----------------------------------------------------------------------------------------

LINE61 = re.compile(
    r"(?P<value>\d{6})(?P<entry>\d{4})?(?P<mark>RC|RD|C|D)(?P<fund>[A-Z])?"
    r"(?P<amount>\d+,\d{0,2})N?(?P<code>\w{3})?(?P<ref>[^/\n]*)(?://(?P<bankref>\S+))?"
)


def _mt_date(raw: str) -> date:
    return datetime.strptime(raw, "%y%m%d").date()


def _mt_amount(raw: str) -> Decimal:
    return Decimal(raw.replace(",", "."))


def _fields(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        match = re.match(r"^:(\d\d[A-Z]?):(.*)$", line)
        if match:
            out.append((match[1], match[2]))
        elif out and line and line != "-":
            out[-1] = (out[-1][0], out[-1][1] + "\n" + line)
    return out


def parse_mt940(text: str) -> Statement:
    out = Statement(format="mt940", iban=None)
    last: Transaction | None = None
    for tag, value in _fields(text):
        if tag == "25":
            account = value.strip().split("/")[-1].replace(" ", "")
            out.iban = account if re.match(r"^[A-Z]{2}\d{2}", account) else value.strip()
        elif tag in ("60F", "60M", "62F"):
            match = re.match(r"([CD])(\d{6})([A-Z]{3})([\d,]+)", value.strip())
            if not match:
                continue
            amount = _mt_amount(match[4]) * (1 if match[1] == "C" else -1)
            if tag.startswith("60") and out.opening is None:
                out.opening, out.period_start, out.currency = amount, _mt_date(match[2]), match[3]
            elif tag == "62F":
                out.closing, out.period_end = amount, _mt_date(match[2])
        elif tag == "61":
            match = LINE61.match(value.split("\n")[0].strip())
            if not match:
                continue
            booked = _mt_date(match["value"])
            if match["entry"]:  # MMDD, in the value date's year (or the next one in January)
                entry = date(booked.year, int(match["entry"][:2]), int(match["entry"][2:]))
                booked = (
                    entry
                    if abs((entry - booked).days) < 200
                    else entry.replace(year=entry.year + 1)
                )
            sign = 1 if match["mark"] in ("C", "RD") else -1
            last = Transaction(
                booking_date=booked,
                value_date=_mt_date(match["value"]),
                amount=sign * _mt_amount(match["amount"]),
                currency=out.currency,
                bank_reference=(match["bankref"] or None),
            )
            ref = (match["ref"] or "").strip()
            if ref and ref != "NONREF":
                last.end_to_end_id = ref
            out.transactions.append(last)
        elif tag == "86" and last is not None:
            joined = value.replace("\n", "")
            parts = dict(re.findall(r"\?(\d\d)([^?]*)", joined))
            if parts:
                last.purpose = " ".join(
                    parts[k] for k in sorted(parts) if "20" <= k <= "29" or "60" <= k <= "63"
                ).strip()
                last.counterparty = (parts.get("32", "") + parts.get("33", "")).strip() or None
                last.counterparty_iban = parts.get("31", "").strip() or None
                if e2e := re.search(r"EREF\+(\S+)", last.purpose):
                    last.end_to_end_id = e2e[1] if e2e[1] != "NOTPROVIDED" else None
            else:
                last.purpose = joined.strip()
    if not out.transactions and out.opening is None:
        raise NotAStatement("No MT940 statement data found")
    return out


# CSV ------------------------------------------------------------------------------------------


def _number(raw: str, decimal: str, thousands: str | None) -> Decimal:
    clean = raw.strip().replace(" ", "").replace(" ", "")
    if thousands:
        clean = clean.replace(thousands, "")
    clean = clean.replace(decimal, ".")
    try:
        return Decimal(clean)
    except InvalidOperation:
        raise NotAStatement(f"'{raw}' is not an amount") from None


def _rows(text: str, fmt: dict) -> list[dict[str, str]] | None:
    """The data rows as {column: value}, or None when the header is not in the file."""
    lines = text.replace("\r\n", "\n").split("\n")
    reader = csv.reader(lines, delimiter=fmt.get("delimiter", ";"))
    rows = list(reader)
    wanted = {str(h) for h in fmt["header"]}
    for index, row in enumerate(rows):
        cells = [c.strip() for c in row]
        if wanted <= set(cells):
            return [
                dict(zip(cells, (v.strip() for v in data), strict=False))
                for data in rows[index + 1 :]
                if any(v.strip() for v in data)
            ]
    return None


def _cell(row: dict[str, str], spec: dict | None) -> str | None:
    if not spec:
        return None
    if "value" in spec:
        return str(spec["value"])
    columns = spec["column"] if isinstance(spec["column"], list) else [spec["column"]]
    values = [row.get(c, "").strip() for c in columns]
    return " ".join(v for v in values if v) or None


def parse_csv(text: str, formats: dict, name: str | None = None) -> Statement:
    candidates = (
        [(name, formats[name])]
        if name
        else sorted(
            ((k, v) for k, v in formats.items() if isinstance(v, dict) and "header" in v),
            key=lambda kv: (kv[0].startswith("_"), -len(kv[1]["header"])),  # most specific first
        )
    )
    for fmt_name, fmt in candidates:
        rows = _rows(text, fmt)
        if rows is None:
            continue
        out = Statement(format=f"csv:{fmt_name}", iban=None)
        iban_line = re.search(
            r"\b([A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,4})?)\b", text[:600]
        )
        amount_spec, date_spec = fmt["amount"], fmt["date"]
        for row in rows:
            raw_date = _cell(row, date_spec)
            raw_amount = _cell(row, amount_spec)
            if not raw_date or not raw_amount:
                continue
            value_spec = fmt.get("value_date")
            raw_value = _cell(row, value_spec)
            tx = Transaction(
                booking_date=datetime.strptime(raw_date, date_spec["format"]).date(),
                value_date=datetime.strptime(raw_value, value_spec["format"]).date()
                if raw_value and value_spec
                else None,
                amount=_number(
                    raw_amount, amount_spec.get("decimal", ","), amount_spec.get("thousands")
                ),
                currency=_cell(row, fmt.get("currency")) or "EUR",
                counterparty=_cell(row, fmt.get("name")),
                counterparty_iban=(_cell(row, fmt.get("iban")) or "").replace(" ", "") or None,
                purpose=_cell(row, fmt.get("text")) or "",
                bank_reference=_cell(row, fmt.get("reference")),
            )
            out.transactions.append(tx)
            account = _cell(row, fmt.get("account"))
            if account and not out.iban:
                out.iban = account.replace(" ", "")
        if out.iban is None and iban_line:
            out.iban = iban_line[1].replace(" ", "")
        if not out.transactions:
            continue
        dates = [t.booking_date for t in out.transactions]
        out.period_start, out.period_end = min(dates), max(dates)
        out.currency = out.transactions[0].currency
        return out
    raise NotAStatement("This CSV file does not match a known bank format")
