"""The plugins shipped with DocuHive: browse, install, update and remove them from the app.

The catalogue is a read-only folder in the image (or ./plugins-example in development). Installing
copies a plugin into the writable plugins folder; every process then loads it when it is switched
on, without a restart. A person's `custom/` files stay through updates. Nothing is downloaded.
"""

import shutil
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from docuhive.config.settings import get_settings

from . import check as checks
from . import discovery, state
from .manifest import Manifest, ManifestError, load, satisfies

IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")


class Refused(ValueError):
    """Said to the person as it is."""


def root() -> Path | None:
    configured = get_settings().catalogue_dir
    if configured is not None:
        return configured.resolve()
    return discovery.EXAMPLES if discovery.EXAMPLES.is_dir() else None


def entries() -> list[discovery.Found]:
    """Every plugin in the catalogue, with its manifest, or the problems that keep it out."""
    return [discovery.read(p, "catalogue") for p in discovery.folders(root())]


def entry(plugin_id: str) -> discovery.Found:
    found = next((f for f in entries() if f.id == plugin_id), None)
    if found is None or found.manifest is None:
        raise Refused(f"'{plugin_id}' is not in the catalogue")
    return found


def target_root() -> Path:
    folder = discovery.plugins_dir()
    if folder is None:
        raise Refused("No plugins folder is set: set DOCUHIVE_PLUGINS_DIR (installation guide).")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _changed() -> None:
    try:
        state.changed()
    except SQLAlchemyError:
        pass  # the command line works without a database; the processes sync when they start


def copy(source: Path, target: Path, keep_custom: Path | None = None) -> None:
    shutil.copytree(source, target, ignore=IGNORE)
    custom = target / "custom"
    if keep_custom is not None:
        shutil.rmtree(custom, ignore_errors=True)
        shutil.copytree(keep_custom, custom)
    elif custom.exists():
        # The user's files belong to their installation, never to the copy being added.
        shutil.rmtree(custom)
    custom.mkdir(exist_ok=True)


def install(source: Path) -> Manifest:
    """Copy a plugin folder into the plugins folder. It stays off until switched on."""
    try:
        manifest = load(source)
    except ManifestError as error:
        raise Refused(f"{source} is not a valid plugin: " + "; ".join(error.problems)) from None
    if not manifest.sdk_compatible():
        raise Refused(f"{manifest.name} needs a newer DocuHive ({manifest.requires_sdk})")
    target = target_root() / manifest.id
    if target.exists() or discovery.find(manifest.id) is not None:
        raise Refused(f"'{manifest.id}' is already installed")
    copy(source, target)
    _changed()
    return manifest


def update(plugin_id: str, source: Path, *, force: bool = False) -> tuple[Manifest, Manifest]:
    """Replace an installed plugin with a newer copy, keeping its custom/ files. If the new
    version asks to do more, it stays off until an administrator approves that."""
    target = target_root() / plugin_id
    if not target.is_dir():
        raise Refused(f"'{plugin_id}' is not installed in {target.parent}")
    try:
        new, old = load(source), load(target)
    except ManifestError as error:
        raise Refused("; ".join(error.problems)) from None
    if new.id != plugin_id:
        raise Refused(f"{source} is the plugin '{new.id}', not '{plugin_id}'")
    if not new.sdk_compatible():
        raise Refused(f"{new.version} needs a newer DocuHive ({new.requires_sdk})")
    if not force and not satisfies(new.version, f">={old.version}"):
        raise Refused(f"{new.version} is older than the installed {old.version}")
    staging = target.with_name(f".{plugin_id}.updating")
    shutil.rmtree(staging, ignore_errors=True)
    copy(source, staging, keep_custom=target / "custom")
    problems = checks.scan_files(staging)
    if problems:
        shutil.rmtree(staging)
        raise Refused("Your custom files do not fit the new version: " + "; ".join(problems))
    backup = target.with_name(f".{plugin_id}.previous")
    shutil.rmtree(backup, ignore_errors=True)
    target.rename(backup)
    staging.rename(target)
    shutil.rmtree(backup)
    _changed()
    return old, new


def remove(plugin_id: str) -> None:
    """Delete an installed plugin's folder. It must be off; its data and settings stay, so
    installing it again brings everything back (purge deletes them)."""
    rows = state.states()
    if rows.get(plugin_id) and rows[plugin_id].enabled:
        raise Refused("Switch it off first.")
    target = target_root() / plugin_id
    if not target.is_dir():
        raise Refused(f"'{plugin_id}' was not installed from the catalogue; remove it by hand")
    shutil.rmtree(target)
    _changed()
