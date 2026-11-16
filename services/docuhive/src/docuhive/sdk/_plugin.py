"""Which plugin is calling: plugin code runs as the module `docuhive_plugin_<id>.…`."""

import inspect
from contextvars import ContextVar

from .registry import Registry

# Set only while a page action runs for a signed-in person who pressed its button: what goes out
# of the house (mail, a guest link) needs that person, never a job or an event handler.
INTERACTIVE: ContextVar[bool] = ContextVar("docuhive_plugin_interactive", default=False)


class NotInteractive(PermissionError):
    def __init__(self) -> None:
        super().__init__("This can only happen when a person presses a button on a plugin page")


def require_interactive() -> None:
    if not INTERACTIVE.get():
        raise NotInteractive()


def current() -> Registry:
    from docuhive.plugins import runtime

    frame = inspect.currentframe()
    while frame is not None:
        name = frame.f_globals.get("__name__", "")
        if name.startswith("docuhive_plugin_"):
            module = name.split(".")[0].removeprefix("docuhive_plugin_")
            for plugin_id, loaded in runtime.LOADED.items():
                if plugin_id.replace("-", "_") == module:
                    return loaded.registry
        frame = frame.f_back
    raise RuntimeError("docuhive.sdk functions can only be called from a running plugin")
