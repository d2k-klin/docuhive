"""CL subcommands for the `docuhive` CLI: ai check, taxonomy check, index rebuild, mail gen-key,
and `eval ...` (from the evals package when installed)."""

import argparse
import sys
from pathlib import Path


def ai_check(args: argparse.Namespace) -> None:
    from docuhive.ai import routing
    from docuhive.ai.router import parse_route
    from docuhive.ai.routes import reachable
    from docuhive.ai.settings import get_ai_settings

    cfg = routing.load()  # raises with the failing path if routing.yaml is invalid
    print(f"AI enabled: {get_ai_settings().enabled}   local_only: {cfg.privacy.local_only}")
    print("\nRouting (task -> routes, * = local):")
    for task, t in cfg.tasks.items():
        routes = [parse_route(r, cfg) for r in [t.route, *t.fallback]]
        print(f"  {task:9} " + " -> ".join(f"{r}{'*' if r.local else ''}" for r in routes))
    print("\nProviders:")
    failed = False
    used = {
        parse_route(r, cfg).provider for t in cfg.tasks.values() for r in [t.route, *t.fallback]
    }
    for name, p in cfg.providers.items():
        if not p.enabled or name not in used:
            print(f"  {name:10} {'disabled' if not p.enabled else 'not routed'}")
            continue
        ok, note = reachable(name)
        if ok and args.ping and not p.local:
            ok, note = _ping(name, cfg)
        failed |= not ok
        print(
            f"  {name:10} {'ok ' if ok else 'FAIL'} {note}"
            + (" (experimental)" if p.experimental else "")
        )
    if failed:
        sys.exit(1)


def _ping(provider: str, cfg) -> tuple[bool, str]:  # type: ignore[no-untyped-def]
    """A tiny completion against the first route that uses this provider."""
    from strands import Agent

    from docuhive.ai.router import model_for, parse_route

    spec = next(
        (
            r
            for t in cfg.tasks.values()
            for r in [t.route, *t.fallback]
            if r.startswith(f"{provider}/")
        ),
        None,
    )
    if spec is None:
        return True, "not routed"
    try:
        Agent(model=model_for(parse_route(spec, cfg)), callback_handler=None)("Reply with: ok")
        return True, f"{spec} answered"
    except Exception as e:  # noqa: BLE001 - this is a diagnostic
        return False, f"{spec}: {type(e).__name__}: {e}"


def taxonomy_check(args: argparse.Namespace) -> None:
    import yaml

    from docuhive import config, taxonomy
    from docuhive.config.settings import get_settings

    default = taxonomy.validate(
        yaml.safe_load((get_settings().defaults_dir / "taxonomy.yaml").read_text())
    )
    raw = (
        yaml.safe_load(Path(args.path).read_text())
        if args.path
        else config.load_yaml("taxonomy.yaml")
    )
    tax = taxonomy.validate(raw)
    print(
        f"OK: {len(tax.categories)} categories, {len(tax.document_types)} document types, "
        f"{len(tax.tags)} tags, languages {tax.languages}"
    )
    for kind, a, b in (
        ("category", default.categories, tax.categories),
        ("document type", default.document_types, tax.document_types),
    ):
        old, new = {x.id for x in a}, {x.id for x in b}
        for i in sorted(new - old):
            print(f"  + {kind} {i}")
        for i in sorted(old - new):
            print(f"  - {kind} {i}")
    for t in sorted(set(tax.tags) - set(default.tags)):
        print(f"  + tag {t}")
    for t in sorted(set(default.tags) - set(tax.tags)):
        print(f"  - tag {t}")


def index_rebuild(args: argparse.Namespace) -> None:
    from docuhive.index.jobs import rebuild

    print(f"Queued index.embed for {rebuild(missing_only=args.missing_only)} documents")


def mail_gen_key(args: argparse.Namespace) -> None:
    from cryptography.fernet import Fernet

    print(Fernet.generate_key().decode())


def register(subs: argparse._SubParsersAction) -> None:
    ai = subs.add_parser("ai", help="AI providers and routing").add_subparsers(
        dest="ai_cmd", required=True
    )
    check = ai.add_parser("check", help="Show the effective routing and ping providers")
    check.add_argument("--ping", action="store_true", help="tiny completion on cloud providers")
    check.set_defaults(func=ai_check)
    tax = subs.add_parser("taxonomy", help="Taxonomy tools").add_subparsers(
        dest="tax_cmd", required=True
    )
    tc = tax.add_parser("check", help="Validate a taxonomy file and diff it against the default")
    tc.add_argument("path", nargs="?")
    tc.set_defaults(func=taxonomy_check)
    idx = subs.add_parser("index", help="Semantic index").add_subparsers(
        dest="index_cmd", required=True
    )
    rb = idx.add_parser("rebuild", help="Re-embed documents (initial backfill or model change)")
    rb.add_argument("--missing-only", action="store_true")
    rb.set_defaults(func=index_rebuild)
    mail = subs.add_parser("mail", help="Mail connectors").add_subparsers(
        dest="mail_cmd", required=True
    )
    mail.add_parser("gen-key", help="Print a new DOCUHIVE_MAIL_TOKEN_KEY").set_defaults(
        func=mail_gen_key
    )
    try:
        from docuhive_evals.cli import register as register_evals  # type: ignore[import-untyped]
    except ModuleNotFoundError:
        return
    register_evals(subs)
