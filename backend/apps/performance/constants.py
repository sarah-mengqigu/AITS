"""Tunable thresholds and defaults for the performance testing module.

Keeping them in one module makes the pass/fail contract obvious and easy to
assert from tests (``docs/ARCHITECTURE.md`` §2.6).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# quality gates (an execution is ``passed`` only when *all* hold)
# ---------------------------------------------------------------------------
#: Error rate tolerated for a passing run (1%).
ERROR_RATE_THRESHOLD = 0.01

#: P95 latency ceiling used by the AI/rules diagnosis (milliseconds).
P95_RESPONSE_TIME_THRESHOLD_MS = 2000

#: P99 latency ceiling used by the AI/rules diagnosis (milliseconds).
P99_RESPONSE_TIME_THRESHOLD_MS = 5000

#: Average TPS below which a run is considered under-performing (rules only).
MIN_AVG_TPS_THRESHOLD = 1.0

#: Severity bucket boundaries for the rules based diagnosis.
ERROR_RATE_SEVERE = 0.10
ERROR_RATE_WARNING = 0.03

# ---------------------------------------------------------------------------
# simulated runner defaults
# ---------------------------------------------------------------------------
#: Never simulate more than this many sampling points.
MAX_SIMULATED_SAMPLES = 60

#: Time buckets simulated. Each bucket may emit one success and one failure
#: record, therefore ``MAX_SIMULATED_BUCKETS * 2 == MAX_SIMULATED_SAMPLES``.
MAX_SIMULATED_BUCKETS = MAX_SIMULATED_SAMPLES // 2

#: Lower bound of sampling points (keeps short durations readable).
MIN_SIMULATED_SAMPLES = 5

#: Default error rate produced by the simulated runner (well under threshold).
SIMULATED_ERROR_RATE = 0.002

#: Default response time produced by the simulated runner (milliseconds).
SIMULATED_RESPONSE_TIME_MS = 120

#: Requests per virtual user per second used by the simulated model.
SIMULATED_RPS_PER_USER = 2.0

# ---------------------------------------------------------------------------
# load configuration defaults (used when no LoadConfiguration is attached)
# ---------------------------------------------------------------------------
DEFAULT_USERS = 10
DEFAULT_SPAWN_RATE = 5.0
DEFAULT_DURATION_SECONDS = 60
DEFAULT_HOST = "http://127.0.0.1:8000"

# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------
#: Statuses after which an execution can no longer change.
TERMINAL_STATUSES = ("passed", "failed", "error", "cancelled")

#: How long the real runner may wait past the configured duration.
REAL_RUN_TIMEOUT_EXTRA_SECONDS = 120

#: Polling interval while a locust subprocess is running.
REAL_RUN_POLL_INTERVAL = 0.5

#: Cache key remembering the resolved Grafana AI notification receiver id.
NOTIFY_TARGET_CACHE_KEY = "performance:grafana_ai_notify_target"

#: Dashboard default window (days).
DEFAULT_DASHBOARD_DAYS = 7

#: Maximum dashboard window (days).
MAX_DASHBOARD_DAYS = 90
