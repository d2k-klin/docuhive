"""Events with many listeners: every subscriber gets its own job, retries and failures.

Core emit sites keep calling `jobs.enqueue("document.stored", …)`; `jobs.enqueue` fans the
event out here, in the same transaction, so a listener can never miss an event that happened
or see one that was rolled back.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

# Events plugins may listen to (plugins may also emit "<plugin id>.<name>" for each other).
CORE_EVENTS = (
    "document.stored",
    "document.classified",
    "document.metadata_changed",
    "document.trashed",
    "document.restored",
    "document.quarantined",
    "review.accepted",
)
ALIASES = {"document.changed": "document.metadata_changed"}  # the name the plugin guide uses

SUBSCRIBERS: dict[str, list[str]] = {}  # event -> subscriber job kinds
QUEUES: dict[str, str] = {}


@dataclass
class Event:
    """What a listener receives: `event.name`, and the payload's keys as attributes."""

    name: str
    payload: dict
    ctx: Any = field(default=None, repr=False)

    def __getattr__(self, key: str) -> Any:
        try:
            return self.payload[key]
        except KeyError:
            raise AttributeError(key) from None


def kind_for(event: str, subscriber: str) -> str:
    return f"event:{subscriber}:{event}"


def subscribe(
    event: str,
    subscriber: str,
    fn: Callable[[Event], None],
    *,
    queue: str = "default",
    timeout_s: int = 600,
) -> str:
    from docuhive import jobs

    event = ALIASES.get(event, event)
    kind = kind_for(event, subscriber)
    jobs.handler(kind, queue=queue, timeout_s=timeout_s)(
        lambda payload, ctx: fn(Event(event, payload, ctx))
    )
    SUBSCRIBERS.setdefault(event, [])
    if kind not in SUBSCRIBERS[event]:
        SUBSCRIBERS[event].append(kind)
    QUEUES[kind] = queue
    return kind


def unsubscribe(kind: str) -> None:
    from docuhive import jobs

    for kinds in SUBSCRIBERS.values():
        if kind in kinds:
            kinds.remove(kind)
    QUEUES.pop(kind, None)
    jobs.HANDLERS.pop(kind, None)


def fan_out(event: str, payload: dict, origin: str, db: Session) -> None:
    from docuhive import jobs

    for kind in SUBSCRIBERS.get(event, []):
        jobs.enqueue(
            kind, payload, queue=QUEUES[kind], dedupe_key=f"{kind}:{origin}", in_session=db
        )


def emit(event: str, payload: dict, *, key: str, in_session: Session | None = None) -> None:
    """An event with no core handler: only its subscribers get a job. `key` identifies this
    occurrence, so emitting it twice (a retried job) does not run a listener twice."""
    from docuhive.db import session

    if not SUBSCRIBERS.get(event):
        return
    if in_session is not None:
        fan_out(event, payload, key, in_session)
        return
    with session() as db:
        fan_out(event, payload, key, db)
