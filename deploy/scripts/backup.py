"""Quiesced database + vault + staging backups. Run on the Linux Docker host.

What to back up, when, and how long to keep it come from `_system/backup.json`, which
administrators edit in the app (Storage health → Backup). Where backups go and the password stay
in backup.env on this host. `--when-due` (the timer) runs only when the schedule or a "back up
now" request says so.
"""

import fcntl
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRITERS = {"api", "worker", "worker-ocr"}
DEFAULTS: dict = {
    "time": "03:00",
    "days": [0, 1, 2, 3, 4, 5, 6],
    "keep": {"daily": 7, "weekly": 8, "monthly": 24, "dumps": 14},
    "check_percent": 5,
    "include": {"staging": True, "plugins": True, "linked_folders": False},
    "linked_paths": [],
}
LIMITS = {"daily": (1, 365), "weekly": (0, 520), "monthly": (0, 240), "dumps": (1, 365)}


def options(vault: Path) -> dict:
    """The app's choices, each checked; anything missing or wrong keeps its default, so a bad
    file can never stop the backup."""
    try:
        chosen = json.loads((vault / "_system" / "backup.json").read_text())
        if not isinstance(chosen, dict):
            chosen = {}
    except (OSError, ValueError):
        chosen = {}
    out = json.loads(json.dumps(DEFAULTS))
    try:
        time.fromisoformat(str(chosen.get("time")))
        out["time"] = str(chosen["time"])
    except ValueError:
        pass
    days = chosen.get("days")
    if isinstance(days, list) and days and all(d in range(7) for d in days):
        out["days"] = sorted(set(days))
    for key, (low, high) in LIMITS.items():
        value = (chosen.get("keep") or {}).get(key)
        if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high:
            out["keep"][key] = value
    percent = chosen.get("check_percent")
    if isinstance(percent, int) and not isinstance(percent, bool) and 0 <= percent <= 100:
        out["check_percent"] = percent
    for key in out["include"]:
        value = (chosen.get("include") or {}).get(key)
        if isinstance(value, bool):
            out["include"][key] = value
    paths = chosen.get("linked_paths")
    if isinstance(paths, list):
        out["linked_paths"] = [p for p in paths if isinstance(p, str)]
    return out


def parse(value: object) -> datetime | None:
    try:
        found = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return found if found.tzinfo else None


def due(now: datetime, chosen: dict, status: dict, requested: bool) -> bool:
    """A request, or a scheduled start that has passed with no attempt since (also after the
    host was off at that time)."""
    if requested:
        return True
    local = now.astimezone()
    at = time.fromisoformat(chosen["time"])
    starts = [
        datetime.combine((local - timedelta(days=back)).date(), at, tzinfo=local.tzinfo)
        for back in range(8)
    ]
    passed = [s for s in starts if s <= local and s.weekday() in chosen["days"]]
    if not passed:
        return False
    attempted = parse(status.get("at"))
    return attempted is None or attempted < max(passed)


def extra_sources(vault: Path, staging: Path, chosen: dict) -> tuple[list[Path], list[str]]:
    """Plugins and linked folders, each only from where it is allowed to be."""
    sources: list[Path] = []
    included: list[str] = []
    plugins = os.environ.get("DOCUHIVE_PLUGINS_HOST_DIR")
    if chosen["include"]["plugins"] and plugins and Path(plugins).is_dir():
        sources.append(Path(plugins).resolve())
        included.append("plugins")
    storage = os.environ.get("DOCUHIVE_STORAGE_ROOT_HOST_DIR")
    if chosen["include"]["linked_folders"] and storage:
        allowed = Path(storage).resolve()
        linked = []
        for raw in chosen["linked_paths"]:
            path = Path(raw)
            if not path.is_absolute() or path.is_symlink() or not path.is_dir():
                continue
            path = path.resolve()
            # Only folders inside the storage folder, never the vault or staging themselves.
            if not path.is_relative_to(allowed) or any(
                path.is_relative_to(p) or p.is_relative_to(path) for p in (vault, staging)
            ):
                continue
            linked.append(path)
        sources += linked
        if linked:
            included.append(f"linked:{len(linked)}")
    return sources, included


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
    try:
        found = (vault / "_system" / "VAULT_ID").read_text().strip()
    except OSError:
        found = ""
    if not expected or found != expected:
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
    chosen = options(vault)
    (vault / "_system" / "backup-request.json").unlink(missing_ok=True)
    sources = [vault] + ([staging] if chosen["include"]["staging"] else [])
    included = ["vault", "database"] + (["staging"] if chosen["include"]["staging"] else [])
    extra, more = extra_sources(vault, staging, chosen)
    sources += extra
    included += more
    result = {
        "at": now.isoformat(),
        "ok": False,
        "last_success": previous.get("last_success"),
        "last_prune": previous.get("last_prune"),
        "last_check": previous.get("last_check"),
        "targets": [],
        "included": included,
        "error": None,
    }
    atomic_json(status_path, previous | {"running_since": now.isoformat()})
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
                    *[str(p) for p in sources],
                ],
                stdout=subprocess.DEVNULL,
            )
            last_prune = parse(previous.get("last_prune"))
            if last_prune is None or now - last_prune >= timedelta(days=7):
                result["last_prune"] = now.isoformat()
                command(
                    [
                        *args,
                        "forget",
                        "--tag",
                        "docuhive",
                        "--keep-daily",
                        str(chosen["keep"]["daily"]),
                        "--keep-weekly",
                        str(chosen["keep"]["weekly"]),
                        "--keep-monthly",
                        str(chosen["keep"]["monthly"]),
                        "--prune",
                    ],
                    stdout=subprocess.DEVNULL,
                )
            last_check = parse(previous.get("last_check"))
            if chosen["check_percent"] and (
                last_check is None or now - last_check >= timedelta(days=28)
            ):
                result["last_check"] = now.isoformat()
                command(
                    [*args, "check", f"--read-data-subset={chosen['check_percent']}%"],
                    stdout=subprocess.DEVNULL,
                )
            target["ok"] = True
        # Only generated dumps are retained; originals and staging are never pruned here.
        for old in sorted(dumps.glob("docuhive-*.dump"), reverse=True)[chosen["keep"]["dumps"] :]:
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
        if "--when-due" in sys.argv[1:]:
            vault = Path(os.environ["DOCUHIVE_VAULT_HOST_DIR"]).resolve()
            try:
                status = json.loads((vault / "_system" / "backup-status.json").read_text())
            except (OSError, ValueError):
                status = {}
            requested = (vault / "_system" / "backup-request.json").is_file()
            if not due(datetime.now(UTC), options(vault), status, requested):
                return  # not yet: the timer asks again in a quarter of an hour
        try:
            result = backup()
        except ValueError as error:  # a refusal (wrong or missing vault), not a crash
            raise SystemExit(str(error)) from None
    print(json.dumps(result))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
