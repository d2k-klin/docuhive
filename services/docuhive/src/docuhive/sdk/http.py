"""HTTP for plugins: reaches only the hosts the plugin declared under `capabilities: network`."""

import fnmatch
import ipaddress
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from .registry import Registry


class HostNotAllowed(PermissionError):
    pass


# What a request raises when the other side cannot be reached; catch it as `http.HTTPError`.
HTTPError = httpx.HTTPError


def allowed(host: str, patterns: list[str]) -> bool:
    host = host.lower().rstrip(".")
    for pattern in patterns:
        pattern = pattern.lower().split(":")[0]
        if host == pattern or (pattern.startswith("*.") and fnmatch.fnmatch(host, pattern)):
            try:
                ip = ipaddress.ip_address(host)
            except ValueError:
                return True
            # An address inside the home network must be named exactly, never by wildcard.
            return host == pattern or ip.is_global
    return False


def _resolve(registry: "Registry", pattern: str) -> str:
    """`setting:url` is the host of the address in that setting, matched exactly; empty (so
    nothing matches) until an administrator enters it."""
    if not pattern.startswith("setting:"):
        return pattern
    from urllib.parse import urlsplit

    value = str(registry.settings.get(pattern.removeprefix("setting:")) or "")
    return urlsplit(value if "://" in value else f"http://{value}").hostname or ""


def client(registry: "Registry", **kwargs: Any) -> httpx.Client:
    """An httpx.Client that refuses every other host, also after a redirect.
    ponytail: checks the name, not where it resolves to; a declared name pointing at a private
    address is reachable. Pin resolution in a custom transport if plugins ever come from strangers.
    """
    patterns = [_resolve(registry, h) for h in registry.manifest.hosts()]

    def check(request: httpx.Request) -> None:
        if not allowed(request.url.host, patterns):
            raise HostNotAllowed(
                f"The plugin '{registry.id}' may not reach {request.url.host}; declare it under "
                "capabilities: network in plugin.yaml"
            )

    kwargs.setdefault("timeout", 20)
    return httpx.Client(event_hooks={"request": [check]}, trust_env=False, **kwargs)
