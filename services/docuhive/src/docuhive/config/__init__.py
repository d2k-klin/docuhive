"""Public configuration contract: defaults, private overlays and plugin hooks."""

import logging
from collections.abc import Callable
from copy import deepcopy
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any

import yaml

from .settings import get_settings

log = logging.getLogger(__name__)


def _within(root: Path, *parts: str) -> Path:
    root = root.resolve()
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Configuration paths must stay inside their configured directory")
    return path


def overlay_path(*parts: str) -> Path | None:
    root = get_settings().overlay_dir
    if root is None:
        return None
    path = _within(root, *parts)
    return path if path.exists() else None


def _mapping(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Configuration must be a mapping: {path.name}")
    return data


def _merge(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


@lru_cache
def _load_yaml(name: str) -> dict:
    base = _mapping(_within(get_settings().defaults_dir, name))
    return _merge(base, _mapping(overlay_path(name)))


def default_yaml(name: str) -> dict:
    """The shipped default alone, without the overlay, for comparing an overlay against it."""
    return _mapping(_within(get_settings().defaults_dir, name))


def public_url() -> str:
    """The address users reach DocuHive at, without a trailing slash."""
    return get_settings().public_url.rstrip("/")


def load_yaml(name: str) -> dict:
    # Callers cannot mutate a cached configuration seen by another task.
    return deepcopy(_load_yaml(name))


@lru_cache
def prompt(name: str) -> tuple[str, str]:
    path = overlay_path("prompts", f"{name}.md")
    if path is None:
        path = _within(get_settings().defaults_dir, "prompts", f"{name}.md")
    content = path.read_text(encoding="utf-8")
    version = 1
    if content.startswith("---\n"):
        front, separator, body = content[4:].partition("\n---\n")
        if not separator:
            raise ValueError(f"Unterminated prompt front matter: {name}")
        header = yaml.safe_load(front) or {}
        if not isinstance(header, dict):
            raise ValueError(f"Prompt front matter must be a mapping: {name}")
        version = header.get("version", 1)
        content = body
    return content, f"{name}@{version}"


def plugins(hook: str) -> list[Callable]:
    hooks: list[Callable] = []
    for entry in metadata.entry_points(group="docuhive.plugins"):
        try:
            candidate = getattr(entry.load(), hook, None)
            if callable(candidate):
                hooks.append(candidate)
        except Exception:
            log.warning("Plugin %s could not be loaded", entry.name)
    return hooks


def reload() -> None:
    get_settings.cache_clear()
    _load_yaml.cache_clear()
    prompt.cache_clear()


def get_setting(key: str) -> Any:
    """Shared runtime preferences, uncached so API and worker processes agree."""
    from sqlalchemy import select

    from docuhive import db
    from docuhive.db.models import Setting

    with db.session() as session:
        return session.scalar(select(Setting.value).where(Setting.key == key))


def set_setting(key: str, value: Any) -> None:
    """Persist a JSON preference. The owning API must authorise and validate it first."""
    from sqlalchemy.dialects.postgresql import insert

    from docuhive import db
    from docuhive.db.models import Setting

    statement = insert(Setting).values(key=key, value=value)
    with db.session() as session:
        session.execute(
            statement.on_conflict_do_update(index_elements=[Setting.key], set_={"value": value})
        )
