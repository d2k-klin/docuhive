"""Find installed plugins by reading their plugin.yaml only; no plugin code runs here."""

import importlib.util
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Literal

from docuhive.config.settings import get_settings

from .manifest import Manifest, ManifestError, load

EXAMPLES = Path(__file__).resolve().parents[5] / "plugins-example"


@dataclass
class Found:
    id: str
    path: Path
    source: Literal["folder", "package", "dev"]
    manifest: Manifest | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def loadable(self) -> bool:
        return self.manifest is not None and not self.problems


def plugins_dir() -> Path | None:
    settings = get_settings()
    # Absolute, so every path derived from it compares with resolved file paths.
    if settings.plugins_dir is not None:
        return settings.plugins_dir.resolve()
    return (settings.overlay_dir / "plugins").resolve() if settings.overlay_dir else None


def _folders(root: Path | None) -> list[Path]:
    if root is None or not root.is_dir():
        return []
    return sorted(
        p
        for p in root.iterdir()
        # Symlinks are skipped like in the scanner folder; `name.disabled` parks a plugin.
        if p.is_dir()
        and not p.is_symlink()
        and not p.name.startswith((".", "_"))
        and not p.name.endswith(".disabled")
        and (p / "plugin.yaml").is_file()
    )


def _packages() -> list[Path]:
    """Installed packages registered in `docuhive.plugins` whose folder holds a plugin.yaml."""
    out = []
    for entry in metadata.entry_points(group="docuhive.plugins"):
        try:
            spec = importlib.util.find_spec(entry.value.split(":")[0])
        except (ImportError, ValueError):
            continue
        for location in (spec and spec.submodule_search_locations) or []:
            if (Path(location) / "plugin.yaml").is_file():
                out.append(Path(location))
    return out


def _read(path: Path, source: Literal["folder", "package", "dev"]) -> Found:
    found = Found(id=path.name, path=path, source=source)
    try:
        found.manifest = load(path)
        found.id = found.manifest.id
        if not found.manifest.sdk_compatible():
            found.problems.append(
                f"Needs a newer DocuHive: it was written for plugin interface "
                f"{found.manifest.requires_sdk}"
            )
    except ManifestError as error:
        found.problems += error.problems
    return found


def discover() -> list[Found]:
    """Every plugin, in dependency order; the first source wins for a repeated id."""
    settings = get_settings()
    candidates = [_read(p, "folder") for p in _folders(plugins_dir())]
    candidates += [_read(p, "package") for p in _packages()]
    if settings.env == "dev" and settings.plugins_dev:
        candidates += [_read(p, "dev") for p in _folders(EXAMPLES)]
    by_id: dict[str, Found] = {}
    for found in candidates:
        by_id.setdefault(found.id, found)
    for found in by_id.values():
        for dep in found.manifest.depends_on if found.manifest else []:
            if dep not in by_id:
                found.problems.append(f"Needs the plugin '{dep}', which is not installed")
    return _ordered(by_id)


def _ordered(by_id: dict[str, Found]) -> list[Found]:
    done: list[Found] = []
    seen: set[str] = set()

    def visit(found: Found, path: tuple[str, ...]) -> None:
        if found.id in seen:
            return
        if found.id in path:
            found.problems.append("Its dependencies form a loop: " + " → ".join((*path, found.id)))
            return
        for dep in found.manifest.depends_on if found.manifest else []:
            if dep in by_id:
                visit(by_id[dep], (*path, found.id))
        seen.add(found.id)
        done.append(found)

    for found in sorted(by_id.values(), key=lambda f: f.id):
        visit(found, ())
    return done


def find(plugin_id: str) -> Found | None:
    return next((f for f in discover() if f.id == plugin_id), None)
