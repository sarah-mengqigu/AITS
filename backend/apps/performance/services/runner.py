"""Performance execution runners.

``docs/ARCHITECTURE.md`` §1.8 requires a common runner interface::

    class BaseRunner:
        def run(self, plan, on_progress=None) -> dict

This module provides:

* :class:`SimulatedRunner` - deterministic load curve, no real traffic, writes a
  Locust compatible ``stats.csv`` (+ history) under
  ``settings.REPORT_ROOT/<execution_id>/``. Never waits for the configured
  duration.
* :class:`LocustRunner` - spawns ``locust --headless`` in ``real`` mode, polls
  the process, enforces a timeout and parses the produced CSV files.
* :func:`get_runner` - mode aware factory (``settings.AITS_EXECUTION_MODE``).
"""

from __future__ import annotations

import csv
import importlib.util
import logging
import math
import random
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

from django.conf import settings

from apps.common.api.api_exception_handler import BusinessError

from ..constants import (
    ERROR_RATE_THRESHOLD,
    MAX_SIMULATED_BUCKETS,
    MIN_SIMULATED_SAMPLES,
    REAL_RUN_POLL_INTERVAL,
    REAL_RUN_TIMEOUT_EXTRA_SECONDS,
    SIMULATED_ERROR_RATE,
    SIMULATED_RESPONSE_TIME_MS,
    SIMULATED_RPS_PER_USER,
)
from .stats import compute_summary, parse_locust_csv

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]

#: Locust ``*_stats.csv`` header (an extra ``Status Code`` column is appended).
STATS_CSV_HEADER = [
    "Type",
    "Name",
    "Request Count",
    "Failure Count",
    "Median Response Time",
    "Average Response Time",
    "Min Response Time",
    "Max Response Time",
    "Average Content Size",
    "Requests/s",
    "Failures/s",
    "50%",
    "66%",
    "75%",
    "80%",
    "90%",
    "95%",
    "98%",
    "99%",
    "99.9%",
    "99.99%",
    "100%",
    "Status Code",
]

HISTORY_CSV_HEADER = [
    "Timestamp",
    "User Count",
    "Type",
    "Name",
    "Requests/s",
    "Failures/s",
    "Median Response Time",
    "Average Response Time",
    "Min Response Time",
    "Max Response Time",
    "Average Content Size",
    "Requests",
    "Failures",
    "95%",
    "99%",
]


def _clamp(value, low, high):
    return max(low, min(high, value))


def _percentile_columns(p50, p95, p99, cap) -> list[int]:
    """Render the 11 Locust percentile columns monotonically."""
    def between(low, high, ratio):
        return int(round(low + (high - low) * ratio))

    p50 = max(int(p50), 0)
    p95 = max(int(p95), p50)
    p99 = max(int(p99), p95)
    cap = max(int(cap), p99)
    return [
        p50,
        between(p50, p95, 0.25),
        between(p50, p95, 0.45),
        between(p50, p95, 0.55),
        between(p50, p95, 0.75),
        p95,
        between(p95, p99, 0.4),
        p99,
        between(p99, cap, 0.5),
        between(p99, cap, 0.9),
        cap,
    ]


