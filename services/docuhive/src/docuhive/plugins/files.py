"""A plugin's own files, with the user's replacements in `custom/` taking precedence."""

from copy import deepcopy
from pathlib import Path
from typing import Literal

from .manifest import load_yaml

KINDS = ("rules", "templates", "prompts", "pages")
Kind = Literal["rules", "templates", "prompts", "pages"]


def _inside(root: Path, *parts: str) -> Path:
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("A plugin file name must stay inside the plugin folder")
    return path


def resolve(plugin: Path, kind: Kind, name: str) -> Path | None:
    for base in (plugin / "custom" / kind, plugin / kind):
        path = _inside(plugin, *base.relative_to(plugin).parts, name)
        if path.is_file():
            return path
    return None


def read_text(plugin: Path, kind: Kind, name: str) -> str:
    path = resolve(plugin, kind, name)
    if path is None:
        raise FileNotFoundError(f"{kind}/{name} is not part of this plugin")
    return path.read_text(encoding="utf-8")


def merge(base: object, custom: object) -> object:
    """Mappings merge key by key; lists of entries with an `id` merge by id; the rest replaces."""
    if isinstance(base, dict) and isinstance(custom, dict):
        out = deepcopy(base)
        for key, value in custom.items():
            out[key] = merge(out[key], value) if key in out else deepcopy(value)
        return out
    if (
        isinstance(base, list)
        and isinstance(custom, list)
        and all(isinstance(i, dict) and "id" in i for i in base + custom)
    ):
        out_list = [deepcopy(i) for i in base]
        index = {item["id"]: n for n, item in enumerate(out_list)}
        for item in custom:
            if item["id"] in index:
                out_list[index[item["id"]]] = merge(out_list[index[item["id"]]], item)
            else:
                out_list.append(deepcopy(item))
        return out_list
    return deepcopy(custom)


def rules(plugin: Path, name: str) -> object:
    """A rules file. A custom file starting with `_merge: true` adds to the plugin's own file;
    any other custom file replaces it."""
    own = _inside(plugin, "rules", name)
    custom = _inside(plugin, "custom", "rules", name)
    base = load_yaml(own) if own.is_file() else None
    if not custom.is_file():
        if base is None:
            raise FileNotFoundError(f"rules/{name} is not part of this plugin")
        return _plain(base)
    mine = _plain(load_yaml(custom))
    if isinstance(mine, dict) and mine.pop("_merge", False) and base is not None:
        return merge(_plain(base), mine)
    return mine


def _plain(value: object) -> object:
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def listing(plugin: Path) -> list[dict]:
    """Every customisable file, where it currently comes from."""
    out = []
    for kind in KINDS:
        names = {
            p.relative_to(root).as_posix()
            for root in (plugin / kind, plugin / "custom" / kind)
            if root.is_dir()
            for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        }
        for name in sorted(names):
            own = (plugin / kind / name).is_file()
            custom = (plugin / "custom" / kind / name).is_file()
            out.append(
                {
                    "file": f"{kind}/{name}",
                    "from": "custom" if custom else "plugin",
                    "replaces": own and custom,
                    "only_custom": custom and not own,
                }
            )
    return out
