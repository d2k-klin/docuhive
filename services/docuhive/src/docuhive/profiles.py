"""Identities ("profiles"): the person, business or household the archive writes and sends as.

Same visibility as documents: your own, and the ones shared with the household. A profile is
not a tenant: documents are not split by profile; plugins bind their own records to one.
Checks are offline only (IBAN checksum, VAT id format and the German check digit).
"""

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select

from docuhive import db
from docuhive.contracts import CurrentUser
from docuhive.db.models import Profile


class NotFound(LookupError):
    pass


def iban_ok(iban: str) -> bool:
    value = re.sub(r"\s+", "", iban).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", value):
        return False
    digits = "".join(str(int(c, 36)) for c in value[4:] + value[:4])
    return int(digits) % 97 == 1


def vat_id_ok(vat_id: str) -> bool:
    value = re.sub(r"[\s.-]+", "", vat_id).upper()
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{2,12}", value):
        return False
    if value.startswith("DE"):  # ISO 7064 MOD 11,10 over the nine digits
        if not re.fullmatch(r"DE\d{9}", value):
            return False
        product = 10
        for digit in value[2:10]:
            total = (int(digit) + product) % 10 or 10
            product = (2 * total) % 11
        return (11 - product) % 10 == int(value[10])
    return True


EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class Address(BaseModel):
    street: str = ""
    postcode: str = ""
    city: str = ""
    country: str = "DE"


class Bank(BaseModel):
    holder: str = ""
    iban: str = ""
    bic: str = ""
    name: str = ""

    @field_validator("iban")
    @classmethod
    def checksum(cls, value: str) -> str:
        if value and not iban_ok(value):
            raise ValueError("This IBAN's check digits are wrong; check for a typo")
        return re.sub(r"\s+", "", value).upper()


class Smtp(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(default=587, ge=1, le=65535)
    username: str = ""
    from_address: str = Field(pattern=EMAIL)


class SmtpIn(Smtp):
    password: str | None = None  # write only: empty keeps the stored one; never returned


class ProfileIn(BaseModel):
    kind: Literal["person", "business", "household"]
    name: str = Field(min_length=1, max_length=200)
    shared: bool = False
    legal_form: str | None = None
    address: Address = Address()
    email: str | None = Field(default=None, pattern=EMAIL)
    phone: str | None = None
    website: str | None = None
    tax_number: str | None = None
    vat_id: str | None = None
    tax_office: str | None = None
    bank: Bank = Bank()
    logo_document_id: str | None = None
    smtp: SmtpIn | None = None

    @field_validator("vat_id")
    @classmethod
    def vat(cls, value: str | None) -> str | None:
        if value and not vat_id_ok(value):
            raise ValueError("This is not a valid VAT id (for Germany: DE and nine digits)")
        return re.sub(r"[\s.-]+", "", value).upper() if value else None


class ProfileOut(ProfileIn):
    smtp: Smtp | None = None  # type: ignore[assignment]
    id: int
    owner_id: int
    has_smtp_password: bool = False


def visible(user: CurrentUser) -> Any:
    return or_(Profile.owner_id == user.id, Profile.shared.is_(True))


def _out(row: Profile) -> ProfileOut:
    smtp = dict(row.smtp) if row.smtp else None
    return ProfileOut(
        id=row.id,
        owner_id=row.owner_id,
        kind=row.kind,  # type: ignore[arg-type]
        name=row.name,
        shared=row.shared,
        legal_form=row.legal_form,
        address=Address(**row.address),
        email=row.email,
        phone=row.phone,
        website=row.website,
        tax_number=row.tax_number,
        vat_id=row.vat_id,
        tax_office=row.tax_office,
        bank=Bank.model_construct(**row.bank),
        logo_document_id=row.logo_document_id,
        smtp=Smtp.model_construct(**smtp) if smtp else None,
        has_smtp_password=row.smtp_secret is not None,
    )


def list_for(user: CurrentUser) -> list[ProfileOut]:
    with db.session() as s:
        return [
            _out(r) for r in s.scalars(select(Profile).where(visible(user)).order_by(Profile.name))
        ]


def get(user: CurrentUser, profile_id: int) -> ProfileOut:
    with db.session() as s:
        row = s.scalar(select(Profile).where(Profile.id == profile_id, visible(user)))
        if row is None:
            raise NotFound(profile_id)
        return _out(row)


def save(user: CurrentUser, data: ProfileIn, profile_id: int | None = None) -> ProfileOut:
    """Create, or change one of your own. A shared profile is changed only by its owner."""
    from docuhive.mail.settings import fernet

    values = data.model_dump(exclude={"smtp"}, mode="json")
    with db.session() as s:
        found = (
            Profile(owner_id=user.id)
            if profile_id is None
            else s.scalar(
                select(Profile).where(Profile.id == profile_id, Profile.owner_id == user.id)
            )
        )
        if found is None:
            raise NotFound(profile_id)
        row = found
        s.add(row)
        for key, value in values.items():
            setattr(row, key, value)
        if data.smtp is None:
            row.smtp, row.smtp_secret = None, None
        else:
            row.smtp = data.smtp.model_dump(exclude={"password"}, mode="json")
            if data.smtp.password:
                row.smtp_secret = fernet().encrypt(data.smtp.password.encode())
        row.updated_at = datetime.now(UTC)
        s.flush()
        return _out(row)


def delete(user: CurrentUser, profile_id: int) -> None:
    with db.session() as s:
        row = s.scalar(select(Profile).where(Profile.id == profile_id, Profile.owner_id == user.id))
        if row is None:
            raise NotFound(profile_id)
        s.delete(row)


def smtp_password(profile_id: int) -> str | None:
    """Only the mail sender calls this; no API returns it."""
    from docuhive.mail.settings import fernet

    with db.session() as s:
        secret = s.scalar(select(Profile.smtp_secret).where(Profile.id == profile_id))
    return fernet().decrypt(secret).decode() if secret else None
