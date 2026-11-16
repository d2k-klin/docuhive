"""Load this plugin's modules for tests (the folder name `vermieter-de` is not a package name)."""

import importlib
import sys
import types
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
PACKAGE = "vermieter_de_test"


def module(name: str):  # type: ignore[no-untyped-def]
    if PACKAGE not in sys.modules:
        package = types.ModuleType(PACKAGE)
        package.__path__ = [str(PLUGIN)]
        sys.modules[PACKAGE] = package
    return importlib.import_module(f"{PACKAGE}.{name}")
