"""Check the built browser assets, never server-side source-map metadata."""

import re
import sys

from qa_plugin import ROOT


def main() -> None:
    bundle = ROOT / "tmp/qa/web-static"
    files = list(bundle.rglob("*"))
    if not any(path.suffix == ".js" for path in files):
        sys.exit("No production browser assets copied; run make qa-bundle")
    prompts = []
    for path in (ROOT / "config/defaults/prompts").glob("*.md"):
        body = re.sub(r"\A---.*?---\s*", "", path.read_text(), flags=re.S)
        prompts += [line.strip() for line in body.splitlines() if len(line.strip()) >= 60]
    failures = []
    for path in files:
        if path.suffix == ".map":
            failures.append(f"source map: {path.name}")
        if path.suffix not in {".js", ".json", ".css"}:
            continue
        text = path.read_text()
        if (
            "DOCUHIVE_AI_" in text
            or "DOCUHIVE_MAIL_" in text
            or any(line in text for line in prompts)
        ):
            failures.append(f"server configuration or prompt: {path.name}")
    if failures:
        sys.exit("\n".join(failures))
    print(f"Browser exposure checks passed ({len(files)} assets)")


if __name__ == "__main__":
    main()
