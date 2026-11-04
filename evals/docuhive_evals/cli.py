"""`docuhive eval ...` (registered through docuhive.ai.cli when this package is installed)."""

import argparse
import json
from pathlib import Path

from docuhive_evals import report
from docuhive_evals.datasets import load_labels, load_yaml_list


def _routes(args: argparse.Namespace, task: str) -> list[str]:
    routes = [r.split("=", 1)[1] for r in args.route if r.startswith(f"{task}=")]
    if not routes:
        raise SystemExit(f"Pass at least one --route {task}=<provider>/<model>")
    return routes


def _cases(args: argparse.Namespace):  # type: ignore[no-untyped-def]
    cases = [c for s in args.set for c in load_labels(Path(s))]
    return cases[: args.limit] if args.limit else cases


def _fakes(task: str, cases: list) -> dict:
    from docuhive_evals import oracle

    return oracle.classify_fakes(cases) if task == "classify" else oracle.extract_fakes(cases)


def run_task(args: argparse.Namespace) -> None:
    from docuhive_evals import runner

    cases = _cases(args)
    fn = runner.classify_set if args.task == "classify" else runner.extract_set
    results = []
    for route in _routes(args, args.task):
        fakes = _fakes(args.task, cases) if route.startswith("fake/") else None
        results.append(fn(cases, route, concurrency=args.concurrency, fakes=fakes))
    out = report.write(Path(args.out), args.task, args.set, results)
    print(out.read_text())
    if args.task == "classify":
        for r in results:
            print(f"gate {r['route']}: {'PASS' if report.gate(r) else 'fail'}")


def run_search(args: argparse.Namespace) -> None:
    from docuhive_evals.retrieval import search_set

    cases = _cases(args)
    queries = [q for s in args.set for q in load_yaml_list(Path(s), "search.yaml")]
    results = [search_set(cases, queries, r, args.mode) for r in _routes(args, "embed")]
    print(report.write(Path(args.out), f"search-{args.mode}", args.set, results).read_text())


def run_ask(args: argparse.Namespace) -> None:
    from docuhive_evals.retrieval import ask_set

    cases = _cases(args)
    qa = [q for s in args.set for q in load_yaml_list(Path(s), "qa.yaml")]
    embed = next(
        (r.split("=", 1)[1] for r in args.route if r.startswith("embed=")), "ollama/bge-m3"
    )
    results = [ask_set(cases, qa, r, embed) for r in _routes(args, "chat")]
    print(report.write(Path(args.out), "ask", args.set, results).read_text())


def export_golden(args: argparse.Namespace) -> None:
    """Export documents whose fields were all user-confirmed (needs OA's documents service)."""
    import yaml
    from docuhive import documents
    from docuhive.review import pending_for

    out = Path(args.out)
    (out / "docs").mkdir(parents=True, exist_ok=True)
    by_type: dict[str, list] = {}
    for doc_id in documents.iter_ids():
        v = documents.get(doc_id)
        confirmed = {"category", "document_type"} <= set(v.manual_fields)
        if not args.reviewed or (confirmed and not pending_for(doc_id)):
            by_type.setdefault(v.document_type or "other", []).append(v)
    picked: list = []
    while len(picked) < args.n and any(by_type.values()):  # stratify by document type
        for views in by_type.values():
            if views and len(picked) < args.n:
                picked.append(views.pop(0))
    labels = []
    for v in picked:
        (out / "docs" / f"{v.id}.txt").write_text(documents.get_content(v.id), encoding="utf-8")
        labels.append(
            {
                "id": v.id,
                "file": f"docs/{v.id}.txt",
                "expect": {
                    "category": v.category,
                    "document_type": v.document_type,
                    "correspondent": v.correspondent,
                    "document_date": v.document_date.isoformat() if v.document_date else None,
                    "language": v.language,
                    "tags": v.tags,
                    "facts": {
                        k: (
                            {"value": f.value, "currency": f.currency}
                            if f.type == "money"
                            else f.value
                        )
                        for k, f in v.facts.items()
                    },
                },
                "restricted": False,
            }
        )
    (out / "labels.yaml").write_text(yaml.safe_dump(labels, sort_keys=False, allow_unicode=True))
    print(json.dumps({"exported": len(labels), "out": str(out)}))


def register(subs: argparse._SubParsersAction) -> None:
    ev = subs.add_parser("eval", help="Evaluate agents on labelled sets").add_subparsers(
        dest="eval_cmd", required=True
    )

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--set", action="append", required=True, help="eval set folder")
        p.add_argument("--route", action="append", default=[], help="task=provider/model")
        p.add_argument("--limit", type=int)
        p.add_argument("--out", default="evals/reports")

    for task in ("classify", "extract"):
        p = ev.add_parser(task)
        common(p)
        p.add_argument("--concurrency", type=int, default=1)
        p.set_defaults(func=run_task, task=task)
    s = ev.add_parser("search")
    common(s)
    s.add_argument("--mode", choices=["hybrid", "fts", "semantic"], default="semantic")
    s.set_defaults(func=run_search)
    a = ev.add_parser("ask")
    common(a)
    a.set_defaults(func=run_ask)
    g = ev.add_parser("export-golden")
    g.add_argument("--reviewed", action="store_true")
    g.add_argument("--n", type=int, default=100)
    g.add_argument("--out", required=True)
    g.set_defaults(func=export_golden)
