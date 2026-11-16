"""Which plugins are switched on, what they were allowed, and their settings."""

import base64
import hashlib
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select

from docuhive import db
from docuhive.config.settings import get_settings
from docuhive.db.models import AuditLog, PluginState, Setting

from .manifest import Manifest, SettingField


class SecretsUnavailable(RuntimeError):
    pass


def states() -> dict[str, PluginState]:
    with db.session() as s:
        rows = list(s.scalars(select(PluginState)))
        for row in rows:
            s.expunge(row)
    return {r.id: r for r in rows}


def enable(plugin_id: str, granted: list[str], actor: str) -> None:
    with db.session() as s:
        row = s.get(PluginState, plugin_id) or PluginState(id=plugin_id)
        row.enabled, row.granted = True, sorted(granted)
        row.enabled_at, row.enabled_by, row.last_error = datetime.now(UTC), actor, None
        s.add(row)
        after = {"id": plugin_id, "granted": granted}
        s.add(AuditLog(actor=actor, action="plugin.enable", after=after))


def disable(plugin_id: str, actor: str) -> None:
    with db.session() as s:
        row = s.get(PluginState, plugin_id)
        if row is not None:
            row.enabled = False
        s.add(AuditLog(actor=actor, action="plugin.disable", after={"id": plugin_id}))


def record(plugin_id: str, *, version: str | None = None, error: str | None = None) -> None:
    with db.session() as s:
        row = s.get(PluginState, plugin_id)
        if row is None:
            return
        row.last_error = error
        if version is not None:
            row.version = version


def forget(plugin_id: str, actor: str) -> None:
    with db.session() as s:
        s.execute(delete(Setting).where(Setting.key.like(f"plugin:{plugin_id}:%")))
        s.execute(delete(PluginState).where(PluginState.id == plugin_id))
        s.add(AuditLog(actor=actor, action="plugin.purge", after={"id": plugin_id}))


# Settings ---------------------------------------------------------------------------------


def _fernet() -> Fernet:
    secret = get_settings().secret_key
    if secret is None:
        raise SecretsUnavailable(
            "Set DOCUHIVE_SECRET_KEY before saving secret plugin settings (installation guide)."
        )
    digest = hashlib.sha256(b"docuhive-plugin-secrets:" + secret.get_secret_value().encode())
    return Fernet(base64.urlsafe_b64encode(digest.digest()))


def _key(plugin_id: str, key: str) -> str:
    return f"plugin:{plugin_id}:{key}"


def get_value(plugin_id: str, field: SettingField) -> Any:
    with db.session() as s:
        stored = s.scalar(select(Setting.value).where(Setting.key == _key(plugin_id, field.key)))
    if stored is None:
        return field.default
    if field.type == "secret":
        try:
            return _fernet().decrypt(stored["enc"].encode()).decode()
        except (InvalidToken, KeyError, TypeError):
            return None
    return stored


def is_set(plugin_id: str, key: str) -> bool:
    with db.session() as s:
        return (
            s.scalar(select(Setting.value).where(Setting.key == _key(plugin_id, key))) is not None
        )


def _coerce(field: SettingField, value: Any) -> Any:
    if value in (None, ""):
        return None
    if field.type == "boolean":
        if not isinstance(value, bool):
            raise ValueError("Choose yes or no")
        return value
    if field.type == "number":
        try:
            return float(value) if "." in str(value) else int(value)
        except ValueError:
            raise ValueError("Enter a number") from None
    if field.type == "date":
        datetime.strptime(str(value), "%Y-%m-%d")
        return str(value)
    if field.type == "choice" and value not in field.options:
        raise ValueError(f"Choose one of: {', '.join(field.options)}")
    if not isinstance(value, str | int):
        raise ValueError("Enter text")
    return str(value) if field.type != "profile" else int(value)


def save(manifest: Manifest, values: dict[str, Any], actor: str) -> dict[str, str]:
    """Validate and store; returns {key: message} for fields that were refused."""
    errors: dict[str, str] = {}
    fields = {f.key: f for f in manifest.settings}
    clean: dict[str, Any] = {}
    for key, value in values.items():
        field = fields.get(key)
        if field is None:
            errors[key] = "Not a setting of this plugin"
            continue
        if field.type == "secret" and value == "":
            continue  # an empty secret field means "keep the saved one"
        try:
            clean[key] = _coerce(field, value)
        except ValueError as error:
            errors[key] = str(error)
    for key, field in fields.items():
        missing = clean[key] is None if key in clean else not is_set(manifest.id, key)
        if field.required and missing:
            errors.setdefault(key, "Required")
    if errors:
        return errors
    with db.session() as s:
        for key, value in clean.items():
            row_key = _key(manifest.id, key)
            if value is None:
                s.execute(delete(Setting).where(Setting.key == row_key))
                continue
            if fields[key].type == "secret":
                value = {"enc": _fernet().encrypt(str(value).encode()).decode()}
            s.merge(Setting(key=row_key, value=value))
        s.add(
            AuditLog(
                actor=actor,
                action="plugin.settings",
                after={"id": manifest.id, "keys": sorted(clean)},  # never the values
            )
        )
    return {}


def public_values(manifest: Manifest) -> dict[str, Any]:
    """Values for the settings form: secrets only say whether one is saved."""
    out: dict[str, Any] = {}
    for field in manifest.settings:
        if field.type == "secret":
            out[field.key] = {"saved": is_set(manifest.id, field.key)}
        else:
            out[field.key] = get_value(manifest.id, field)
    return out
