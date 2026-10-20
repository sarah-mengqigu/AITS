"""Statistics helpers for Locust CSV output and generic load samples.

Two entry points are part of the module contract (``ARCHITECTURE`` §2.6):

* :func:`parse_locust_csv` - read a Locust ``*_stats.csv`` /
  ``*_stats_history.csv`` result set from disk.
* :func:`parse_stats_csv_text` - same parsing over text (handy for tests).
* :func:`compute_summary` - aggregate raw ``{elapsed, requests, failures,
  response_time_ms, status_code}`` samples into the metrics stored on
  :class:`apps.performance.models.PerformanceExecution`.

The parser understands the stock Locust schema::

    Type,Name,Request Count,Failure Count,Median Response Time,Average Response
    Time,Min Response Time,Max Response Time,Average Content Size,Requests/s,
    Failures/s,50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%

and the cumulative ``stats_history`` schema (``Timestamp`` + ``Requests`` /
``Failures``).  An optional ``Status Code`` column is honoured so the
simulated runner can report a status code distribution without inventing a
second schema.
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# column aliases (all compared lower-cased / stripped)
# ---------------------------------------------------------------------------
_NAME_KEYS = ("name", "endpoint", "request name")
_REQUEST_KEYS = (
    "request count",
    "total request count",
    "requests",
    "request_count",
    "total requests",
)
_FAILURE_KEYS = (
    "failure count",
    "total failure count",
    "failures",
    "failure_count",
    "total failures",
)
_TPS_KEYS = (
    "requests/s",
    "requests per second",
    "requests/sec",
    "requests_per_second",
    "total requests per second",
    "tps",
)
_P50_KEYS = ("50%", "p50", "median response time", "median_response_time")
_P95_KEYS = ("95%", "p95", "95th percentile", "p95_response_time")
_P99_KEYS = ("99%", "p99", "99th percentile", "p99_response_time")
_STATUS_KEYS = ("status code", "status_code", "statuscode", "http status")
_TIMESTAMP_KEYS = ("timestamp", "time", "elapsed")


# ---------------------------------------------------------------------------
# tiny value coercion helpers
# ---------------------------------------------------------------------------
def _norm(key) -> str:
    return str(key or "").strip().lower()


def _normalise_row(row: dict) -> dict:
    return {_norm(key): value for key, value in row.items() if key is not None}


def _first(row: dict, keys) -> object:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _as_float(value, default=None):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _as_int(value, default=0) -> int:
    number = _as_float(value, default=None)
    if number is None:
        return default
    try:
        return int(round(number))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return default


def _clean_percentile(value):
    number = _as_float(value, default=None)
    if number is None:
        return None
    return int(round(number))


def _clean_status(value):
    if value in (None, ""):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    number = _as_float(text, default=None)
    if number is None:
        return ""
    return str(int(number))


def _empty_summary() -> dict:
    """Zero valued metric dict - the contract for "no data"."""
    return {
        "total_requests": 0,
        "failures": 0,
        "avg_tps": 0.0,
        "p50_response_time": 0,
        "p95_response_time": 0,
        "p99_response_time": 0,
        "error_rate": 0.0,
        "status_code_dist": {},
        "duration_seconds": 0.0,
        "aggregated": [],
    }


def _finalise(summary: dict) -> dict:
    total = max(_as_int(summary.get("total_requests"), 0), 0)
    failures = max(_as_int(summary.get("failures"), 0), 0)
    failures = min(failures, total) if total else failures
    error_rate = round(failures / total, 6) if total else 0.0
    summary["total_requests"] = total
    summary["failures"] = failures
    summary["error_rate"] = error_rate
    summary["avg_tps"] = round(float(summary.get("avg_tps") or 0.0), 2)
    for key in ("p50_response_time", "p95_response_time", "p99_response_time"):
        summary[key] = max(_as_int(summary.get(key), 0), 0)
    summary["duration_seconds"] = round(float(summary.get("duration_seconds") or 0.0), 3)
    summary["status_code_dist"] = {
        str(code): max(_as_int(count, 0), 0)
        for code, count in (summary.get("status_code_dist") or {}).items()
        if str(code).strip()
    }
    summary.setdefault("aggregated", [])
    return summary


# ---------------------------------------------------------------------------
# CSV row parsing
# ---------------------------------------------------------------------------
def _parse_row(raw_row: dict) -> dict | None:
    row = _normalise_row(raw_row)
    if not row:
        return None
    name = str(_first(row, _NAME_KEYS) or "").strip()
    requests = _as_int(_first(row, _REQUEST_KEYS), 0)
    failures = _as_int(_first(row, _FAILURE_KEYS), 0)
    tps = _as_float(_first(row, _TPS_KEYS), None)
    has_metric = any(
        value is not None
        for value in (
            requests,
            failures,
            tps,
            _first(row, _P50_KEYS),
            _first(row, _P95_KEYS),
            _first(row, _P99_KEYS),
            _first(row, _STATUS_KEYS),
        )
    )
    if not has_metric and not name:
        return None
    return {
        "name": name,
        "requests": requests,
        "failures": failures,
        "tps": tps,
        "p50_response_time": _clean_percentile(_first(row, _P50_KEYS)),
        "p95_response_time": _clean_percentile(_first(row, _P95_KEYS)),
        "p99_response_time": _clean_percentile(_first(row, _P99_KEYS)),
        "status_code": _clean_status(_first(row, _STATUS_KEYS)),
        "timestamp": _first(row, _TIMESTAMP_KEYS),
    }


def _read_rows(text: str) -> list:
    if not isinstance(text, str) or not text.strip():
        return []
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
        return [row for row in reader if row and any(v not in (None, "") for v in row.values())]
    except csv.Error as exc:  # pragma: no cover - malformed upload
        logger.warning("stats csv parse failed: %s", exc)
        return []


def _is_history(rows: list) -> bool:
    if not rows:
        return False
    keys = {_norm(key) for key in rows[0].keys() if key is not None}
    return "timestamp" in keys


def _weighted_percentile(entries: list, key: str, percentile: float):
    """Weighted percentile over entries carrying ``key`` (weight = requests)."""
    pairs = []
    for entry in entries:
        value = entry.get(key)
        if value is None:
            continue
        weight = max(_as_int(entry.get("requests"), 0), 1)
        pairs.append((float(value), weight))
    if not pairs:
        return None
    pairs.sort(key=lambda item: item[0])
    total_weight = sum(weight for _, weight in pairs)
    if total_weight <= 0:  # pragma: no cover - defensive
        return None
    threshold = total_weight * (percentile / 100.0)
    cumulative = 0
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= threshold:
            return int(round(value))
    return int(round(pairs[-1][0]))


def parse_stats_csv_text(text: str) -> dict:
    """Parse Locust style CSV text into an aggregated metrics dict.

    Accepts both the ``*_stats.csv`` schema and the cumulative
    ``*_stats_history.csv`` schema. Returns zero values for empty input.
    """
    rows = _read_rows(text)
    if not rows:
        return _empty_summary()

    entries = [entry for entry in (_parse_row(row) for row in rows) if entry]
    if not entries:
        return _empty_summary()

    summary = _empty_summary()
    status_dist: dict[str, int] = {}

    if _is_history(rows):
        # Cumulative snapshots: the *last aggregated* row carries the totals.
        # Locust may interleave per-endpoint rows with the Aggregated row.
        snapshots = [
            entry for entry in entries
            if (entry["name"] or "").strip().lower() == "aggregated"
        ] or entries
        last = snapshots[-1]
        summary["total_requests"] = last["requests"]
        summary["failures"] = last["failures"]
        tps_values = [entry["tps"] for entry in snapshots if entry.get("tps") is not None]
        if tps_values:
            summary["avg_tps"] = sum(tps_values) / len(tps_values)
        summary["p50_response_time"] = last["p50_response_time"] or 0
        summary["p95_response_time"] = last["p95_response_time"] or 0
        summary["p99_response_time"] = last["p99_response_time"] or 0
        # Full snapshots can be long; keep the tail for reports.
        summary["aggregated"] = [
            _entry_payload(entry) for entry in snapshots[-60:]
        ]
    else:
        aggregated = [
            entry for entry in entries
            if (entry["name"] or "").strip().lower() == "aggregated"
        ]
        if aggregated:
            chosen = aggregated[0]
            summary["total_requests"] = chosen["requests"]
            summary["failures"] = chosen["failures"]
            summary["avg_tps"] = chosen["tps"] or 0.0
            summary["p50_response_time"] = chosen["p50_response_time"] or 0
            summary["p95_response_time"] = chosen["p95_response_time"] or 0
            summary["p99_response_time"] = chosen["p99_response_time"] or 0
            if chosen["status_code"]:
                status_dist[chosen["status_code"]] = chosen["requests"]
        else:
            summary["total_requests"] = sum(entry["requests"] for entry in entries)
            summary["failures"] = sum(entry["failures"] for entry in entries)
            summary["avg_tps"] = sum(entry["tps"] or 0.0 for entry in entries)
            summary["p50_response_time"] = _weighted_percentile(entries, "p50_response_time", 50) or 0
            summary["p95_response_time"] = _weighted_percentile(entries, "p95_response_time", 95) or 0
            summary["p99_response_time"] = _weighted_percentile(entries, "p99_response_time", 99) or 0
        for entry in entries:
            code = entry.get("status_code")
            if code and entry["name"].strip().lower() != "aggregated":
                status_dist[code] = status_dist.get(code, 0) + max(entry["requests"], 0)
        summary["aggregated"] = [
            _entry_payload(entry) for entry in entries
            if entry["name"].strip().lower() != "aggregated"
        ]

    summary["status_code_dist"] = status_dist
    if summary["total_requests"] and not summary["avg_tps"]:
        summary["avg_tps"] = 0.0
    return _finalise(summary)


def _entry_payload(entry: dict) -> dict:
    return {
        "name": entry.get("name") or "",
        "requests": entry.get("requests") or 0,
        "failures": entry.get("failures") or 0,
        "avg_tps": round(float(entry.get("tps") or 0.0), 2),
        "p50_response_time": entry.get("p50_response_time") or 0,
        "p95_response_time": entry.get("p95_response_time") or 0,
        "p99_response_time": entry.get("p99_response_time") or 0,
        "status_code": entry.get("status_code") or "",
    }


# ---------------------------------------------------------------------------
# file based parsing
# ---------------------------------------------------------------------------
def _collect_csv_files(path) -> list[Path]:
    if path is None:
        return []
    target = Path(path)
    if target.is_file():
        return [target]
    if not target.is_dir():
        return []
    files = []
    for candidate in sorted(target.glob("*.csv")):
        if candidate.is_file():
            files.append(candidate)
    return files


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:  # pragma: no cover - unreadable artifact
        logger.warning("cannot read stats csv %s: %s", path, exc)
        return ""


def _merge_status_dist(target: dict, source: dict) -> None:
    for code, count in (source or {}).items():
        target[str(code)] = target.get(str(code), 0) + max(_as_int(count, 0), 0)


def parse_locust_csv(path) -> dict:
    """Parse a Locust CSV result set (file **or** containing directory).

    ``*_stats.csv`` provides the authoritative aggregate; ``*_stats_history.csv``
    fills in missing TPS / percentile values. Any ``*status*.csv`` file
    contributes a status code distribution.
    """
    files = _collect_csv_files(path)
    if not files:
        logger.warning("no locust csv artifacts under %s", path)
        return _empty_summary()

    stats_files = [f for f in files if "history" not in f.name.lower()
                   and "status" not in f.name.lower()]
    history_files = [f for f in files if "history" in f.name.lower()]
    status_files = [f for f in files if "status" in f.name.lower()]

    result = None
    for candidate in stats_files:
        parsed = parse_stats_csv_text(_read_text(candidate))
        if parsed["total_requests"] or parsed["aggregated"]:
            result = parsed
            break
    if result is None:
        result = _empty_summary()

    history = _empty_summary()
    for candidate in history_files:
        parsed = parse_stats_csv_text(_read_text(candidate))
        if parsed["total_requests"] or parsed["aggregated"]:
            history = parsed
            break

    if history["total_requests"]:
        if not result["total_requests"]:
            result["total_requests"] = history["total_requests"]
            result["failures"] = history["failures"]
        if not result["avg_tps"]:
            result["avg_tps"] = history["avg_tps"]
        for key in ("p50_response_time", "p95_response_time", "p99_response_time"):
            if not result[key] and history[key]:
                result[key] = history[key]
        if not result["aggregated"]:
            result["aggregated"] = history["aggregated"]

    status_dist = dict(result.get("status_code_dist") or {})
    for candidate in status_files:
        _merge_status_dist(status_dist, parse_stats_csv_text(_read_text(candidate)).get(
            "status_code_dist", {}
        ))
    result["status_code_dist"] = status_dist
    result["source_files"] = [str(f) for f in files]
    return _finalise(result)


# ---------------------------------------------------------------------------
# sample based aggregation
# ---------------------------------------------------------------------------
def _sample_duration(samples: list) -> float:
    """Infer the measured window from sample ``elapsed`` values (seconds).

    Load samples mark the *end* of their bucket, therefore the newest
    ``elapsed`` is the measured window when sampling does not start at zero.
    """
    elapsed = []
    for sample in samples:
        value = _as_float(sample.get("elapsed"), None)
        if value is not None:
            elapsed.append(value)
    if elapsed:
        earliest, latest = min(elapsed), max(elapsed)
        if earliest > 0:
            return latest
        duration = latest - earliest
        if duration > 0:
            return duration
    if len(samples) > 1:
        # Fall back to "one bucket == one second".
        return float(len(samples) - 1)
    return 0.0


def compute_summary(samples: list) -> dict:
    """Aggregate load samples into execution level metrics.

    Each sample is a dict with ``elapsed`` (seconds), ``requests``,
    ``failures``, ``response_time_ms`` and ``status_code``. Empty / malformed
    input yields the zero valued metric dict instead of raising.
    """
    if not isinstance(samples, (list, tuple)):
        return _empty_summary()
    cleaned = [sample for sample in samples if isinstance(sample, dict)]
    if not cleaned:
        return _empty_summary()

    summary = _empty_summary()
    total_requests = 0
    total_failures = 0
    status_dist: dict[str, int] = {}
    for sample in cleaned:
        requests = max(_as_int(sample.get("requests"), 0), 0)
        failures = max(_as_int(sample.get("failures"), 0), 0)
        total_requests += requests
        total_failures += min(failures, requests) if requests else failures
        code = _clean_status(sample.get("status_code"))
        if code:
            status_dist[code] = status_dist.get(code, 0) + requests

    duration = _sample_duration(cleaned)
    summary["total_requests"] = total_requests
    summary["failures"] = total_failures
    summary["avg_tps"] = (total_requests / duration) if duration > 0 else 0.0
    summary["duration_seconds"] = duration
    summary["p50_response_time"] = _weighted_percentile(cleaned, "response_time_ms", 50) or 0
    summary["p95_response_time"] = _weighted_percentile(cleaned, "response_time_ms", 95) or 0
    summary["p99_response_time"] = _weighted_percentile(cleaned, "response_time_ms", 99) or 0
    summary["status_code_dist"] = status_dist
    summary["aggregated"] = []
    return _finalise(summary)


def summarise_sample_series(samples: list) -> dict:
    """Alias kept for readability inside the runner."""
    return compute_summary(samples)
