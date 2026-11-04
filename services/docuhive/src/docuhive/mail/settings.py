"""Mail connector settings (env prefix DOCUHIVE_MAIL_)."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MailSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCUHIVE_MAIL_", env_file=".env", extra="ignore")

    token_key: SecretStr | None = None  # Fernet key; `docuhive mail gen-key` prints one
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    ms_client_id: str | None = None
    ms_client_secret: SecretStr | None = None
    ms_tenant: str = "common"  # "consumers" = personal Microsoft accounts only
    sync_every_min: int = Field(default=15, ge=1)
    overlap_min: int = Field(default=120, ge=0)
    max_attachment_mb: int = Field(default=50, ge=1)


@lru_cache
def get_mail_settings() -> MailSettings:
    return MailSettings()


class MissingKey(Exception):
    pass


def fernet(key: SecretStr | None = None):  # type: ignore[no-untyped-def]
    """Fernet for credentials at rest. DOCUHIVE_MAIL_TOKEN_KEY, required once secrets exist."""
    from cryptography.fernet import Fernet

    key = key or get_mail_settings().token_key
    if key is None:
        raise MissingKey("Set DOCUHIVE_MAIL_TOKEN_KEY (run `docuhive mail gen-key`)")
    return Fernet(key.get_secret_value().encode())
