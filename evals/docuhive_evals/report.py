"""Markdown + JSON reports with a side-by-side table per route."""

import json
from datetime import date
from pathlib import Path


def _flat(d: dict, prefix: str = "") -> dict:
    out: dict = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out |= _flat(v, f"{prefix}{k}.")
        else:
            out[f"{prefix}{k}"] = v
    return out


def _fmt(v: object) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.3f}" if v < 10 else f"{v:.0f}"
    return str(v)


def markdown(task: str, set_names: list[str], results: list[dict]) -> str:
    rows = [_flat(r) for r in results]
    keys = [k for k in rows[0] if k != "route"] if rows else []
    lines = [
        f"# Eval: {task} — {date.today().isoformat()}",
        "",
        f"Sets: {', '.join(set_names)}",
        "",
        "| metric | " + " | ".join(f"`{r['route']}`" for r in rows) + " |",
        "| --- |" + " --- |" * len(rows),
    ]
    lines += [f"| {k} | " + " | ".join(_fmt(r.get(k)) for r in rows) + " |" for k in keys]
    lines += [
        "",
        "Gate (docs/decisions/0004-model-selection.md): "
        "precision_above_threshold >= 0.95 and category/document_type accuracy >= 0.90.",
    ]
    return "\n".join(lines) + "\n"


def write(out_dir: Path, task: str, set_names: list[str], results: list[dict]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"{date.today().isoformat()}-{task}"
    md = markdown(task, set_names, results)
    stem.with_suffix(".md").write_text(md, encoding="utf-8")
    stem.with_suffix(".json").write_text(json.dumps(results, indent=2, default=str))
    return stem.with_suffix(".md")


def gate(result: dict) -> bool:
    """NFR-09: auto-apply only if calibrated precision >= 95% and category/type >= 90%."""
    return (
        (result.get("precision_above_threshold") or 0) >= 0.95
        and (result.get("category_accuracy") or 0) >= 0.90
        and (result.get("document_type_accuracy") or 0) >= 0.90
    )
