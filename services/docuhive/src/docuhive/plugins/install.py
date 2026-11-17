"""Installs what a plugin registered when it starts, and removes it again.

Checks that can refuse a plugin run first (prepare); nothing becomes live before every check
passed (commit). Rollback undoes a commit, for tests and for switching off within a process.
"""

import inspect
import typing
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from docuhive import config, events, jobs, taxonomy
from docuhive.sdk.registry import Registry

from . import data, runtime


class Refused(RuntimeError):
    pass


# "<plugin id>.<function name>" -> function, for plugins that depend on another.
SERVICES: dict[str, Callable] = {}


def _contributed_ids(exclude: str) -> dict[str, str]:
    """Category and document type ids other running plugins created, with their plugin. Adding
    facts to a built-in type (invoice, receipt) is not creating it: any plugin may do that."""
    core = taxonomy.defaults()
    builtin = {c.id for c in core.categories} | {t.id for t in core.document_types}
    out: dict[str, str] = {}
    for plugin_id, add in taxonomy.CONTRIBUTIONS:
        if plugin_id == exclude:
            continue
        for item_id in [c.id for c in add.categories] + [t.id for t in add.document_types]:
            if item_id not in builtin:
                out[item_id] = plugin_id
    return out


def prepare(registry: Registry, process: str) -> None:
    manifest = registry.manifest
    taken = _contributed_ids(registry.id)
    add = manifest.taxonomy
    for item_id in [c.id for c in add.categories] + [t.id for t in add.document_types]:
        if item_id in taken:
            raise Refused(
                f"'{item_id}' is already added by the plugin '{taken[item_id]}'; "
                "rename it in plugin.yaml"
            )
    for task in manifest.ai_tasks:
        if registry.path is None or not (
            (registry.path / "prompts" / f"{task.prompt}.md").is_file()
            or (registry.path / "custom" / "prompts" / f"{task.prompt}.md").is_file()
        ):
            raise Refused(f"ai_tasks: prompts/{task.prompt}.md is missing")
    from . import pages

    found, problems = pages.load(registry.path)
    if problems:
        raise Refused(problems[0])
    for name, page in found.items():
        sources, actions = pages.names(page)
        where = f"pages/{name}.yaml"
        if missing := sources - set(registry.data_sources):
            raise Refused(f"{where} uses the data source '{min(missing)}', not in plugin.py")
        if missing := actions - set(registry.actions):
            raise Refused(f"{where} uses the action '{min(missing)}', not in plugin.py")
        for block in page.blocks:
            # Sending: the page shows a preview first, so only forms and action blocks may send.
            if (form := getattr(block, "action", None)) and registry.actions[form][1]["outgoing"]:
                if not registry.actions[form][1]["preview"]:
                    raise Refused(f"{where}: '{form}' sends something out: give it a preview")
            for button in getattr(block, "row_actions", []):
                if registry.actions[button.action][1]["outgoing"]:
                    raise Refused(
                        f"{where}: '{button.action}' sends something out: put it in a form or "
                        "an actions block, where its preview is shown, not on a table row"
                    )
            for button in [*getattr(block, "actions", []), *getattr(block, "row_actions", [])]:
                flags = registry.actions[button.action][1]
                if flags["outgoing"] and not flags["preview"]:
                    raise Refused(
                        f"{where}: '{button.action}' sends something out: give it a preview"
                    )
                if flags["destructive"] and not button.confirm:
                    raise Refused(
                        f"{where}: '{button.action}' needs confirm: what the person agrees to"
                    )
    registry.pages = found
    if data.migrations(registry.path):
        if not manifest.snapshot and not registry.rebuilders:
            raise Refused(
                "it has tables but no way to get them back after a restore: set snapshot: true "
                "in plugin.yaml or register @registry.rebuild"
            )
        data.migrate(registry.id, registry.path)


