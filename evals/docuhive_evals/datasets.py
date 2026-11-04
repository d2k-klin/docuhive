"""Loaders for eval sets (evals/synthetic, overlay/evals/golden). Schema errors are readable."""

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError


class Expect(BaseModel):
    category: str
    document_type: str
    correspondent: str | None = None
    document_date: date | None = None
    language: str
    tags: list[str] = []
    facts: dict[str, dict | str] = {}  # money: {value, currency}; others: "canonical string"


class Case(BaseModel):
    id: str
    file: str
    expect: Expect
    restricted: bool = False
    text: str = ""


class DatasetError(ValueError):
    pass


def load_labels(set_dir: Path) -> list[Case]:
    path = set_dir / "labels.yaml"
    if not path.exists():
        raise DatasetError(f"{path}: not found (expected labels.yaml in the set folder)")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    cases: list[Case] = []
    for i, item in enumerate(raw):
        try:
            case = Case.model_validate(item)
        except ValidationError as e:
            where = item.get("id", f"#{i}") if isinstance(item, dict) else f"#{i}"
            errs = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
            raise DatasetError(f"{path} entry {where}: {errs}") from None
        doc = set_dir / case.file
        if not doc.exists():
            raise DatasetError(f"{path} entry {case.id}: file {case.file} not found")
        case.text = doc.read_text(encoding="utf-8") if doc.suffix == ".txt" else _pdf_text(doc)
        cases.append(case)
    return cases


def _pdf_text(path: Path) -> str:
    try:  # golden sets may hold PDFs; OA's text extraction does the work when installed
        from docuhive.ingest.text import extract_text  # type: ignore[import-not-found]
    except ImportError as e:
        raise DatasetError(f"{path}: PDF cases need OA's text extraction (docuhive[ocr])") from e
    return extract_text(path)


def load_yaml_list(set_dir: Path, name: str) -> list[dict]:
    path = set_dir / name
    if not path.exists():
        return []
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []
