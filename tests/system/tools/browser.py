"""Run Playwright once and attach its exact-candidate evidence to the requirement matrix."""

import json
import subprocess
import sys

from qa_plugin import ROOT, fingerprint, save_results


def outcomes(report: dict) -> dict[str, str]:
    result = {}

    def visit(suite: dict) -> None:
        for spec in suite.get("specs", []):
            for test in spec["tests"]:
                node = f"{spec['file']}::{spec['title']}[{test['projectName']}]"
                runs = test.get("results", [])
                passed = (
                    test.get("expectedStatus") == "passed"
                    and len(runs) == 1
                    and runs[0].get("status") == "passed"
                )
                result[node] = (
                    "passed"
                    if passed
                    else "pending"
                    if not runs or all(r.get("status") == "skipped" for r in runs)
                    else "failed"
                )
        for child in suite.get("suites", []):
            visit(child)

    for suite in report["suites"]:
        visit(suite)
    return result


def main() -> None:
    stamp = fingerprint()
    output = ROOT / "tmp/qa/playwright.json"
    output.unlink(missing_ok=True)
    run = subprocess.run(
        [
            "node",
            "node_modules/@playwright/test/cli.js",
            "test",
            "--config=tests/e2e/playwright.config.ts",
            *sys.argv[1:],
        ],
        cwd=ROOT,
    )
    if output.exists():
        save_results(outcomes(json.loads(output.read_text())), stamp)
    sys.exit(run.returncode)


if __name__ == "__main__":
    main()
