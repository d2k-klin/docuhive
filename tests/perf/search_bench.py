"""Measure actual search, refusing undersized or unapproved reference data."""

import json
import math
import ssl
import statistics
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


def percentile(values: list[float], fraction: float) -> float:
    if not values or not 0 < fraction <= 1:
        raise ValueError("A percentile needs samples and a fraction in (0, 1]")
    return sorted(values)[math.ceil(len(values) * fraction) - 1]


def main() -> None:
    with httpx.Client(
        base_url="https://127.0.0.1:58000",
        verify=ssl.create_default_context(cafile=ROOT / "tmp/qa/tls/cert.pem"),
        timeout=30,
        trust_env=False,
        headers={"X-DocuHive-CSRF": "1"},
    ) as client:
        response = client.post(
            "/api/auth/login", json={"username": "alice", "password": "synthetic qa password 2026"}
        )
        response.raise_for_status()
        listing = client.get("/api/documents", params={"limit": 1})
        listing.raise_for_status()
        if listing.json().get("total", 0) < 20000:
            raise ValueError("Search benchmark requires 20,000 seeded documents; no score recorded")
        results = {}
        for mode in ("fts", "hybrid"):
            times = []
            for i in range(105):
                start = time.perf_counter()
                response = client.get("/api/search", params={"q": "Rechnung", "mode": mode})
                response.raise_for_status()
                if i >= 5:
                    times.append((time.perf_counter() - start) * 1000)
            results[mode] = {
                "p50_ms": statistics.median(times),
                "p95_ms": percentile(times, 0.95),
                "samples": len(times),
            }
        output = ROOT / "tmp/qa/search-bench.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, indent=2) + "\n")
        baseline = json.loads((ROOT / "tests/perf/baselines.json").read_text())
        for mode, values in results.items():
            if values["p95_ms"] >= 500:
                raise ValueError(f"{mode}: search p95 exceeds 500 ms")
            if baseline["approved"] and values["p95_ms"] > baseline["search_p95_ms"] * 1.2:
                raise ValueError(f"{mode}: search regressed more than 20%")
        if not baseline["approved"]:
            raise ValueError("Trend measured, but reference-host baseline still needs approval")


if __name__ == "__main__":
    main()
