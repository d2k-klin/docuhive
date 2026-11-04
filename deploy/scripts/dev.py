"""Run the three development processes and shut down the entire process groups together."""

import os
import signal
import subprocess
import time
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    commands = [
        ["uv", "run", "docuhive", "api", "--reload"],
        [
            "uv",
            "run",
            "docuhive",
            "worker",
            "--queues",
            "ocr,ai,mail,default",
            "--concurrency",
            "4",
        ],
        ["npm", "run", "dev", "--workspace", "apps/web"],
    ]
    processes: list[subprocess.Popen] = []
    stopped = False

    def stop(*args) -> None:
        nonlocal stopped
        stopped = True

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, stop)
    code = 0
    try:
        for command in commands:
            processes.append(subprocess.Popen(command, start_new_session=True))
        while not stopped:
            failures = [p.returncode for p in processes if p.poll() is not None]
            if failures:
                code = failures[0] or 0
                break
            time.sleep(0.2)
    finally:
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        deadline = time.monotonic() + 30
        for process in processes:
            try:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
