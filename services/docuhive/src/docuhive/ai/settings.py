"""AI provider settings (env prefix DOCUHIVE_AI_). Secrets come from env, never from YAML."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AISettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCUHIVE_AI_", env_file=".env", extra="ignore")

    enabled: bool = True
    ollama_host: str = "http://localhost:11434"
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    aws_profile: str | None = None
    aws_region: str | None = None
    # Fernet key for notification channel configs; falls back to DOCUHIVE_MAIL_TOKEN_KEY.
    notify_key: SecretStr | None = None
    tz: str = "Europe/Berlin"  # reminders are sent from 07:00 in this zone


@lru_cache
def get_ai_settings() -> AISettings:
    return AISettings()
