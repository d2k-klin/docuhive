"""Settings → Plugins: list, switch on and off, and each plugin's settings (administrators)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from docuhive.auth import require_admin
from docuhive.config import get_setting, set_setting
from docuhive.contracts import CurrentUser
from docuhive.plugins import discovery, runtime, state
from docuhive.plugins.manifest import CAPABILITIES, Manifest

router = APIRouter(prefix="/api/plugins", tags=["plugins"])
Admin = Annotated[CurrentUser, Depends(require_admin)]


class Capability(BaseModel):
    id: str
    label: str


class PluginOut(BaseModel):
    id: str
    name: str
    description: str
    version: str | None
    source: str
    enabled: bool
    running: bool  # loaded by this process; differs from `enabled` until a restart
    state: str  # on, off, problem, needs_approval, needs_restart
    message: str | None
    capabilities: list[Capability]
    settings: list[dict]
    values: dict[str, Any]
    # None: the plugin offers Ask nothing (or is not running); otherwise the switch's state.
    in_ask: bool | None = None


class AskIn(BaseModel):
    use: bool


NOT_IN_ASK = "plugins.not_in_ask"


class EnableIn(BaseModel):
    capabilities: list[str]


def _label(cap: str, manifest: Manifest | None = None) -> str:
    if cap.startswith("network:setting:"):
        key = cap.removeprefix("network:setting:")
        field = next((f for f in (manifest.settings if manifest else []) if f.key == key), None)
        return f"Reach the address you enter in its settings ({field.label if field else key})"
    if cap.startswith("network:"):
        return f"Reach the internet address {cap.removeprefix('network:')}"
    return CAPABILITIES.get(cap, cap)


def _out(found: discovery.Found, rows: dict) -> PluginOut:
    row = rows.get(found.id)
    enabled = bool(row and row.enabled)
    granted = set(row.granted) if row else set()
    last_error = row.last_error if row else None
    running = found.id in runtime.LOADED
    manifest = found.manifest
    caps = manifest.capability_names() if manifest else []
    if found.problems:
        status, message = "problem", "; ".join(found.problems)
    elif enabled and set(caps) - granted:
        status, message = "needs_approval", "This version asks to do more than you approved."
    elif enabled and last_error:  # it was started and failed: a restart alone will not help
        status, message = "problem", last_error
    elif enabled != running:
        status, message = "needs_restart", "Restart DocuHive to apply."
    else:
        status, message = ("on" if enabled else "off"), None
    return PluginOut(
        id=found.id,
        name=manifest.name if manifest else found.id,
        description=manifest.description if manifest else "",
        version=manifest.version if manifest else None,
        source=found.source,
        enabled=enabled,
        running=running,
        state=status,
        message=message,
        capabilities=[Capability(id=c, label=_label(c, manifest)) for c in caps],
        settings=[f.model_dump() for f in manifest.settings] if manifest else [],
        values=state.public_values(manifest) if manifest else {},
        in_ask=(found.id not in (get_setting(NOT_IN_ASK) or []))
        if running and runtime.LOADED[found.id].registry.tools
        else None,
    )


def _found(plugin_id: str) -> discovery.Found:
    found = discovery.find(plugin_id)
    if found is None:
        raise HTTPException(404, {"code": "not_found", "message": "No such plugin", "details": {}})
    return found


@router.get("", response_model=list[PluginOut])
def list_plugins(user: Admin) -> list[PluginOut]:
    rows = state.states()
    return [_out(f, rows) for f in discovery.discover()]


@router.post("/{plugin_id}/enable", response_model=PluginOut)
def enable(plugin_id: str, body: EnableIn, user: Admin) -> PluginOut:
    found = _found(plugin_id)
    if not found.loadable or found.manifest is None:
        raise HTTPException(
            409, {"code": "plugin_problem", "message": "; ".join(found.problems), "details": {}}
        )
    wanted = found.manifest.capability_names()
    if sorted(body.capabilities) != wanted:
        # The person must have seen exactly what this version asks for.
        raise HTTPException(
            409,
            {
                "code": "capabilities_changed",
                "message": "What this plugin asks to do has changed. Reload and review it again.",
                "details": {"capabilities": wanted},
            },
        )
    state.enable(plugin_id, wanted, actor=f"user:{user.id}")
    return _out(found, state.states())


@router.post("/{plugin_id}/disable", response_model=PluginOut)
def disable(plugin_id: str, user: Admin) -> PluginOut:
    found = _found(plugin_id)
    state.disable(plugin_id, actor=f"user:{user.id}")
    return _out(found, state.states())


@router.put("/{plugin_id}/ask", response_model=PluginOut)
def use_in_ask(plugin_id: str, body: AskIn, user: Admin) -> PluginOut:
    """Whether Ask may use this plugin's tools (its records, such as contracts or bookings)."""
    found = _found(plugin_id)
    off = set(get_setting(NOT_IN_ASK) or []) - {plugin_id}
    set_setting(NOT_IN_ASK, sorted(off if body.use else off | {plugin_id}))
    return _out(found, state.states())


@router.put("/{plugin_id}/settings", response_model=PluginOut)
def save_settings(plugin_id: str, values: dict[str, Any], user: Admin) -> PluginOut:
    found = _found(plugin_id)
    if found.manifest is None:
        raise HTTPException(
            409, {"code": "plugin_problem", "message": "Fix the plugin first", "details": {}}
        )
    try:
        errors = state.save(found.manifest, values, actor=f"user:{user.id}")
    except state.SecretsUnavailable as error:
        raise HTTPException(
            409, {"code": "secrets_unavailable", "message": str(error), "details": {}}
        ) from None
    if errors:
        raise HTTPException(
            422,
            {
                "code": "invalid_settings",
                "message": "Check the marked fields.",
                "details": {"fields": errors},
            },
        )
    return _out(found, state.states())
