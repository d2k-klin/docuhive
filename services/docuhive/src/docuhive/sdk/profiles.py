"""The identities a person may use (Settings → Identities). Passwords are never part of it."""

import builtins

from docuhive import profiles as core
from docuhive.contracts import CurrentUser

from ._plugin import current

NotFound = core.NotFound


def _public(profile: core.ProfileOut) -> dict:
    return profile.model_dump(exclude={"smtp"}) | {"can_send": profile.smtp is not None}


def list(user: CurrentUser) -> builtins.list[dict]:  # noqa: A001
    current()
    return [_public(p) for p in core.list_for(user)]


def get(user: CurrentUser, profile_id: int) -> dict:
    current()
    return _public(core.get(user, profile_id))
