#!/usr/bin/env python
"""Live smoke check against a running AITS backend.

Usage:
    python scripts/smoke_live.py [--url http://127.0.0.1:8000] [--strict]

Exit codes:
    0  all checks passed, or the server is not running (skipped unless --strict)
    1  a check failed (--strict turns "server not running" into a failure)

The demo account comes from `python manage.py seed_demo`
(`admin` / `Admin@12345`); override with AITS_DEMO_USER / AITS_DEMO_PASSWORD.
"""

from __future__ import annotations

import argparse
import os
import sys

import requests

ENDPOINTS = [
    ("projects", "/api/projects/"),
    ("api specs", "/api/api-testing/specs/"),
    ("api executions", "/api/api-testing/executions/"),
    ("web executions", "/api/web-testing/executions/"),
    ("app runs", "/api/app-testing/runs/"),
    ("perf executions", "/api/performance/executions/"),
    ("perf dashboard", "/api/performance/dashboard/"),
    ("ai models", "/api/ai/llm-configs/"),
    ("ai agents", "/api/ai/agents/"),
    ("scheduled tasks", "/api/scheduled-tasks/tasks/"),
    ("task logs", "/api/scheduled-tasks/logs/"),
    ("notification receivers", "/api/notifications/receivers/"),
    ("notification logs", "/api/notifications/logs/"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get("AITS_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--strict", action="store_true",
                        help="fail when the server is unreachable")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    try:
        health = requests.get(f"{base}/health/", timeout=5)
    except requests.RequestException as exc:
        print(f"↷ backend not reachable at {base} ({exc.__class__.__name__}) - skipped")
        return 1 if args.strict else 0

    if health.status_code != 200 or health.json().get("status") != "ok":
        print(f"✘ health check failed: {health.status_code} {health.text[:200]}")
        return 1
    print(f"✔ health  {health.json()['service']} v{health.json()['version']}")

    username = os.environ.get("AITS_DEMO_USER", "admin")
    password = os.environ.get("AITS_DEMO_PASSWORD", "Admin@12345")
    login = requests.post(f"{base}/api/auth/login/",
                          json={"username": username, "password": password}, timeout=10)
    if login.status_code != 200:
        print(f"✘ login failed ({login.status_code}). Run `manage.py seed_demo` first.")
        print(f"  {login.text[:200]}")
        return 1
    token = login.json()["access"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"✔ login   {username}")

    failures = 0
    for label, path in ENDPOINTS:
        try:
            response = requests.get(f"{base}{path}", headers=headers, timeout=15)
        except requests.RequestException as exc:
            print(f"✘ {label:<24} request error: {exc}")
            failures += 1
            continue
        if response.status_code != 200:
            print(f"✘ {label:<24} {response.status_code} {response.text[:120]}")
            failures += 1
            continue
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        count = payload.get("count") if isinstance(payload, dict) else None
        suffix = f"count={count}" if count is not None else "ok"
        print(f"✔ {label:<24} {suffix}")

    metrics = requests.get(f"{base}/metrics/", timeout=10)
    if metrics.status_code == 200 and b"aits_test_cases_total" in metrics.content:
        print("✔ prometheus metrics exposed")
    else:
        print(f"✘ metrics endpoint: {metrics.status_code}")
        failures += 1

    schema = requests.get(f"{base}/api/schema/", timeout=10)
    if schema.status_code == 200:
        print("✔ openapi schema served")
    else:
        print(f"✘ schema endpoint: {schema.status_code}")
        failures += 1

    if failures:
        print(f"\n{failures} live check(s) failed")
        return 1
    print("\nall live checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
