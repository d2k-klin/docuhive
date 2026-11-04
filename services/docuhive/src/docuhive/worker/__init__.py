"""Threaded worker with bounded graceful shutdown and scheduler failover."""

import logging
import signal
import threading
import time
from importlib import import_module

from sqlalchemy import text

from docuhive.config.settings import get_settings
from docuhive.db import get_engine
from docuhive.jobs import scheduler
from docuhive.jobs.runner import claim, reap, run
from docuhive.startup import start_intelligence
from docuhive.worker.handlers import HANDLER_MODULES

log = logging.getLogger(__name__)


def _consume(queues: list[str], stopped: threading.Event) -> None:
    while not stopped.is_set():
        try:
            job = claim(queues)
            if job:
                run(job)
            else:
                stopped.wait(0.5)
        except Exception:
            log.exception("Worker could not process the queue")
            stopped.wait(5)


def _schedule(queues: list[str], stopped: threading.Event) -> None:
    while not stopped.is_set():
        try:
            with get_engine().connect() as connection:
                leader = scheduler.acquire(connection)
                connection.commit()
                try:
                    while leader and not stopped.is_set():
                        # Detect a lost connection before doing any leader-only work.
                        connection.execute(text("SELECT 1"))
                        connection.commit()
                        scheduler.tick()
                        reap()
                        stopped.wait(30)
                finally:
                    if leader:
                        scheduler.release(connection)
        except Exception:
            log.exception("Scheduler connection failed; leadership will be reacquired")
        stopped.wait(5)


def serve(queues: list[str], concurrency: int) -> None:
    get_settings()
    if concurrency < 1 or not queues:
        raise ValueError("Worker requires queues and positive concurrency")
    for module in HANDLER_MODULES:
        import_module(module)
    start_intelligence()
    stopped = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopped.set())
    threads = [
        threading.Thread(target=_consume, args=(queues, stopped), daemon=True)
        for _ in range(concurrency)
    ]
    threads.append(threading.Thread(target=_schedule, args=(queues, stopped), daemon=True))
    for thread in threads:
        thread.start()
    stopped.wait()
    deadline = time.monotonic() + 30
    for thread in threads:
        thread.join(timeout=max(0, deadline - time.monotonic()))
