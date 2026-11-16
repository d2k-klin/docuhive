"""Functions plugins offer each other. Declare the plugin you use under depends_on."""

from collections.abc import Callable
from typing import Any


class NotRunning(LookupError):
    pass


def get(name: str) -> Callable[..., Any]:
    """`get("bank.payments_for")`: the function, or NotRunning when that plugin is off."""
    from docuhive.plugins.install import SERVICES

    try:
        return SERVICES[name]
    except KeyError:
        raise NotRunning(
            f"{name} is not available: is the plugin '{name.split('.')[0]}' on?"
        ) from None


def available(name: str) -> bool:
    from docuhive.plugins.install import SERVICES

    return name in SERVICES
