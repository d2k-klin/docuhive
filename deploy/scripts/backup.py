"""Quiesced database + vault + staging backups. Run on the Linux Docker host."""

import fcntl
import json
import os
import shlex
import stat
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRITERS = {"api", "worker", "worker-ocr"}


def command(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
    # Output may contain repository credentials; keep it out of status files and UI.
    return subprocess.run(args, check=True, stderr=subprocess.PIPE, **kwargs)


def atomic_json(path: Path, value: dict) -> None:
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".backup-status-")
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(value, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def mounted(vault: Path, expected: str) -> None:
    if not expected or (vault / "_system" / "VAULT_ID").read_text().strip() != expected:
        raise ValueError("Mount the registered vault before backing up")


def backup(now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    vault = Path(os.environ["DOCUHIVE_VAULT_HOST_DIR"]).resolve()
    staging = Path(os.environ["DOCUHIVE_STAGING_HOST_DIR"]).resolve()
    expected = os.environ["DOCUHIVE_VAULT_ID"]
    mounted(vault, expected)
    if not staging.is_dir() or staging.is_relative_to(vault) or vault.is_relative_to(staging):
        raise ValueError("Use the existing SSD staging directory outside the vault")
    password = Path(os.environ["RESTIC_PASSWORD_FILE"])
    if not password.is_file() or stat.S_IMODE(password.stat().st_mode) & 0o077:
        raise ValueError("RESTIC_PASSWORD_FILE must be a private file (mode 600)")
    repositories = shlex.split(os.environ["RESTIC_REPOSITORIES"])
    if not repositories:
        raise ValueError("Configure at least one restic repository")
    for repository in repositories:
        target = Path(repository).resolve()
        if ":" not in repository and (
            target.is_relative_to(vault) or target.is_relative_to(staging)
        ):
            raise ValueError("The backup repository must be outside the source directories")
    version = command(["restic", "version"], stdout=subprocess.PIPE).stdout.decode().split()
    if version[:2] != ["restic", "0.18.1"]:
        raise ValueError("Install the pinned restic 0.18.1 before running backups")
    compose = [
        "docker",
        "compose",
        "--env-file",
        os.environ["DOCUHIVE_PROD_ENV"],
        "-f",
        str(ROOT / "deploy/compose.yml"),
    ]
    status_path = vault / "_system" / "backup-status.json"
    try:
        previous = json.loads(status_path.read_text())
        if not isinstance(previous, dict):
            previous = {}
    except (OSError, ValueError):
        previous = {}
    result = {
        "at": now.isoformat(),
        "ok": False,
        "last_success": previous.get("last_success"),
        "targets": [],
        "error": None,
    }
    running = (
        command([*compose, "ps", "--status", "running", "--services"], stdout=subprocess.PIPE)
        .stdout.decode()
        .split()
    )
    writers = sorted(WRITERS.intersection(running))
    step = "pause"
    try:
        if writers:
            command([*compose, "stop", "-t", "90", *writers], stdout=subprocess.DEVNULL)
        mounted(vault, expected)
        step = "dump"
        dumps = vault / "_system" / "db"
        dumps.mkdir(exist_ok=True)
        destination = dumps / f"docuhive-{now.strftime('%Y%m%dT%H%M%S%fZ')}.dump"
        temporary = destination.with_suffix(".partial")
        try:
            with temporary.open("wb") as out:
                command(
                    [
                        *compose,
                        "exec",
                        "-T",
                        "postgres",
                        "pg_dump",
                        "-U",
                        "docuhive",
                        "-d",
                        "docuhive",
                        "-Fc",
                    ],
                    stdout=out,
                )
                out.flush()
                os.fsync(out.fileno())
            with temporary.open("rb") as source:
                command(
                    [*compose, "exec", "-T", "postgres", "pg_restore", "--list"],
                    stdin=source,
                    stdout=subprocess.DEVNULL,
                )
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        step = "backup"
        for index, repository in enumerate(repositories):
            target = {"target": index + 1, "ok": False}
            result["targets"].append(target)
            args = ["restic", "-r", repository]
            command(
                [
                    *args,
                    "backup",
                    "--tag",
                    "docuhive",
                    "--exclude",
                    str(vault / "library"),
                    str(vault),
                    str(staging),
                ],
                stdout=subprocess.DEVNULL,
            )
            if now.weekday() == 6:
                command(
                    [
                        *args,
                        "forget",
                        "--tag",
                        "docuhive",
                        "--keep-daily",
                        "7",
                        "--keep-weekly",
                        "8",
                        "--keep-monthly",
                        "24",
                        "--prune",
                    ],
                    stdout=subprocess.DEVNULL,
                )
            if now.day == 1:
                command([*args, "check", "--read-data-subset=5%"], stdout=subprocess.DEVNULL)
            target["ok"] = True
        # Only generated dumps are retained; originals and staging are never pruned here.
        for old in sorted(dumps.glob("docuhive-*.dump"), reverse=True)[14:]:
            old.unlink()
        result.update(ok=True, last_success=now.isoformat())
    except (OSError, ValueError, subprocess.SubprocessError):
        result["error"] = f"backup_{step}_failed"
    finally:
        try:
            if writers:
                command([*compose, "start", *writers], stdout=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            result.update(ok=False, error="backup_restart_failed")
        mounted(vault, expected)
        atomic_json(status_path, result)
    return result


def main() -> None:
    os.umask(0o077)
    state = Path(os.environ["DOCUHIVE_BACKUP_STATE_DIR"])
    with (state / "backup.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("A backup is already running") from None
        result = backup()
    print(json.dumps(result))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
