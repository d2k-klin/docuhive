"""Overlay safety, merge rules, cache invalidation and startup validation."""

from types import SimpleNamespace

import pytest
from docuhive import config
from docuhive.config.settings import CoreSettings
from pydantic import ValidationError


def test_merge_cache_and_reload(monkeypatch, tmp_path):
    defaults, overlay = tmp_path / "defaults", tmp_path / "private"
    defaults.mkdir()
    overlay.mkdir()
    monkeypatch.setenv("DOCUHIVE_DEFAULTS_DIR", str(defaults))
    monkeypatch.setenv("DOCUHIVE_OVERLAY_DIR", str(overlay))
    (defaults / "sample.yaml").write_text("nested: {a: 1, b: 2}\nlist: [1, 2]\nscalar: old\n")
    (overlay / "sample.yaml").write_text("nested: {a: 3}\nlist: [9]\nscalar: new\n")
    expected = {"nested": {"a": 3, "b": 2}, "list": [9], "scalar": "new"}
    assert config.load_yaml("sample.yaml") == expected
    config.load_yaml("sample.yaml")["nested"]["b"] = 999
    assert config.load_yaml("sample.yaml") == expected
    (overlay / "sample.yaml").write_text("list: [8]\n")
    assert config.load_yaml("sample.yaml")["list"] == [9]
    config.reload()
    assert config.load_yaml("sample.yaml")["list"] == [8]
    assert config.load_yaml("absent.yaml") == {}


def test_prompt_override_version_and_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCUHIVE_DEFAULTS_DIR", str(tmp_path / "default"))
    monkeypatch.setenv("DOCUHIVE_OVERLAY_DIR", str(tmp_path / "private"))
    for name in ("default", "private"):
        (tmp_path / name / "prompts").mkdir(parents=True)
    default = tmp_path / "default" / "prompts" / "demo.md"
    default.write_text("Default body")
    assert config.prompt("demo") == ("Default body", "demo@1")
    (tmp_path / "private" / "prompts" / "demo.md").write_text("---\nversion: 3\n---\nPrivate body")
    config.reload()
    assert config.prompt("demo") == ("Private body", "demo@3")
    with pytest.raises(FileNotFoundError):
        config.prompt("absent")


def test_config_rejects_traversal_and_non_mapping(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCUHIVE_DEFAULTS_DIR", str(tmp_path))
    (tmp_path / "bad.yaml").write_text("[1, 2]")
    with pytest.raises(ValueError, match="mapping"):
        config.load_yaml("bad.yaml")
    with pytest.raises(ValueError, match="inside"):
        config.load_yaml("../outside.yaml")


def test_plugin_load_failure_is_skipped(monkeypatch):
    def fn():
        return "good"

    def broken():
        raise RuntimeError("broken")

    entries = [
        SimpleNamespace(name="broken", load=broken),
        SimpleNamespace(name="good", load=lambda: SimpleNamespace(after_ingest=fn)),
        SimpleNamespace(name="absent", load=lambda: object()),
    ]
    monkeypatch.setattr(config.metadata, "entry_points", lambda **kwargs: entries)
    assert config.plugins("after_ingest") == [fn]


@pytest.mark.parametrize(
    "settings",
    [
        {"env": "prod", "secret_key": "short"},
        {"env": "test", "auth_disabled": True},
        {"env": "prod", "auth_disabled": True, "secret_key": "x" * 32},
        {"staging_dir": "data/vault/staging"},
        {"max_upload_mb": 0},
    ],
)
def test_invalid_settings_fail_fast(settings):
    with pytest.raises(ValidationError):
        CoreSettings(_env_file=None, **settings)


def test_production_secret_and_separate_metadata():
    from docuhive.db import CoreBase, IntelBase

    settings = CoreSettings(_env_file=None, env="prod", secret_key="x" * 32)
    assert "x" * 32 not in repr(settings)
    assert CoreBase.metadata is not IntelBase.metadata


def test_empty_paths_do_not_resolve_to_the_working_directory():
    assert CoreSettings(_env_file=None, overlay_dir="").overlay_dir is None
    with pytest.raises(ValidationError):
        CoreSettings(_env_file=None, vault_dir="")


def test_invalid_settings_do_not_echo_secrets():
    secret = "synthetic-secret-that-must-never-appear-in-validation-errors"
    with pytest.raises(ValidationError) as error:
        CoreSettings(_env_file=None, env="prod", secret_key=secret, auth_disabled=True)
    assert secret not in str(error.value)
