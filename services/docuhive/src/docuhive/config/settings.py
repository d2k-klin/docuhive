"""Validated core runtime settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_source_defaults = Path(__file__).resolve().parents[5] / "config" / "defaults"
_defaults = (
    _source_defaults
    if _source_defaults.is_dir()
    else Path(__file__).resolve().parents[1] / "_defaults"
)


class CoreSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DOCUHIVE_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    env: Literal["dev", "prod", "test"] = "dev"
    database_url: str = "postgresql+psycopg://docuhive:docuhive@localhost:5432/docuhive"
    vault_dir: Path = Path("data/vault")
    staging_dir: Path = Path("data/staging")
    overlay_dir: Path | None = None
    defaults_dir: Path = _defaults
    secret_key: SecretStr | None = None
    auth_disabled: bool = False
    max_upload_mb: int = Field(default=100, ge=1, le=1024)
    ocr_languages: str = "deu+eng"
    ocr_jobs: int = Field(default=2, ge=1, le=32)
    public_url: str = "http://localhost:3000"
    gotenberg_url: str = "http://localhost:3001"
    consume_dir: Path | None = None  # unset: VAULT_DIR/consume
    consume_default_owner: str | None = None

    @field_validator("overlay_dir", "consume_dir", "consume_default_owner", mode="before")
    @classmethod
    def empty_overlay_is_unset(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("vault_dir", "staging_dir", "defaults_dir", mode="before")
    @classmethod
    def paths_are_not_empty(cls, value: object) -> object:
        if value == "":
            raise ValueError("Storage and configuration directories must not be empty")
        return value

    @model_validator(mode="after")
    def validate_security(self) -> Self:
        if self.auth_disabled and self.env != "dev":
            raise ValueError("AUTH_DISABLED is only permitted with DOCUHIVE_ENV=dev")
        if self.env == "prod":
            if not self.secret_key or len(self.secret_key.get_secret_value().encode()) < 32:
                raise ValueError("DOCUHIVE_SECRET_KEY must contain at least 32 bytes in production")
        vault, staging = self.vault_dir.resolve(), self.staging_dir.resolve()
        if vault == staging or staging.is_relative_to(vault) or vault.is_relative_to(staging):
            raise ValueError("STAGING_DIR and VAULT_DIR must be separate directories")
        return self


@lru_cache
def get_settings() -> CoreSettings:
    return CoreSettings()
