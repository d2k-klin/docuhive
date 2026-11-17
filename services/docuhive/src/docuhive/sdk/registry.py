"""What a plugin's `setup(registry)` registers. Nothing is live until the whole setup succeeded."""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from docuhive.plugins.manifest import Manifest


class CapabilityMissing(PermissionError):
    def __init__(self, plugin_id: str, capability: str) -> None:
        super().__init__(
            f"The plugin '{plugin_id}' needs the capability '{capability}' in its plugin.yaml"
        )


class Settings:
    def __init__(self, manifest: "Manifest") -> None:
        self._manifest = manifest

    def get(self, key: str) -> Any:
        from docuhive.plugins import state

        field = next((f for f in self._manifest.settings if f.key == key), None)
        if field is None:
            raise KeyError(f"'{key}' is not declared under settings in plugin.yaml")
        if field.type == "secret" and "secrets" not in self._manifest.capability_names():
            raise CapabilityMissing(self._manifest.id, "secrets")
        return state.get_value(self._manifest.id, field)


class Registry:
    def __init__(self, manifest: "Manifest", path: Path) -> None:
        self.id, self.path, self.manifest = manifest.id, path, manifest
        self.settings = Settings(manifest)
        self.log = logging.getLogger(f"docuhive.plugin.{manifest.id}")
        self.setup_checks: list[Callable] = []
        self.notify_channels: list[Callable] = []
        self.listeners: list[tuple[str, Callable, str]] = []  # (event, fn, queue)
        self.jobs: list[tuple[str, Callable, str, int]] = []  # (name, fn, queue, timeout)
        self.periodics: list[tuple[str, timedelta]] = []
        self.tools: list[tuple[Callable, bool]] = []  # (fn, aggregates_only)
        self.rebuilders: list[Callable] = []
        self.services: dict[str, Callable] = {}
        self.data_sources: dict[str, Callable] = {}
        self.actions: dict[str, tuple[Callable, dict]] = {}
        self.pages: dict[str, Any] = {}  # filled from pages/*.yaml when the plugin starts
        self.installed: list[str] = []  # job kinds installed at start, for switching off

    # Files, with the user's replacements in custom/ first -------------------------------
    def rules(self, name: str) -> Any:
        from docuhive.plugins import files

        return files.rules(self.path, name)

    def template(self, name: str) -> str:
        from docuhive.plugins import files

        return files.read_text(self.path, "templates", name)

    def prompt(self, name: str) -> str:
        from docuhive.plugins import files

        return files.read_text(self.path, "prompts", name)

    # Registrations ------------------------------------------------------------------------
    def setup_check(self, fn: Callable) -> Callable:
        """`fn(user) -> SetupCheck | list[SetupCheck] | None` joins the dashboard's setup card."""
        self.setup_checks.append(fn)
        return fn

    def notify_channel(self, kind: str) -> Callable[[Callable], Callable]:
        """`fn(config: dict, notification)` delivers a notification over a channel kind."""

        def register(fn: Callable) -> Callable:
            fn.kind = kind  # type: ignore[attr-defined]
            self.notify_channels.append(fn)
            return fn

        return register

    def on(self, event: str, *, queue: str = "default") -> Callable[[Callable], Callable]:
        """`fn(event)` runs as its own job whenever the event happens. Events: document.stored,
        document.classified, document.changed, document.trashed, document.restored,
        document.quarantined, review.accepted, and `<plugin id>.<name>` from other plugins."""

        def register(fn: Callable) -> Callable:
            self.listeners.append((event, fn, queue))
            return fn

        return register

    def job(
        self, name: str, *, queue: str = "default", timeout_s: int = 600
    ) -> Callable[[Callable], Callable]:
        """`fn(payload, ctx)` runs in the background when enqueued with `registry.enqueue`."""

        def register(fn: Callable) -> Callable:
            self.jobs.append((name, fn, queue, timeout_s))
            return fn

        return register

    def every(self, interval: timedelta, name: str) -> Callable[[Callable], Callable]:
        """`fn(payload, ctx)` runs on a schedule, for example every day."""

        def register(fn: Callable) -> Callable:
            self.jobs.append((name, fn, "default", 600))
            self.periodics.append((name, interval))
            return fn

        return register

    def job_kind(self, name: str) -> str:
        return f"plugin:{self.id}:{name}"

    def enqueue(self, name: str, payload: dict, *, dedupe_key: str | None = None) -> int:
        from docuhive import jobs

        queue = next((q for n, _, q, _ in self.jobs if n == name), "default")
        kind = self.job_kind(name)
        return jobs.enqueue(
            kind, payload, queue=queue, dedupe_key=dedupe_key and f"{kind}:{dedupe_key}"
        )

    def emit(self, name: str, payload: dict, *, key: str) -> None:
        """Tell other plugins something happened: they listen to `<this plugin's id>.<name>`."""
        from docuhive import events

        events.emit(f"{self.id}.{name}", payload, key=key)

    def tool(self, fn: Callable | None = None, *, aggregates_only: bool = False) -> Any:
        """`fn(user, …) -> dict` becomes a tool for Ask. The result must list the documents it
        used under "documents"; a function that accepts `exclude_ids` is called without the
        documents a cloud model may not see."""

        def register(f: Callable) -> Callable:
            self.tools.append((f, aggregates_only))
            return f

        return register(fn) if fn is not None else register

    def data(self, name: str) -> Callable[[Callable], Callable]:
        """`fn(user, params) -> list[dict] | dict` feeds a page block's `source: <name>`. It must
        only return what this user may see."""

        def register(fn: Callable) -> Callable:
            self.data_sources[name] = fn
            return fn

        return register

    def action(
        self,
        name: str,
        *,
        outgoing: bool = False,
        destructive: bool = False,
        preview: Callable | None = None,
    ) -> Callable[[Callable], Callable]:
        """`fn(user, params) -> str | Result` runs when a person presses a button or sends a form.
        `destructive` actions ask the person to confirm first. `outgoing` actions (they send
        something out of the house) need `preview(user, params) -> dict` with `to`, `subject`,
        `body` and `attachments`: the page shows exactly that before anything is sent."""

        def register(fn: Callable) -> Callable:
            self.actions[name] = (
                fn,
                {"outgoing": outgoing, "destructive": destructive, "preview": preview},
            )
            return fn

        return register

    def service(self, fn: Callable) -> Callable:
        """Offer a function to plugins that depend on this one: services.get("<id>.<name>")."""
        self.services[fn.__name__] = fn
        return fn

    def rebuild(self, fn: Callable) -> Callable:
        """`fn()` refills the plugin's tables from documents after the database was restored."""
        self.rebuilders.append(fn)
        return fn

    @property
    def db(self) -> "PluginDb":
        return PluginDb(self.id)

    def require(self, capability: str) -> None:
        if capability not in self.manifest.capability_names():
            raise CapabilityMissing(self.id, capability)


class PluginDb:
    """The plugin's own tables, in a database schema of its own."""

    def __init__(self, plugin_id: str) -> None:
        self.plugin_id = plugin_id

    @property
    def schema(self) -> str:
        from docuhive.plugins.data import schema

        return schema(self.plugin_id)

    @contextmanager
    def session(self) -> Iterator[Any]:
        """A transaction in which unqualified table names are the plugin's own."""
        from sqlalchemy import text

        from docuhive import db

        with db.session() as s:
            s.execute(text(f'SET LOCAL search_path TO "{self.schema}", public'))
            yield s
