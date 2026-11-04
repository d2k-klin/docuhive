"""Carry public defaults and the license through both wheel and source distributions."""

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:
        project = Path(self.root)
        repository = project.parents[1]
        resources = project / "_distribution"
        defaults = repository / "config/defaults"
        license_file = repository / "LICENSE"
        if not defaults.is_dir():
            defaults = resources / "defaults"
        if not license_file.is_file():
            license_file = resources / "LICENSE"
        destination = "_distribution" if self.target_name == "sdist" else "docuhive"
        defaults_name = "defaults" if self.target_name == "sdist" else "_defaults"
        build_data.setdefault("force_include", {}).update(
            {
                str(defaults): f"{destination}/{defaults_name}",
                str(license_file): f"{destination}/LICENSE",
            }
        )
