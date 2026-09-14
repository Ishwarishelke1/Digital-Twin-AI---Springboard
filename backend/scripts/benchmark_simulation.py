"""
One-off script: benchmarks the Decision Simulation Engine's response latency
against the "results generated within 5 seconds" Milestone 4 deliverable.

Usage (backend must be running, e.g. `python3 -m uvicorn main:app`):
    python3 scripts/benchmark_simulation.py --email you@example.com --password ... [--runs 10]

Logs in via the same POST /auth/login the frontend uses (cookie-based session,
via requests.Session()), then times each of the 4 scenario endpoints plus
/simulation/compare, N times each, and prints p50/p95/max latency per endpoint.
"""
import argparse
import statistics
import sys
import time

import requests

BASE_URL = "http://127.0.0.1:8000/api/v1"

# Small, valid default deltas for each domain's scenario request — timing is
# what's under test here, not scenario correctness (already covered by tests).
SCENARIO_ENDPOINTS = [
    ("POST", "/simulation/finance/scenarios", {"additional_monthly_saving": 200, "expense_reduction_pct": 5}),
    ("POST", "/simulation/study/scenarios", {"additional_weekly_study_hours": 2}),
    ("POST", "/simulation/fitness/scenarios", {"additional_exercise_minutes": 20}),
    ("POST", "/simulation/hybrid/scenarios", {"additional_monthly_saving": 200, "additional_weekly_study_hours": 2}),
    ("GET", "/simulation/compare", None),
]


def percentile(values, pct):
    values = sorted(values)
    k = (len(values) - 1) * pct
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


def main():
    parser = argparse.ArgumentParser(description="Benchmark simulation endpoint latency.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args()

    session = requests.Session()
    login = session.post(f"{BASE_URL}/auth/login", json={"email": args.email, "password": args.password})
    if login.status_code != 200:
        print(f"Login failed ({login.status_code}): {login.text}", file=sys.stderr)
        sys.exit(1)

    print(f"Benchmarking {args.runs} runs per endpoint...\n")
    results = {}
    for method, path, payload in SCENARIO_ENDPOINTS:
        durations = []
        for _ in range(args.runs):
            start = time.perf_counter()
            if method == "POST":
                resp = session.post(f"{BASE_URL}{path}", json=payload)
            else:
                resp = session.get(f"{BASE_URL}{path}")
            elapsed = time.perf_counter() - start
            if resp.status_code >= 400:
                print(f"  ! {path} returned {resp.status_code}: {resp.text[:200]}")
                continue
            durations.append(elapsed)
        results[path] = durations

    print(f"{'Endpoint':<40} {'p50':>8} {'p95':>8} {'max':>8}  (seconds)")
    print("-" * 68)
    overall_max = 0.0
    for path, durations in results.items():
        if not durations:
            print(f"{path:<40} {'—':>8} {'—':>8} {'—':>8}  (all requests failed)")
            continue
        p50, p95, mx = percentile(durations, 0.5), percentile(durations, 0.95), max(durations)
        overall_max = max(overall_max, mx)
        print(f"{path:<40} {p50:>8.3f} {p95:>8.3f} {mx:>8.3f}")

    print()
    verdict = "PASS" if overall_max < 5.0 else "FAIL"
    print(f"Deliverable check — simulation results within 5 seconds: {verdict} (slowest single call: {overall_max:.3f}s)")


if __name__ == "__main__":
    main()