class BaseRunner:
    """Common behaviour shared by every performance runner."""

    mode = "base"

    # -- interface ----------------------------------------------------------
    def run(self, plan: dict, on_progress: ProgressCallback | None = None) -> dict:
        """Execute ``plan`` and return ``{status, summary, artifacts, samples}``."""
        raise NotImplementedError  # pragma: no cover - abstract

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def notify_progress(on_progress, progress: int, message: str) -> None:
        if not on_progress:
            return
        try:
            on_progress(int(progress), str(message))
        except Exception:  # noqa: BLE001 - progress must never break a run
            logger.warning("progress callback failed", exc_info=True)

    @staticmethod
    def output_dir(plan: dict) -> Path:
        root = Path(
            getattr(settings, "REPORT_ROOT", None)
            or (Path(getattr(settings, "MEDIA_ROOT", ".")) / "reports")
        )
        key = plan.get("execution_id") or plan.get("scenario_id") or "adhoc"
        directory = root / str(key)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def write_script(plan: dict, directory: Path) -> Path:
        script_path = directory / "locustfile.py"
        script_path.write_text(str(plan.get("script") or ""), encoding="utf-8")
        return script_path

    @staticmethod
    def decide_status(summary: dict) -> str:
        error_rate = float(summary.get("error_rate") or 0.0)
        p95 = int(summary.get("p95_response_time") or 0)
        if error_rate <= ERROR_RATE_THRESHOLD and p95 > 0:
            return "passed"
        return "failed"


