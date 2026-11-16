"""Load this plugin's modules by path: the folder name `vertraege` is not a Python package name."""

import importlib.util
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]


def module(name: str):  # type: ignore[no-untyped-def]
    key = f"vertraege_test_{name}"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, PLUGIN / f"{name}.py")
        loaded = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.modules[key] = loaded
        spec.loader.exec_module(loaded)  # type: ignore[union-attr]
    return sys.modules[key]
