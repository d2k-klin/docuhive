"""Command-line entry points for the platform and optional intelligence extensions."""

import argparse
import getpass
import json
import logging
from importlib import import_module

from docuhive import __version__
from docuhive.config.settings import get_settings


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
    vault = subs.add_parser("vault", help="Check the vault without changing it")
    vault.add_argument("action", choices=["check"])
    vault.add_argument("--full", action="store_true", help="Also verify every original's SHA-256")
    subs.add_parser("openapi", help="Print the OpenAPI schema")
    spike = subs.add_parser("spike", help="Measure conversion and OCR before selecting a backend")
    spike_sub = spike.add_subparsers(dest="spike_action", required=True)
    ingest = spike_sub.add_parser("ingest")
    ingest.add_argument("input_dir")
    ingest.add_argument("--out", required=True)
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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        get_settings()
        if args.command == "api":
            import uvicorn

            uvicorn.run(
                "docuhive.api.app:create_app",
                factory=True,
                host=args.host,
                port=args.port,
                reload=args.reload,
            )
        elif args.command == "worker":
            from docuhive.worker import serve

            serve([q.strip() for q in args.queues.split(",") if q.strip()], args.concurrency)
        elif args.command == "db":
            from docuhive.db.migrations import migrate

            if args.action == "downgrade" and get_settings().env == "prod":
                root.error("Database downgrades are only allowed in development/test")
            migrate(args.action, args.revision)
        elif args.command == "vault":
            from docuhive.vault.health import scan

            result = scan(full=args.full)
            print(result.model_dump_json(indent=2))
            if not result.ok:
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