# ---------------------------------------------------------------------------
# simulated
# ---------------------------------------------------------------------------
class SimulatedRunner(BaseRunner):
    """Deterministic load model used for CI, demos and offline environments."""

    mode = "simulated"

    def run(self, plan: dict, on_progress: ProgressCallback | None = None) -> dict:
        self.notify_progress(on_progress, 5, "准备压测计划")
        directory = self.output_dir(plan)
        script_path = self.write_script(plan, directory)

        samples = self.build_samples(plan)
        summary = compute_summary(samples)
        stats_path = directory / "stats.csv"
        history_path = directory / "stats_history.csv"
        self.write_stats_csv(stats_path, plan, summary)
        self.write_history_csv(history_path, plan, samples)

        status = self.decide_status(summary)
        self.notify_progress(on_progress, 100, "压测完成")
        return {
            "status": status,
            "summary": summary,
            "samples": samples,
            "artifacts": {
                "mode": self.mode,
                "out_dir": str(directory),
                "script_path": str(script_path),
                "stats_csv": str(stats_path),
                "history_csv": str(history_path),
                "csv_path": str(stats_path),
            },
        }

    # -- deterministic model ------------------------------------------------
    def build_samples(self, plan: dict) -> list[dict]:
        users = max(int(plan.get("users") or 1), 1)
        spawn_rate = max(float(plan.get("spawn_rate") or 1.0), 0.1)
        duration = max(int(plan.get("duration_seconds") or 1), 1)
        options = plan.get("options") or {}
        target_error_rate = _clamp(
            float(options.get("error_rate", SIMULATED_ERROR_RATE)), 0.0, 1.0
        )
        base_response = max(float(options.get("response_time_ms", SIMULATED_RESPONSE_TIME_MS)), 1.0)

        # One bucket every 5 seconds, bounded so a run never emits more than
        # ``MAX_SIMULATED_SAMPLES`` raw samples (each bucket <= 2 records).
        buckets = int(
            _clamp(duration // 5, MIN_SIMULATED_SAMPLES, MAX_SIMULATED_BUCKETS)
        )
        step = duration / buckets
        ramp_time = users / spawn_rate
        ramp_time = max(min(ramp_time, duration), step)

        seed = int((plan.get("scenario_id") or 0) * 1_000_003 + (plan.get("config_id") or 0))
        rng = random.Random(seed)
        rps_per_user = SIMULATED_RPS_PER_USER * rng.uniform(0.8, 1.25)
        failure_codes = (500, 503, 502, 429)
        samples: list[dict] = []

        for index in range(buckets):
            elapsed = round(step * (index + 1), 3)
            concurrency = users * min(1.0, elapsed / ramp_time)
            requests = max(int(round(concurrency * rps_per_user * step)), 0)
            if requests == 0 and concurrency > 0:
                requests = 1
            failures = 0
            if requests and target_error_rate > 0:
                raw = requests * target_error_rate
                failures = int(math.floor(raw + rng.random()))
                if failures == 0 and rng.random() < target_error_rate * 4:
                    failures = 1
                failures = min(failures, requests)

            response_time = base_response * rng.uniform(0.75, 1.35)
            if index % 7 == 6:
                response_time *= 1.8  # periodic latency spike
            response_time = int(round(response_time))

            success = requests - failures
            if success:
                samples.append(
                    {
                        "elapsed": elapsed,
                        "requests": success,
                        "failures": 0,
                        "response_time_ms": response_time,
                        "status_code": 200,
                    }
                )
            if failures:
                status_code = failure_codes[index % len(failure_codes)]
                samples.append(
                    {
                        "elapsed": elapsed,
                        "requests": failures,
                        "failures": failures,
                        "response_time_ms": int(round(response_time * 2.5)),
                        "status_code": status_code,
                    }
                )
        return samples

    # -- artifact writers ---------------------------------------------------
    def write_stats_csv(self, path: Path, plan: dict, summary: dict) -> Path:
        p50 = int(summary.get("p50_response_time") or 0)
        p95 = int(summary.get("p95_response_time") or 0)
        p99 = int(summary.get("p99_response_time") or 0)
        min_rt = max(int(p50 * 0.6), 0)
        max_rt = max(int(p99 * 1.4), p99)
        percentiles = _percentile_columns(p50, p95, p99, max_rt)
        failures_per_second = round(
            float(summary.get("error_rate") or 0.0)
            * float(summary.get("avg_tps") or 0.0),
            2,
        )
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(STATS_CSV_HEADER)
            writer.writerow(
                [
                    "",
                    "Aggregated",
                    summary.get("total_requests", 0),
                    summary.get("failures", 0),
                    p50,
                    p95 if p95 else p50,
                    min_rt,
                    max_rt,
                    0,
                    summary.get("avg_tps", 0.0),
                    failures_per_second,
                    *percentiles,
                    "",
                ]
            )
            for code, count in sorted(
                (summary.get("status_code_dist") or {}).items(), key=lambda item: str(item[0])
            ):
                failed = code.startswith(("4", "5"))
                median = p95 if failed else p50
                writer.writerow(
                    [
                        "STATUS",
                        f"status_{code}",
                        count,
                        count if failed else 0,
                        median,
                        median,
                        min_rt,
                        max_rt,
                        0,
                        round(
                            float(count)
                            / max(int(plan.get("duration_seconds") or 1), 1),
                            2,
                        ),
                        0,
                        *percentiles,
                        code,
                    ]
                )
        return path

    def write_history_csv(self, path: Path, plan: dict, samples: list) -> Path:
        users = max(int(plan.get("users") or 1), 1)
        total_requests = 0
        total_failures = 0
        by_elapsed: dict[float, dict] = {}
        for sample in samples:
            bucket = by_elapsed.setdefault(
                float(sample.get("elapsed") or 0.0),
                {"requests": 0, "failures": 0, "response_times": []},
            )
            bucket["requests"] += int(sample.get("requests") or 0)
            bucket["failures"] += int(sample.get("failures") or 0)
            bucket["response_times"].append(int(sample.get("response_time_ms") or 0))

        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(HISTORY_CSV_HEADER)
            for elapsed in sorted(by_elapsed):
                bucket = by_elapsed[elapsed]
                total_requests += bucket["requests"]
                total_failures += bucket["failures"]
                times = sorted(bucket["response_times"]) or [0]
                median = times[len(times) // 2]
                writer.writerow(
                    [
                        elapsed,
                        users,
                        "",
                        "Aggregated",
                        round(bucket["requests"] / max(elapsed, 1), 2),
                        round(bucket["failures"] / max(elapsed, 1), 3),
                        median,
                        int(sum(times) / len(times)),
                        min(times),
                        max(times),
                        0,
                        total_requests,
                        total_failures,
                        max(times),
                        max(times),
                    ]
                )
        return path


# ---------------------------------------------------------------------------
# real locust
# ---------------------------------------------------------------------------
class LocustRunner(BaseRunner):
    """Spawn ``locust --headless`` and parse its CSV output."""

    mode = "real"

    def __init__(self, binary: str | None = None):
        self._binary = binary or shutil.which("locust")
        self._python_module = self._module_available()

    @staticmethod
    def _module_available() -> bool:
        try:
            return importlib.util.find_spec("locust") is not None
        except (ImportError, ValueError, AttributeError):  # pragma: no cover - odd envs
            return False

    @property
    def available(self) -> bool:
        return bool(self._binary) or self._python_module

    def run(self, plan: dict, on_progress: ProgressCallback | None = None) -> dict:
        if not self.available:
            raise BusinessError(
                message="locust 未安装或不在 PATH 中，无法执行真实压测；"
                "请安装 locust 或将 AITS_EXECUTION_MODE 设为 simulated",
                code="locust_unavailable",
                status_code=503,
            )
        directory = self.output_dir(plan)
        script_path = self.write_script(plan, directory)
        csv_prefix = directory / "locust"
        users = max(int(plan.get("users") or 1), 1)
        spawn_rate = max(float(plan.get("spawn_rate") or 1.0), 0.1)
        duration = max(int(plan.get("duration_seconds") or 1), 1)
        host = str(plan.get("host") or "")

        binary = self._binary or shutil.which("locust") or "locust"
        command = [
            binary,
            "-f",
            str(script_path),
            "--headless",
            "--only-summary",
            "-u",
            str(users),
            "-r",
            str(spawn_rate),
            "-t",
            f"{duration}s",
            "--csv",
            str(csv_prefix),
        ]
        if host:
            command.extend(["--host", host])

        self.notify_progress(on_progress, 5, "启动 locust 压测进程")
        timeout = duration + REAL_RUN_TIMEOUT_EXTRA_SECONDS
        started = time.monotonic()
        process = subprocess.Popen(  # noqa: S603 - trusted local binary
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        timed_out = False
        try:
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed > timeout:
                    timed_out = True
                    process.kill()
                    break
                progress = int(_clamp(5 + (elapsed / duration) * 90, 5, 95))
                self.notify_progress(on_progress, progress, "locust 压测进行中")
                time.sleep(REAL_RUN_POLL_INTERVAL)
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            process.kill()
            stdout, stderr = process.communicate()
        finally:
            if process.poll() is None:  # pragma: no cover - defensive
                process.kill()

        if timed_out:
            raise BusinessError(
                message=f"locust 压测执行超时（>{timeout}s），已强制终止",
                code="locust_timeout",
                status_code=504,
            )
        if process.returncode not in (0, None):
            tail = (stderr or stdout or "").strip().splitlines()[-5:]
            raise BusinessError(
                message="locust 执行失败: " + (" | ".join(tail) or f"退出码 {process.returncode}"),
                code="locust_failed",
                status_code=500,
            )

        summary = parse_locust_csv(directory)
        self.notify_progress(on_progress, 100, "压测完成")
        return {
            "status": self.decide_status(summary),
            "summary": summary,
            "samples": [],
            "artifacts": {
                "mode": self.mode,
                "out_dir": str(directory),
                "script_path": str(script_path),
                "stats_csv": str(directory / "locust_stats.csv"),
                "history_csv": str(directory / "locust_stats_history.csv"),
                "csv_path": str(directory / "locust_stats.csv"),
                "stdout_tail": (stdout or "").strip().splitlines()[-20:],
            },
        }


# ---------------------------------------------------------------------------
# factory
# ---------------------------------------------------------------------------
def get_runner(mode: str | None = None) -> BaseRunner:
    """Return the runner for ``mode`` or ``settings.AITS_EXECUTION_MODE``."""
    resolved = (
        mode or getattr(settings, "AITS_EXECUTION_MODE", "simulated") or "simulated"
    )
    resolved = str(resolved).strip().lower()
    if resolved in ("real", "locust"):
        return LocustRunner()
    return SimulatedRunner()
