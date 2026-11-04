"""A durable-work contract demonstration with a fake queue; no database or AI needed."""

from docuhive.jobs import JobContext


def main() -> None:
    # A tiny producer fake keeps this example standalone; production enqueue uses PostgreSQL.
    pending: dict[str, dict] = {}

    def enqueue(kind: str, payload: dict, dedupe_key: str) -> str:
        pending.setdefault(dedupe_key, {"kind": kind, "payload": payload})
        return dedupe_key

    first = enqueue("document.stored", {"document_id": "synthetic"}, "stored:synthetic")
    second = enqueue("document.stored", {"document_id": "synthetic"}, "stored:synthetic")
    assert first == second and len(pending) == 1
    assert hasattr(JobContext, "heartbeat") and hasattr(JobContext, "defer")
    print("Two deliveries, one pending job. Workers must still make side effects idempotent.")


if __name__ == "__main__":
    main()
