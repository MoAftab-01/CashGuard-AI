"""Small bounded synthetic-only local API load probe; no inference or payload logs."""

import argparse
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from uuid import uuid4

import numpy as np

from config import SAMPLE_DATA_PATH
from src.api_client import ApiClient, ApiClientError
from src.dashboard_backend import DashboardBackend
from src.data_processing import validate_csv
from src.settings import Settings, loopback_url


def run_probe(base_url, *, count=12, concurrency=3, token=None):
    base_url = loopback_url(base_url)
    if type(count) is not int or not 1 <= count <= 100 or type(concurrency) is not int or not 1 <= concurrency <= 8:
        raise ValueError("Use 1–100 requests and 1–8 workers")
    imported = validate_csv(SAMPLE_DATA_PATH)
    adapter = DashboardBackend(Settings())
    payload = adapter.payload(imported, "2500.00", as_of=imported.data.date.max(), threshold="500.00",
                              irregular=False, reviewed=False, engine="Calibrated amount review")
    def request(_):
        started = perf_counter()
        with ApiClient(base_url, timeout_seconds=30, token=token, session_id=uuid4().hex) as client:
            try:
                client.call("dashboard", payload)
                status = "200"
            except ApiClientError as exc:
                status = str(exc.status) if exc.status else exc.code
        return status, perf_counter() - started
    started = perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(executor.map(request, range(count)))
    latencies = [seconds for _, seconds in results]
    return {"synthetic_only": True, "inference_executed": False, "requests": count, "concurrency": concurrency,
            "status_counts": dict(Counter(status for status, _ in results)),
            "seconds": perf_counter() - started, "p50_seconds": float(np.percentile(latencies, 50)),
            "p95_seconds": float(np.percentile(latencies, 95)), "max_seconds": max(latencies),
            "scope": "Small local smoke load; not a production capacity benchmark"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=12)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = run_probe(args.api_url, count=args.requests, concurrency=args.concurrency,
                       token=os.getenv("CASHGUARD_API_TOKEN"))
    if args.output:
        from pathlib import Path
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
