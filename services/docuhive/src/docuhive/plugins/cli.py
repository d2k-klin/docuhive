"""`docuhive plugins …`: add, update, copy, check, switch on and off."""

import argparse
import subprocess
import sys
from pathlib import Path

from . import catalogue, discovery, files, state
from . import check as checks
from .manifest import CAPABILITIES

SKELETON = """id: {id}
name: {name}
description: What this plugin does for the person using it, in one sentence.
version: 0.1.0
requires_sdk: ">=1,<2"
capabilities: [documents:read]
"""
README = """# {name}

**Overview.** What this plugin does, for whom.

## Set it up

1. Add the plugin and switch it on under **Settings → Plugins**.

## Make it yours

| File | What it controls |
| --- | --- |
"""


def register(subs: argparse._SubParsersAction) -> None:
    p = subs.add_parser("plugins", help="Add, check and switch plugins on and off")
    p.set_defaults(func=run)
    sub = p.add_subparsers(dest="plugins_action", required=True)
    sub.add_parser("list", help="Installed plugins and their state")
    add = sub.add_parser("add", help="Copy a plugin folder into your plugins folder")
    add.add_argument("path")
    upd = sub.add_parser("update", help="Replace a plugin with a newer copy, keeping custom/")
    upd.add_argument("id")
    upd.add_argument("--from", dest="source", required=True)
    upd.add_argument("--force", action="store_true", help="Allow an older version")
    new = sub.add_parser("new", help="Start a plugin, or copy one under a new name")
    new.add_argument("id")
    new.add_argument("--from", dest="source", help="Id of an installed plugin to copy")
    for name, text in (
        ("check", "Find problems in a plugin"),
        ("files", "Show customisable files and where each comes from"),
        ("test", "Run a plugin's tests"),
        ("disable", "Switch a plugin off"),
    ):
        sub.add_parser(name, help=text).add_argument("id")
    en = sub.add_parser("enable", help="Switch a plugin on")
    en.add_argument("id")
    en.add_argument("--yes", action="store_true", help="Do not ask to confirm what it may do")
    pg = sub.add_parser("purge", help="Delete a switched-off plugin's data and settings")
    pg.add_argument("id")


def _root() -> Path:
    root = discovery.plugins_dir()
    if root is None:
        raise SystemExit(
            "No plugins folder: set DOCUHIVE_OVERLAY_DIR (plugins go in its plugins/ folder) "
            "or DOCUHIVE_PLUGINS_DIR."
        )
    root.mkdir(parents=True, exist_ok=True)
    return root


def _found(plugin_id: str) -> discovery.Found:
    found = discovery.find(plugin_id)
    if found is None:
        raise SystemExit(
            f"No plugin '{plugin_id}'. `docuhive plugins list` shows what is installed."
        )
    return found


def _print_problems(problems: list[str]) -> None:
    for problem in problems:
        print(f"  ✗ {problem}")


def run(args: argparse.Namespace) -> None:
    action = args.plugins_action
    if action == "list":
        return _list()
    if action == "add":
        return _add(Path(args.path))
    if action == "update":
        return _update(args.id, Path(args.source), args.force)
    if action == "new":
        return _new(args.id, args.source)
    found = _found(args.id)
    if action == "check":
        problems = checks.check(found.path)
        if problems:
            print(f"{found.id}: {len(problems)} problem(s)")
            _print_problems(problems)
            raise SystemExit(1)
        print(f"{found.id}: no problems found")
    elif action == "files":
        for item in files.listing(found.path):
            note = "custom (replaces the plugin's)" if item["replaces"] else item["from"]
            print(f"  {item['file']:<45} {note}")
    elif action == "test":
        tests = found.path / "tests"
        if not tests.is_dir():
            raise SystemExit(f"{found.id} has no tests folder")
        sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", str(tests)]))  # noqa: S603
    elif action == "enable":
        _enable(found, args.yes)
    elif action == "disable":
        state.disable(found.id, actor="cli")
        print(f"{found.id} is off. Its documents and data are kept.")
    elif action == "purge":
        _purge(found)


