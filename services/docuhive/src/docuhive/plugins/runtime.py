"""Start the enabled plugins in this process, each all-or-nothing, none able to stop the rest."""

import importlib
import logging
import sys
import types
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.exc import SQLAlchemyError

from docuhive.contracts import CurrentUser, SetupCheck
from docuhive.sdk.registry import Registry

from . import discovery, state
from .manifest import Manifest

log = logging.getLogger(__name__)
Process = Literal["api", "worker", "cli"]


@dataclass
class Loaded:
    manifest: Manifest
    registry: Registry


LOADED: dict[str, Loaded] = {}
# Hooks later parts of the platform add: called with (registry, process) after setup() and
# before anything is live; they raise to refuse a plugin and install in their commit step.
PREPARE: list[Callable[[Registry, Process], None]] = []
COMMIT: list[Callable[[Registry, Process], None]] = []
ROLLBACK: list[Callable[[Registry], None]] = []


def friendly(error: BaseException) -> str:
    text = str(error).strip() or type(error).__name__
    return text if len(text) <= 300 else text[:297] + "…"


def _module_name(plugin_id: str) -> str:
    return "docuhive_plugin_" + plugin_id.replace("-", "_")


def _import(found: discovery.Found) -> types.ModuleType | None:
    """Load plugin.py as `<package>.plugin` so a plugin can import its own modules relatively.
    The folder is never put on sys.path, so plugins cannot shadow each other or the core."""
    if not (found.path / "plugin.py").is_file():
        return None
    name = _module_name(found.id)
    package = types.ModuleType(name)
    package.__path__ = [str(found.path)]
    package.__package__ = name
    sys.modules[name] = package
    try:
        return importlib.import_module(f"{name}.plugin")
    except BaseException:
        _unimport(found.id)
        raise


def _unimport(plugin_id: str) -> None:
    name = _module_name(plugin_id)
    for key in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        del sys.modules[key]


def load_one(found: discovery.Found, process: Process) -> Loaded:
    """Run one plugin's setup; raises without leaving anything registered."""
    from . import install  # noqa: F401

    assert found.manifest is not None
    registry = Registry(found.manifest, found.path)
    try:
        module = _import(found)
        setup = getattr(module, "setup", None) if module else None
        if module is not None and not callable(setup):
            raise TypeError("plugin.py must define setup(registry)")
        if setup is not None:
            setup(registry)
        for prepare in PREPARE:
            prepare(registry, process)
    except BaseException:
        for rollback in ROLLBACK:
            rollback(registry)
        _unimport(found.id)
        raise
    for commit in COMMIT:
        commit(registry, process)
    return Loaded(found.manifest, registry)


def start(process: Process) -> None:
    """Load every enabled, compatible plugin. Safe to call again (does nothing the second time)."""
    from . import install  # noqa: F401 - registers what plugins add when they start

    if LOADED:
        return
    installed = discovery.discover()
    if not installed:
        return  # nothing to load: do not touch the database
    try:
        enabled = {k: v for k, v in state.states().items() if v.enabled}
    except SQLAlchemyError:
        log.warning("Plugins not started: the plugins table is not available (run db upgrade)")
        return
    for found in installed:
        row = enabled.get(found.id)
        if row is None:
            continue
        if not found.loadable:
            state.record(found.id, error="; ".join(found.problems))
            continue
        assert found.manifest is not None
        missing = set(found.manifest.capability_names()) - set(row.granted)
        if missing:
            state.record(
                found.id,
                error="Needs your approval: this version asks for " + ", ".join(sorted(missing)),
            )
            continue
        absent = [d for d in found.manifest.depends_on if d not in LOADED]
        if absent:
            state.record(found.id, error=f"Needs the plugin '{absent[0]}' switched on")
            continue
        try:
            LOADED[found.id] = load_one(found, process)
        except Exception as error:
            log.exception("Plugin %s could not start", found.id)
            state.record(found.id, error=f"Could not start: {friendly(error)}")
            continue
        state.record(found.id, version=found.manifest.version, error=None)
        log.info("Plugin %s %s started", found.id, found.manifest.version)


def reset() -> None:
    """Tests only: forget what this process loaded."""
    for plugin_id in list(LOADED):
        for rollback in ROLLBACK:
            rollback(LOADED[plugin_id].registry)
        _unimport(plugin_id)
    LOADED.clear()


def setup_checks(user: CurrentUser) -> list[SetupCheck]:
    out: list[SetupCheck] = []
    for plugin_id, loaded in LOADED.items():
        manifest = loaded.manifest
        for spec in manifest.setup_checks:
            done = state.is_set(plugin_id, spec.when_missing)
            out.append(
                SetupCheck(
                    id=f"plugin.{plugin_id}.{spec.id}",
                    area="plugins",
                    title=spec.title,
                    status="ok" if done else ("todo" if spec.required else "optional"),
                    message=f"{manifest.name}: " + ("done." if done else spec.message),
                    action_label=None if done else "Open settings",
                    action_href=None if done else f"/settings/plugins#{plugin_id}",
                    required=spec.required,
                )
            )
        for fn in loaded.registry.setup_checks:
            try:
                result = fn(user)
            except Exception as error:
                log.warning("Setup check of plugin %s failed: %s", plugin_id, error)
                continue
            out += [r for r in (result if isinstance(result, list) else [result]) if r]
    return out


def notify_channels() -> dict[str, Callable]:
    return {
        fn.kind: fn  # type: ignore[attr-defined]
        for loaded in LOADED.values()
        for fn in loaded.registry.notify_channels
    }


def restore_after_rebuild() -> list[str]:
    """After `vault rebuild`: start the enabled plugins (which recreates their tables), put back
    their newest snapshot, and let them refill what they derive from documents."""
    from . import data

    start("cli")
    report = []
    for plugin_id, loaded in LOADED.items():
        if loaded.manifest.snapshot:
            rows = data.restore(plugin_id)
            report.append(f"{plugin_id}: {rows} rows from its latest snapshot")
        for fn in loaded.registry.rebuilders:
            fn()
            report.append(f"{plugin_id}: rebuilt from documents")
    return report
