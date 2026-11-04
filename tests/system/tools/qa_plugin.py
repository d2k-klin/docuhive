"""Collect requirement links and persist results without accepting stale evidence."""

import fcntl
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "tmp/qa/results.json"
_outcomes: dict[str, str] = {}
_collection: list[dict] = []
_started_with = ""


def pytest_sessionstart(session):
    global _started_with
    _started_with = fingerprint()


def save_results(outcomes: dict[str, str], stamp: str) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
        results = previous.get("tests", {}) if previous.get("fingerprint") == stamp else {}
        at = datetime.now(UTC).isoformat(timespec="seconds")
        results.update({node: {"outcome": outcome, "at": at} for node, outcome in outcomes.items()})
        temporary = RESULTS.with_suffix(".new")
        temporary.write_text(json.dumps({"fingerprint": stamp, "tests": results}, indent=2) + "\n")
        temporary.replace(RESULTS)


def fingerprint(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    paths = []
    for folder in (
        "services",
        "apps/web",
        "tests",
        "config",
        "evals",
        "examples",
        "deploy",
        ".github/workflows",
    ):
        for directory, children, files in os.walk(root / folder):
            children[:] = [
                c
                for c in children
                if c not in {"node_modules", ".next", "__pycache__", "test-results"}
            ]
            for filename in files:
                path = Path(directory) / filename
                # Next rewrites this generated import path during dev/build; the lockfile pins it.
                if path.name == "next-env.d.ts":
                    continue
                if (
                    path.suffix in {".py", ".ts", ".tsx", ".yaml", ".yml", ".json", ".css", ".sql"}
                    or path.name == "Dockerfile"
                ):
                    paths.append(path)
    paths += [
        root / name
        for name in (
            "pyproject.toml",
            "uv.lock",
            "package-lock.json",
            "Makefile",
            ".importlinter",
            "docs/shared/contracts.md",
            "docs/REQUIREMENTS.md",
        )
    ]
    for path in sorted(paths):
        if path.exists():
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def pytest_collection_modifyitems(config, items):
    _outcomes.clear()
    _collection.clear()
    for item in items:
        if item.get_closest_marker("integration"):
            item.add_marker(pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"]))
        reqs = sorted({req for mark in item.iter_markers("req") for req in mark.args})
        xfail = item.get_closest_marker("xfail")
        _collection.append(
            {
                "nodeid": item.nodeid,
                "requirements": reqs,
                "pending": xfail.kwargs.get("reason", "") if xfail else "",
            }
        )
    destination = os.environ.get("DOCUHIVE_QA_COLLECTION")
    if destination:
        Path(destination).write_text(json.dumps(_collection, indent=2) + "\n")


def pytest_runtest_logreport(report):
    if report.when == "call" or report.failed or (report.skipped and report.when == "setup"):
        outcome = "xfail" if getattr(report, "wasxfail", None) else report.outcome
        if report.when == "teardown" and report.failed:
            outcome = "failed"
        _outcomes[report.nodeid] = outcome


def pytest_sessionfinish(session, exitstatus):
    if session.config.option.collectonly or not _outcomes:
        return
    save_results(_outcomes, _started_with)
