"""Prometheus metrics exposed by AITS itself (``/metrics``).

Business modules increment the counters below; the monitoring add-on scrapes
this endpoint alongside Locust / Windows exporters.
"""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

REGISTRY = CollectorRegistry(auto_describe=True)

TEST_EXECUTIONS = Counter(
    "aits_test_executions_total",
    "Number of test executions started",
    ["domain", "status"],
    registry=REGISTRY,
)
TEST_CASES = Counter(
    "aits_test_cases_total",
    "Number of executed test cases",
    ["domain", "status"],
    registry=REGISTRY,
)
AI_REQUESTS = Counter(
    "aits_ai_requests_total",
    "LLM requests issued by agents",
    ["provider", "agent", "status"],
    registry=REGISTRY,
)
AI_TOKENS = Counter(
    "aits_ai_tokens_total",
    "Tokens consumed by LLM calls",
    ["provider", "agent", "kind"],
    registry=REGISTRY,
)
EXECUTION_DURATION = Histogram(
    "aits_execution_duration_seconds",
    "Duration of an execution run",
    ["domain"],
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800),
    registry=REGISTRY,
)
RUNNING_EXECUTIONS = Gauge(
    "aits_running_executions",
    "Executions currently running",
    ["domain"],
    registry=REGISTRY,
)
QUEUE_DEPTH = Gauge(
    "aits_scheduled_tasks_pending",
    "Scheduled task executions pending",
    registry=REGISTRY,
)


def record_execution(domain: str, status: str):
    TEST_EXECUTIONS.labels(domain=domain, status=status).inc()


def record_case(domain: str, status: str, amount: int = 1):
    TEST_CASES.labels(domain=domain, status=status).inc(amount)


def record_ai(provider: str, agent: str, status: str, prompt_tokens=0, completion_tokens=0):
    AI_REQUESTS.labels(provider=provider or "unknown", agent=agent or "unknown",
                       status=status).inc()
    if prompt_tokens:
        AI_TOKENS.labels(provider=provider or "unknown", agent=agent or "unknown",
                         kind="prompt").inc(prompt_tokens)
    if completion_tokens:
        AI_TOKENS.labels(provider=provider or "unknown", agent=agent or "unknown",
                         kind="completion").inc(completion_tokens)


def render_metrics() -> bytes:
    return generate_latest(REGISTRY)
