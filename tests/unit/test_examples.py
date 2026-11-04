"""Every committed standalone learning example runs without network or provider keys."""

import os
import subprocess
import sys
from pathlib import Path


def test_job_queue_example_runs():
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ, DOCUHIVE_ENV="test")
    result = subprocess.run(
        [sys.executable, str(root / "examples/learn/12_job_queue.py")],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )
    assert "one pending job" in result.stdout
