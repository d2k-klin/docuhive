"""Cross-track imports go through the public contracts only."""

import subprocess
import sys
from pathlib import Path

import pytest
from qa_plugin import ROOT


@pytest.mark.req("QAR-INT-03")
def test_import_linter_contracts():
    result = subprocess.run(
        [str(Path(sys.executable).with_name("lint-imports")), "--no-cache"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
