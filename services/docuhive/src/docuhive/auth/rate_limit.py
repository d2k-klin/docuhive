"""Failed-login windows using monotonic time and bounded cleanup."""

import threading
import time
from collections import defaultdict, deque


class LoginLimiter:
    # shortcut: limits are per process; use a DB-backed limiter before scaling API replicas.
    def __init__(self) -> None:
        self.failures: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def _prune(self, now: float) -> None:
        for key in list(self.failures):
            times = self.failures[key]
            while times and times[0] <= now - 900:
                times.popleft()
            if not times:
                del self.failures[key]

    def allowed(self, username: str, ip: str) -> bool:
        with self.lock:
            self._prune(time.monotonic())
            return (
                len(self.failures.get(f"user:{username}", ())) < 5
                and len(self.failures.get(f"ip:{ip}", ())) < 20
            )

    def failed(self, username: str, ip: str) -> None:
        with self.lock:
            now = time.monotonic()
            self._prune(now)
            self.failures[f"user:{username}"].append(now)
            self.failures[f"ip:{ip}"].append(now)