def _tool(registry: Registry, fn: Callable, user: Any, scope: Any, masked: set[str]) -> Callable:
    """The plugin's function as an Ask tool: user and scope are filled in, never by the model,
    and documents a cloud model may not see are left out or the result is withheld."""
    signature = inspect.signature(fn)
    hidden = {"user", "scope", "exclude_ids"}
    params = [p for name, p in signature.parameters.items() if name not in hidden]
    hints = typing.get_type_hints(fn)

    def call(**kwargs: Any) -> dict:
        extra: dict[str, Any] = {}
        if "scope" in signature.parameters:
            extra["scope"] = scope
        if "exclude_ids" in signature.parameters:
            extra["exclude_ids"] = set(masked)
        result = fn(user, **extra, **kwargs)
        if not isinstance(result, dict):
            result = {"result": result}
        withheld = set(result.get("documents") or []) & masked
        if withheld:
            return {
                "withheld": len(withheld),
                "summary": f"{len(withheld)} restricted documents not included",
            }
        result.setdefault("summary", f"{len(result.get('documents') or [])} documents")
        return result

    call.__signature__ = signature.replace(parameters=params)  # type: ignore[attr-defined]
    call.__annotations__ = {k: v for k, v in hints.items() if k not in hidden}
    call.__name__ = fn.__name__
    call.__doc__ = fn.__doc__
    return call


def _tool_factory(registry: Registry) -> Callable:
    def build(user: Any, scope: Any, route: Any, masked: set[str]) -> list:
        from strands import tool

        return [
            tool(
                name=f"{registry.id.replace('-', '_')}__{fn.__name__}",
                description=(fn.__doc__ or fn.__name__).strip(),
            )(_tool(registry, fn, user, scope, masked))
            for fn, _ in registry.tools
        ]

    build.plugin = registry.id  # type: ignore[attr-defined]
    return build


def commit(registry: Registry, process: str) -> None:
    manifest = registry.manifest
    add = manifest.taxonomy
    if add.categories or add.document_types or add.tags:
        taxonomy.CONTRIBUTIONS.append((registry.id, add))
    if registry.path is not None:
        config.PLUGIN_PROMPTS[registry.id] = registry.path
        config.prompt.cache_clear()
    from docuhive.ai import router

    for task in manifest.ai_tasks:
        router.LIKE[f"{registry.id}.{task.prompt}"] = task.like
    for event, fn, queue in registry.listeners:
        subscriber = f"plugin:{registry.id}:{fn.__name__}"
        registry.installed.append(events.subscribe(event, subscriber, fn, queue=queue))
    for name, fn, queue, timeout in registry.jobs:
        kind = registry.job_kind(name)
        jobs.handler(kind, queue=queue, timeout_s=timeout)(fn)
        registry.installed.append(kind)
    for name, interval in registry.periodics:
        kind = registry.job_kind(name)
        jobs.PERIODICS[kind] = jobs.Periodic(interval, jobs.HANDLERS[kind].queue)
    if manifest.snapshot:
        kind = registry.job_kind("snapshot")
        jobs.handler(kind)(lambda payload, ctx: data.snapshot(registry.id))
        jobs.PERIODICS[kind] = jobs.Periodic(timedelta(days=1), "default")
        registry.installed.append(kind)
    for name, fn in registry.services.items():
        SERVICES[f"{registry.id}.{name}"] = fn
    if registry.tools:
        try:
            from docuhive.agents import tools
        except ImportError:  # core-only install: no Ask
            return
        tools.EXTRA.append(_tool_factory(registry))


def rollback(registry: Registry) -> None:
    taxonomy.CONTRIBUTIONS[:] = [c for c in taxonomy.CONTRIBUTIONS if c[0] != registry.id]
    if config.PLUGIN_PROMPTS.pop(registry.id, None) is not None:
        config.prompt.cache_clear()
    from docuhive.ai import router

    for task in list(router.LIKE):
        if task.startswith(f"{registry.id}."):
            del router.LIKE[task]
    for kind in registry.installed:
        events.unsubscribe(kind)
        jobs.HANDLERS.pop(kind, None)
        jobs.PERIODICS.pop(kind, None)
    for name, _ in registry.periodics:
        jobs.PERIODICS.pop(registry.job_kind(name), None)
    registry.installed.clear()
    for name in registry.services:
        SERVICES.pop(f"{registry.id}.{name}", None)
    try:
        from docuhive.agents import tools
    except ImportError:
        return
    tools.EXTRA[:] = [f for f in tools.EXTRA if getattr(f, "plugin", None) != registry.id]


runtime.PREPARE.append(prepare)
runtime.COMMIT.append(commit)
runtime.ROLLBACK.append(rollback)
