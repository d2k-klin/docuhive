"""Bound expensive parsing and terminate the entire OCR subprocess group on timeout."""

import multiprocessing
import os
import signal
import traceback
from collections.abc import Callable
from multiprocessing.connection import Connection
from typing import Any

from .errors import Quarantine

MAX_PAGES = 500
MAX_IMAGE_PIXELS = 200_000_000


def _child(connection: Connection, fn: Callable, args: tuple) -> None:
    if os.name == "posix":
        os.setsid()
    try:
        connection.send((True, fn(*args)))
    except Quarantine as error:
        connection.send((False, str(error)))
    except BaseException as error:
        traceback.print_exc()
        connection.send((False, f"{type(error).__name__}: processing failed"))
    finally:
        connection.close()


def isolated(fn: Callable, *args: Any, timeout_s: float = 1800) -> Any:
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_child, args=(child, fn, args))
    process.start()
    child.close()
    try:
        if not parent.poll(timeout_s):
            raise Quarantine("step_timeout")
        try:
            ok, result = parent.recv()
        except EOFError as error:
            raise Quarantine("step_crashed") from error
        if not ok:
            raise Quarantine(result)
        return result
    finally:
        if process.is_alive():
            if os.name == "posix" and process.pid is not None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    process.kill()
            else:
                process.kill()
        process.join(timeout=5)
        parent.close()
