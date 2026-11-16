"""Load this plugin's modules for tests: the folder name `steuer-de` is not a Python package
name, so it is registered as the package `steuer_de_test`, and relative imports work."""

import importlib
import sys
import types
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
PACKAGE = "steuer_de_test"


def module(name: str):  # type: ignore[no-untyped-def]
    if PACKAGE not in sys.modules:
        package = types.ModuleType(PACKAGE)
        package.__path__ = [str(PLUGIN)]
        sys.modules[PACKAGE] = package
    return importlib.import_module(f"{PACKAGE}.{name}")
