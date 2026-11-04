"""Compute OCR character error rate from private reference and extracted text files."""

import argparse
import unicodedata
from pathlib import Path


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def distance(expected: str, actual: str) -> int:
    if len(expected) < len(actual):
        expected, actual = actual, expected
    previous = list(range(len(actual) + 1))
    for index, char in enumerate(expected, 1):
        current = [index]
        for other_index, other in enumerate(actual, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[other_index] + 1,
                    previous[other_index - 1] + (char != other),
                )
            )
        previous = current
    return previous[-1]


def character_error_rate(reference: str, observed: str) -> float:
    expected, actual = normalize(reference), normalize(observed)
    if not expected:
        if actual:
            raise ValueError("Reference text is empty; CER is undefined")
        return 0.0
    return distance(expected, actual) / len(expected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("observed", type=Path)
    args = parser.parse_args()
    rate = character_error_rate(args.reference.read_text(), args.observed.read_text())
    print(f"CER: {rate:.2%}")


if __name__ == "__main__":
    main()
