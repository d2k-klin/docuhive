"""List or run a learning example by its numeric prefix."""

import runpy
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).parent
    number = sys.argv[1] if len(sys.argv) > 1 else ""
    examples = sorted(root.glob("[0-9][0-9]_*.py"))
    if not number:
        for example in examples:
            print(example.stem)
        return
    matches = [path for path in examples if path.name.startswith(f"{int(number):02d}_")]
    if len(matches) != 1:
        raise SystemExit("Choose one of the available example numbers with EX=NN")
    runpy.run_path(str(matches[0]), run_name="__main__")


if __name__ == "__main__":
    main()
