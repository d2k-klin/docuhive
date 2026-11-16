"""`docuhive plugins check`: everything that can be wrong with a plugin folder, in plain words."""

import ast
from collections.abc import Callable
from pathlib import Path

from . import files
from .manifest import Manifest, ManifestError, load, load_yaml

# Modules a plugin must not import: core internals (use docuhive.sdk) and raw network access
# (use docuhive.sdk.http, which only reaches the hosts the plugin declared).
NETWORK = {"httpx", "requests", "urllib.request", "socket", "http.client", "aiohttp", "urllib3"}
# Later parts of the platform add their checks: fn(path, manifest) -> list of problems.
CHECKS: list[Callable[[Path, Manifest], list[str]]] = []


def _imports(tree: ast.AST) -> list[tuple[str, int]]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(alias.name, node.lineno) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.append((node.module, node.lineno))
    return out


def scan_imports(path: Path) -> list[str]:
    problems = []
    for file in sorted(path.rglob("*.py")):
        # Tests may set up scenes with the core directly; the plugin's own code may not.
        if "__pycache__" in file.parts or file.relative_to(path).parts[0] in {"custom", "tests"}:
            continue
        where = file.relative_to(path).as_posix()
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=where)
        except SyntaxError as error:
            problems.append(f"{where}:{error.lineno}: {error.msg}")
            continue
        for module, line in _imports(tree):
            if module == "docuhive" or (
                module.startswith("docuhive.")
                and not (module == "docuhive.sdk" or module.startswith("docuhive.sdk."))
            ):
                problems.append(f"{where}:{line}: imports {module}; plugins use docuhive.sdk only")
            if module in NETWORK or module.split(".")[0] in NETWORK - {"urllib.request"}:
                problems.append(
                    f"{where}:{line}: imports {module}; use docuhive.sdk.http and declare the "
                    "hosts under capabilities: network"
                )
    return problems


def scan_files(path: Path) -> list[str]:
    problems = []
    for kind in ("rules", "pages"):
        for base in (path / kind, path / "custom" / kind):
            for file in sorted(base.rglob("*.y*ml")) if base.is_dir() else []:
                try:
                    load_yaml(file)
                except ManifestError as error:
                    rel = file.relative_to(path).as_posix()
                    problems += [f"{rel}: {p.split(': ', 1)[-1]}" for p in error.problems]
    for item in files.listing(path):
        if item["only_custom"] and item["file"].split("/")[0] in ("rules", "templates", "prompts"):
            problems.append(
                f"custom/{item['file']}: replaces nothing; the plugin has no {item['file']} "
                "(check the name)"
            )
    return problems


def _source(path: Path) -> str:
    return "\n".join(
        f.read_text(encoding="utf-8") for f in path.rglob("*.py") if "__pycache__" not in f.parts
    )


def check(path: Path) -> list[str]:
    if not (path / "plugin.yaml").is_file():
        return [f"{path.name}: no plugin.yaml in this folder"]
    try:
        manifest = load(path)
    except ManifestError as error:
        return error.problems
    problems: list[str] = []
    if not manifest.sdk_compatible():
        problems.append(
            f"plugin.yaml: requires_sdk {manifest.requires_sdk} does not match this DocuHive"
        )
    problems += scan_imports(path)
    problems += scan_files(path)
    from . import data

    problems += data.check(path)
    if data.migrations(path) and not manifest.snapshot and "@registry.rebuild" not in _source(path):
        problems.append(
            "plugin.yaml: the plugin has tables but no way to get them back after a restore; "
            "set snapshot: true or register @registry.rebuild in plugin.py"
        )
    from . import pages

    problems += pages.load(path)[1]
    for task in manifest.ai_tasks:
        if files.resolve(path, "prompts", f"{task.prompt}.md") is None:
            problems.append(
                f"plugin.yaml: ai_tasks names prompts/{task.prompt}.md, which is missing"
            )
    if not (path / "README.md").is_file():
        problems.append("README.md: missing; say what the plugin does for the person using it")
    for extra in CHECKS:
        problems += extra(path, manifest)
    return problems
