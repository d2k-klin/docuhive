"""Identity checks that run offline."""

from docuhive.profiles import iban_ok, vat_id_ok


def de_vat(eight: str) -> str:
    """A made-up German VAT id with a correct check digit (ISO 7064 MOD 11,10). The first eight
    of the nine digits go in; the ninth is the check digit."""
    product = 10
    for digit in eight:
        total = (int(digit) + product) % 10 or 10
        product = (2 * total) % 11
    return f"DE{eight}{(11 - product) % 10}"


def test_iban_checksum():
    assert iban_ok("DE89 3704 0044 0532 0130 00")  # the standard example IBAN
    assert not iban_ok("DE89 3704 0044 0532 0130 01")
    assert not iban_ok("not an iban")


def test_vat_ids():
    good = de_vat("12345678")
    assert vat_id_ok(good) and vat_id_ok(good.lower())
    wrong = good[:-1] + str((int(good[-1]) + 1) % 10)
    assert not vat_id_ok(wrong)
    assert not vat_id_ok("DE12345")
    assert vat_id_ok("ATU12345678")  # other countries: format only
