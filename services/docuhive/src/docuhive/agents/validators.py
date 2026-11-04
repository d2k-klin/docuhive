"""Pure parsers and checks for model output. Deterministic work stays out of the model."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

MIN_DATE = date(1950, 1, 1)
FACT_YEARS_AHEAD = 30

_SYMBOLS = {
    "€": "EUR",
    "$": "USD",
    "£": "GBP",
    "chf": "CHF",
    "fr.": "CHF",
    "eur": "EUR",
    "euro": "EUR",
    "usd": "USD",
    "gbp": "GBP",
}
_MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("januar", "jänner", "january", "jan"),
            ("februar", "february", "feb"),
            ("märz", "maerz", "march", "mar", "mär"),
            ("april", "apr"),
            ("mai", "may"),
            ("juni", "june", "jun"),
            ("juli", "july", "jul"),
            ("august", "aug"),
            ("september", "sept", "sep"),
            ("oktober", "october", "okt", "oct"),
            ("november", "nov"),
            ("dezember", "december", "dez", "dec"),
        ]
    )
    for m in names
}
# IBAN lengths per country (common in DocuHive's audience; extend as needed).
_IBAN_LEN = {
    "AT": 20,
    "BE": 16,
    "CH": 21,
    "CZ": 24,
    "DE": 22,
    "DK": 18,
    "ES": 24,
    "FI": 18,
    "FR": 27,
    "GB": 22,
    "HR": 21,
    "HU": 28,
    "IE": 22,
    "IT": 27,
    "LI": 21,
    "LU": 20,
    "MK": 19,
    "NL": 18,
    "NO": 15,
    "PL": 28,
    "PT": 25,
    "RS": 22,
    "SE": 24,
    "SI": 19,
    "SK": 24,
}


class Invalid(ValueError):
    pass


def currency_of(text: str | None) -> str | None:
    """ISO 4217 from a code or symbol inside `text`."""
    if not text:
        return None
    if m := re.search(r"\b([A-Z]{3})\b", text):
        if m.group(1) not in ("IBAN", "BIC", "VAT", "UST", "MWS"):
            return m.group(1)
    low = text.lower()
    return next((iso for sym, iso in _SYMBOLS.items() if sym in low), None)


def parse_money(
    raw: str, currency: str | None = None, *, default_currency: str = "EUR"
) -> tuple[Decimal, str]:
    """'1.234,56 €', '1,234.56', 'EUR 84.20' -> (Decimal('1234.56'), 'EUR'). Amount must be > 0."""
    cur = (currency or "").strip().upper() or None
    cur = _SYMBOLS.get(cur.lower(), cur) if cur else None
    cur = cur or currency_of(raw) or default_currency
    if not re.fullmatch(r"[A-Z]{3}", cur):
        raise Invalid(f"currency {cur!r} is not ISO 4217")
    num = re.sub(r"[^\d.,\-]", "", raw)
    if not re.search(r"\d", num):
        raise Invalid(f"no amount in {raw!r}")
    if "," in num and "." in num:  # the right-most separator is the decimal one
        dec = "," if num.rfind(",") > num.rfind(".") else "."
        num = num.replace("." if dec == "," else ",", "").replace(",", ".")
    elif "," in num:  # 84,20 (decimal) vs 1,234 (thousands)
        head, _, tail = num.rpartition(",")
        num = f"{head.replace(',', '')}.{tail}" if len(tail) != 3 else num.replace(",", "")
    elif num.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", num):  # 1.234.567 / 1.234
        num = num.replace(".", "")
    try:
        value = Decimal(num).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise Invalid(f"cannot parse amount {raw!r}") from None
    if value <= 0:
        raise Invalid("amount must be greater than 0")
    return value, cur


def parse_date(raw: str, *, today: date | None = None, years_ahead: int = 1) -> date:
    """ISO, DD.MM.YYYY, D. Monat YYYY, Month D, YYYY. Must be 1950 .. today + `years_ahead`."""
    s = raw.strip().lower().replace(" ", " ")
    d: date | None = None
    try:
        if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s):
            d = date(int(m[1]), int(m[2]), int(m[3]))
        elif m := re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{2}|\d{4})", s):
            year = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
            d = date(year, int(m[2]), int(m[1]))
        elif m := re.fullmatch(r"(\d{1,2})\.?\s+([a-zäö]+)\.?\s+(\d{4})", s):
            d = date(int(m[3]), _MONTHS[m[2]], int(m[1]))
        elif m := re.fullmatch(r"([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", s):
            d = date(int(m[3]), _MONTHS[m[1]], int(m[2]))
    except (KeyError, ValueError):
        d = None
    if d is None:
        raise Invalid(f"unrecognised date {raw!r}")
    check_date_range(d, today, years_ahead)
    return d


def check_date_range(d: date, today: date | None = None, years_ahead: int = 1) -> date:
    """Issue dates: at most a year ahead. Fact dates (expiry, contract end) pass years_ahead."""
    today = today or date.today()
    if d < MIN_DATE or d > date(today.year + years_ahead, today.month, min(today.day, 28)):
        raise Invalid(f"date {d} is outside 1950 .. {years_ahead} year(s) from now")
    return d


def parse_number(raw: str) -> Decimal:
    s = raw.strip().replace(" ", "")
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return Decimal(re.sub(r"[^\d.\-]", "", s) or "x")
    except InvalidOperation:
        raise Invalid(f"not a number: {raw!r}") from None


def parse_iban(raw: str) -> str:
    iban = re.sub(r"\s+", "", raw).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{8,30}", iban):
        raise Invalid("IBAN format")
    expected = _IBAN_LEN.get(iban[:2])
    if expected and len(iban) != expected:
        raise Invalid(f"{iban[:2]} IBANs have {expected} characters")
    digits = "".join(str(int(c, 36)) for c in iban[4:] + iban[:4])
    if int(digits) % 97 != 1:
        raise Invalid("IBAN checksum")
    return iban


def clean_string(raw: str) -> str:
    s = " ".join(raw.split())
    if not s:
        raise Invalid("empty")
    return s[:200]


def canonical(
    fact_type: str, raw: str, currency: str | None = None, *, default_currency: str = "EUR"
) -> tuple[str, str | None]:
    """(canonical value string, currency) for a FactValue, or raises Invalid."""
    if fact_type == "money":
        v, cur = parse_money(raw, currency, default_currency=default_currency)
        return str(v), cur
    if fact_type == "date":  # expiry dates, contract ends: decades ahead are legitimate
        return parse_date(raw, years_ahead=FACT_YEARS_AHEAD).isoformat(), None
    if fact_type == "number":
        return str(parse_number(raw)), None
    if fact_type == "iban":
        return parse_iban(raw), None
    return clean_string(raw), None


def norm_name(name: str) -> str:
    """Same rule as OA's correspondent normalisation: casefold, trimmed, collapsed spaces."""
    return " ".join(name.casefold().split())


def _trigrams(s: str) -> set[str]:
    out: set[str] = set()
    for word in re.findall(r"\w+", s.casefold()):
        padded = f"  {word} "  # pg_trgm pads each word: two spaces before, one after
        out |= {padded[i : i + 3] for i in range(len(padded) - 2)}
    return out


def similarity(a: str, b: str) -> float:
    """pg_trgm-style trigram similarity, 0..1."""
    ta, tb = _trigrams(a), _trigrams(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def best_match(name: str, candidates: list[str], threshold: float = 0.75) -> str | None:
    # ponytail: linear scan over the top 200 correspondents; pg_trgm index if that ever grows.
    scored = [(similarity(name, c), c) for c in candidates]
    best = max(scored, default=(0.0, None))
    return best[1] if best[0] >= threshold else None