def _list() -> None:
    rows = discovery.discover()
    print(f"Plugins folder: {discovery.plugins_dir() or '(not set)'}")
    try:
        saved = state.states()
    except Exception:  # noqa: BLE001 - listing must work without a database
        saved = {}
    if not rows:
        print("  No plugins. Copy one with: docuhive plugins add plugins-example/<name>")
    for found in rows:
        row = saved.get(found.id)
        status = "on" if row and row.enabled else "off"
        if found.problems:
            status = "problem: " + found.problems[0]
        elif row and row.last_error:
            status += f" ({row.last_error})"
        version = found.manifest.version if found.manifest else "?"
        print(f"  {found.id:<20} {version:<9} {found.source:<8} {status}")


def _copy(source: Path, target: Path, keep_custom: Path | None = None) -> None:
    catalogue.copy(source, target, keep_custom)


def _add(source: Path) -> None:
    try:
        manifest = catalogue.install(source)
    except catalogue.Refused as error:
        raise SystemExit(f"Not added: {error}") from None
    print(f"Added {manifest.name} {manifest.version} to {_root() / manifest.id}.")
    print("Switch it on under Settings → Plugins, or run:")
    print(f"  docuhive plugins enable {manifest.id}")


def _update(plugin_id: str, source: Path, force: bool) -> None:
    try:
        old, new = catalogue.update(plugin_id, source, force=force)
    except catalogue.Refused as error:
        raise SystemExit(f"Not updated: {error}") from None
    added = set(new.capability_names()) - set(old.capability_names())
    print(f"Updated {plugin_id} {old.version} → {new.version}. Your custom/ files are unchanged.")
    if added:
        print("It now also asks to: " + ", ".join(sorted(added)))
        print("It stays off until you approve that under Settings → Plugins.")


def _new(plugin_id: str, source_id: str | None) -> None:
    import re

    if not re.fullmatch(r"[a-z][a-z0-9-]{1,30}", plugin_id):
        raise SystemExit("Use lowercase letters, digits and dashes, starting with a letter")
    target = _root() / plugin_id
    if target.exists():
        raise SystemExit(f"{target} already exists")
    name = plugin_id.replace("-", " ").capitalize()
    if source_id is None:
        target.mkdir()
        (target / "plugin.yaml").write_text(SKELETON.format(id=plugin_id, name=name))
        (target / "README.md").write_text(README.format(name=name))
        for folder in ("custom", "pages", "tests"):
            (target / folder).mkdir()
        print(f"Created {target}. Edit plugin.yaml, then: docuhive plugins check {plugin_id}")
        return
    source = _found(source_id)
    _copy(source.path, target)
    manifest_file = target / "plugin.yaml"
    text = manifest_file.read_text()
    text = re.sub(r"(?m)^id:\s*\S+", f"id: {plugin_id}", text, count=1)
    text = re.sub(
        r"(?m)^name:.*$",
        f"name: {name} (from {source.manifest.name if source.manifest else source_id})",
        text,
        count=1,
    )
    text = re.sub(r"(?m)^version:.*$", "version: 0.1.0", text, count=1)
    manifest_file.write_text(text)
    print(f"Copied {source_id} to {target} as '{plugin_id}'. It is yours now: updates of")
    print(f"{source_id} will not change it. Switch {source_id} off and {plugin_id} on.")


def _enable(found: discovery.Found, yes: bool) -> None:
    if not found.loadable or found.manifest is None:
        print(f"{found.id} cannot be switched on:")
        _print_problems(found.problems)
        raise SystemExit(1)
    granted = found.manifest.capability_names()
    print(f"{found.manifest.name} {found.manifest.version} may:")
    for cap in granted:
        print(
            f"  - {CAPABILITIES.get(cap, cap.replace('network:', 'Reach the internet address '))}"
        )
    print(
        "A plugin runs inside DocuHive with access to your documents. Only use plugins you trust."
    )
    if not yes and input("Switch it on? [y/N] ").strip().lower() not in {"y", "yes"}:
        raise SystemExit("Not switched on")
    state.enable(found.id, granted, actor="cli")
    print(f"{found.id} is on. DocuHive loads it within seconds.")


def _purge(found: discovery.Found) -> None:
    row = state.states().get(found.id)
    if row and row.enabled:
        raise SystemExit(f"Switch {found.id} off first: docuhive plugins disable {found.id}")
    if input(f"This deletes {found.id}'s data and settings. Type its id to confirm: ") != found.id:
        raise SystemExit("Nothing deleted")
    from . import data

    data.drop(found.id)
    state.forget(found.id, actor="cli")
    print(f"Deleted the data and settings of {found.id}. Its documents stay in the archive.")
