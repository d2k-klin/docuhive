"""The CI gate catches SPDX identifiers and full-name AGPL variants."""

import importlib.util
from pathlib import Path


def test_agpl_rejection():
    path = Path(__file__).resolve().parents[2] / "deploy/scripts/check_licenses.py"
    spec = importlib.util.spec_from_file_location("license_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for license_name in ("AGPL-3.0", "AGPLv3", "GNU Affero General Public License v3"):
        assert module.forbidden_license(license_name)
    for license_name in ("Apache-2.0", "BSD-3-Clause", "MIT", "MPL-2.0", "LGPL-3.0"):
        assert not module.forbidden_license(license_name)
