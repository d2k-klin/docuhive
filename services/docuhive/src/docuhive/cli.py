"""Command-line entry points for the platform and optional intelligence extensions."""

import argparse
import copy
import getpass
import json
import logging
import os
import re
from importlib import import_module

from docuhive import __version__
from docuhive.config.settings import get_settings

# A key that names a secret, then `=` or `:`, then its whole value: a quoted string (escapes
# included), an auth scheme plus its credential (`Bearer …`, `Basic …`), or a bare word up to
# the next separator (`password=…`, `"token": "…"`, `dh_session=…`).
SECRET = re.compile(
    r"(?i)\b(\w*(?:password|passwd|token|secret|authorization|api_?key|session|cookie))\b"
    r"([\"']?\s*[:=]\s*)"
    r"(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'"
    r"|(?:(?:bearer|basic|digest|token)\s+)?[^\s\"',;&}]+)"
)

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def redact(text: str) -> str:
    def mask(match: re.Match[str]) -> str:
        quote = match[3][0] if match[3][0] in "\"'" else ""
        return f"{match[1]}{match[2]}{quote}[redacted]{quote}"

    return SECRET.sub(mask, text)


class Redact(logging.Filter):
    """Masks secret values in every log line before any handler writes it.

    Arguments are redacted one by one when that suffices, so formatters that unpack them
    (uvicorn's access log) keep working; otherwise the line is flattened.
    ponytail: the message only, not tracebacks; scrub exc_text too if a secret ever shows up there.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        clean = redact(message)
        if clean == message:
            return True
        if isinstance(record.args, tuple):
            args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
            msg = redact(str(record.msg))
            try:
                if msg % args == clean:
                    record.msg, record.args = msg, args
                    return True
            except (TypeError, ValueError):
                pass
        record.msg, record.args = clean, None
        return True


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="docuhive")
    root.add_argument("--version", action="version", version=__version__)
    subs = root.add_subparsers(dest="command", required=True)
    api = subs.add_parser("api", help="Run the HTTP API")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", default=8000, type=int)
    api.add_argument("--reload", action="store_true")
    worker = subs.add_parser("worker", help="Run durable background jobs")
    worker.add_argument("--queues", default="default,ai,mail")
    worker.add_argument("--concurrency", type=int, default=4)
    db = subs.add_parser("db", help="Manage both database migration tracks")
    db.add_argument("action", choices=["upgrade", "downgrade", "current"])
    db.add_argument("revision", nargs="?")
    user = subs.add_parser("user", help="Create users or manage passwords")
    user.add_argument("action", choices=["create", "passwd", "disable"])
    user.add_argument("username")
    user.add_argument("--admin", action="store_true")
    vault = subs.add_parser("vault", help="Create, check or arrange the vault")
    vault.add_argument("action", choices=["init", "check", "rebuild", "migrate", "library-sync"])
    vault.add_argument("--dry-run", action="store_true", help="rebuild: only validate meta.json")
    vault.add_argument("--full", action="store_true", help="Also verify every original's SHA-256")
    ingest = subs.add_parser("ingest", help="Add files to the archive, like an upload")
    ingest.add_argument("files", nargs="+")
    ingest.add_argument("--owner", required=True, help="Username of the owner")
    ingest.add_argument("--private", action="store_true", help="Do not share with the household")
    ingest.add_argument("--combine", action="store_true", help="Several photos as one document")
    subs.add_parser("openapi", help="Print the OpenAPI schema")
    spike = subs.add_parser("spike", help="Measure conversion and OCR before selecting a backend")
    spike_sub = spike.add_subparsers(dest="spike_action", required=True)
    spike_ingest = spike_sub.add_parser("ingest")
    spike_ingest.add_argument("input_dir")
    spike_ingest.add_argument("--out", required=True)
    try:
        module = import_module("docuhive.ai.cli")
    except ImportError:
        pass
    else:
        module.register(subs)
    return root


def main() -> None:
    root = parser()
    args = root.parse_args()
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    for handler in logging.getLogger().handlers:
        handler.addFilter(Redact())
    try:
        os.umask(int(get_settings().umask, 8))
        if args.command == "api":
            import uvicorn
            from uvicorn.config import LOGGING_CONFIG

            # uvicorn installs its own handlers, also in --reload children that never run the
            # basicConfig above: filter those, and give the root logger a filtered handler too.
            log_config = copy.deepcopy(LOGGING_CONFIG)
            log_config["filters"] = {"redact": {"()": Redact}}
            log_config["formatters"]["plain"] = {"format": LOG_FORMAT}
            log_config["handlers"]["root"] = {
                "class": "logging.StreamHandler",
                "formatter": "plain",
                "stream": "ext://sys.stderr",
            }
            for handler in log_config["handlers"].values():
                handler["filters"] = ["redact"]
            log_config["root"] = {"handlers": ["root"], "level": "INFO"}
            uvicorn.run(
                "docuhive.api.app:create_app",
                factory=True,
                host=args.host,
                port=args.port,
                reload=args.reload,
                log_config=log_config,
            )
        elif args.command == "worker":
            from docuhive.worker import serve

            serve([q.strip() for q in args.queues.split(",") if q.strip()], args.concurrency)
        elif args.command == "db":
            from docuhive.db.migrations import migrate

            if args.action == "downgrade" and get_settings().env == "prod":
                root.error("Database downgrades are only allowed in development/test")
            migrate(args.action, args.revision)
        elif args.command == "vault" and args.action == "init":
            from docuhive import vault

            print(f"Vault ready at {vault.root()} (id {vault.init()})")
        elif args.command == "vault" and args.action in {"rebuild", "migrate"}:
            from docuhive.vault import rebuild

            if args.action == "migrate":
                outcome = rebuild.migrate_files()
                print(json.dumps(outcome, indent=2))
                failed = bool(outcome["errors"])
            else:
                summary = rebuild.rebuild(dry_run=args.dry_run)
                print(summary.model_dump_json(indent=2))
                failed = bool(summary.errors)
            if failed:
                raise SystemExit(1)
        elif args.command == "ingest":
            ingest_files(args)
        elif args.command == "vault":
            if args.action == "library-sync":
                from docuhive.vault.library import sync

                result = sync(retry=True)
                print(json.dumps(result))
                if not result["ok"]:
                    raise SystemExit(1)
            else:
                from docuhive.vault.health import scan

                report = scan(full=args.full)
                print(report.model_dump_json(indent=2))
                if not report.ok:
                    raise SystemExit(1)
        elif args.command == "openapi":
            from docuhive.api.app import create_app

            print(json.dumps(create_app().openapi(), indent=2))
        elif args.command == "user":
            from docuhive.auth import change_password, create_user

            password = None
            if args.action != "disable":
                password = getpass.getpass("Password (at least 12 characters): ")
                if password != getpass.getpass("Confirm password: "):
                    root.error("Passwords do not match")
            if args.action == "create":
                create_user(args.username, password or "", admin=args.admin)
            else:
                change_password(args.username, password)
        elif args.command == "spike":
            from pathlib import Path

            from docuhive.ingest.spike import run_spike

            run_spike(Path(args.input_dir), Path(args.out))
        elif hasattr(args, "func"):
            args.func(args)
    except (ValueError, FileNotFoundError) as error:
        root.error(str(error))


def ingest_files(args: argparse.Namespace) -> None:
    """Copies the files into staging, so the originals on disk stay where they are."""
    import shutil
    import uuid
    from pathlib import Path

    from sqlalchemy import select

    from docuhive import db, ingest
    from docuhive.contracts import IngestRequest, SourceInfo, SourceKind
    from docuhive.db.models import User

    with db.session() as session:
        owner = session.scalar(select(User.id).where(User.username == args.owner))
    if owner is None:
        raise ValueError(f"Unknown user: {args.owner}")
    paths = [Path(name) for name in args.files]
    groups = [paths] if args.combine else [[path] for path in paths]
    for group in groups:
        staged: list[Path] = []
        for path in group:
            copy = ingest.incoming_dir() / f"cli-{uuid.uuid4().hex}{path.suffix}"
            shutil.copyfile(path, copy)
            staged.append(copy)
        request = IngestRequest(
            owner_id=owner,
            shared=not args.private,
            combine=args.combine,
            source=SourceInfo(kind=SourceKind.upload, original_filename=group[0].name),
        )
        try:
            result = ingest.submit(staged, request)
        except ingest.IngestRejected as error:
            for copy in staged:
                copy.unlink(missing_ok=True)
            print(f"{group[0].name}: rejected ({error})")
            continue
        print(f"{group[0].name}: {result.status} {result.document_id}")
