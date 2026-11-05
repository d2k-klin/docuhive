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


def test_hybrid_search_example_runs():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "examples/learn/09_hybrid_search.py")],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
        env=dict(os.environ, DOCUHIVE_ENV="test"),
    )
    assert "Hybrid ranking" in result.stdout and "electricity-bill" in result.stdout


def test_near_duplicates_example_runs():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "examples/learn/13_near_duplicates.py")],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
        env=dict(os.environ, DOCUHIVE_ENV="test"),
    )
    assert "next month's invoice" in result.stdout and "→ False" in result.stdout


def test_controlled_categories_example_runs():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "examples/learn/02_categories.py")],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
        env=dict(os.environ, DOCUHIVE_ENV="test"),
    )
    assert "Disabled category rejected; custom category accepted" in result.stdout
