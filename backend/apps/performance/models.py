"""Domain models for the 性能测试 module.

Contract: ``docs/ARCHITECTURE.md`` §2.6 plus the reverse name allocation of
§1.10 (``load_configs`` / ``performance_scenarios`` / ``performance_executions``
/ ``ai_diagnosis_records``).
"""

from __future__ import annotations

from django.db import models

from apps.common.models import TimeStampedModel

# ---------------------------------------------------------------------------
# choices (string constants - no magic numbers)
# ---------------------------------------------------------------------------
SCENARIO_SOURCE_TYPES = (
    ("api_suite", "API 测试套件"),
    ("api_case", "API 测试用例"),
    ("custom_script", "自定义脚本"),
)

EXECUTION_STATUS = (
    ("pending", "等待中"),
    ("running", "执行中"),
    ("passed", "通过"),
    ("failed", "未通过"),
    ("error", "异常"),
    ("cancelled", "已取消"),
)

TRIGGER_TYPES = (
    ("manual", "手动"),
    ("scheduled", "定时"),
    ("api", "API 调用"),
)

DIAGNOSIS_SOURCES = (
    ("grafana", "Grafana 告警"),
    ("manual", "手动诊断"),
)

DIAGNOSIS_STATUS = (
    ("pending", "待处理"),
    ("resolved", "已解决"),
    ("ignored", "已忽略"),
)

EXECUTION_TERMINAL_STATUS = {"passed", "failed", "error", "cancelled"}


class LoadConfiguration(TimeStampedModel):
    """Reusable Locust load profile (users / spawn rate / duration / host)."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="load_configs",
        verbose_name="项目",
    )
    name = models.CharField("配置名称", max_length=255)
    users = models.PositiveIntegerField("并发用户数", default=10)
    spawn_rate = models.FloatField("并发增长率(用户/秒)", default=5.0)
    duration_seconds = models.PositiveIntegerField("持续时间(秒)", default=60)
    host = models.CharField("目标 Host", max_length=500, blank=True, default="")
    config = models.JSONField("扩展配置", default=dict, blank=True)
    description = models.TextField("描述", blank=True, default="")

    class Meta:
        db_table = "aits_load_configuration"
        verbose_name = "负载配置"
        verbose_name_plural = "负载配置"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "name"])]

    def __str__(self) -> str:
        return f"{self.project_id}:{self.name}"


class PerformanceScenario(TimeStampedModel):
    """A performance scenario: locust source + load profile."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="performance_scenarios",
        verbose_name="项目",
    )
    name = models.CharField("场景名称", max_length=255)
    description = models.TextField("描述", blank=True, default="")
    source_type = models.CharField(
        "来源类型", max_length=16, choices=SCENARIO_SOURCE_TYPES,
        default="api_suite", db_index=True,
    )
    source_suite = models.ForeignKey(
        "api_testing.APITestSuite",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="来源 API 套件",
    )
    source_case = models.ForeignKey(
        "api_testing.APITestCase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="来源 API 用例",
    )
    custom_script = models.TextField("自定义 Locust 脚本", blank=True, default="")
    endpoint_count = models.PositiveIntegerField("接口数量", default=0)
    config = models.ForeignKey(
        LoadConfiguration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scenarios",
        verbose_name="负载配置",
    )
    variables = models.JSONField("变量", default=dict, blank=True)
    is_active = models.BooleanField("是否启用", default=True, db_index=True)

    class Meta:
        db_table = "aits_performance_scenario"
        verbose_name = "性能测试场景"
        verbose_name_plural = "性能测试场景"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "source_type"]),
            models.Index(fields=["project", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.project_id}:{self.name}"


class PerformanceExecution(TimeStampedModel):
    """One performance run (Locust or simulated) with its metrics."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="performance_executions",
        verbose_name="项目",
    )
    scenario = models.ForeignKey(
        PerformanceScenario,
        on_delete=models.CASCADE,
        related_name="executions",
        verbose_name="场景",
    )
    config = models.ForeignKey(
        LoadConfiguration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="executions",
        verbose_name="负载配置",
    )
    name = models.CharField("执行名称", max_length=255)
    status = models.CharField(
        "状态", max_length=16, choices=EXECUTION_STATUS, default="pending", db_index=True
    )
    trigger_type = models.CharField(
        "触发方式", max_length=16, choices=TRIGGER_TYPES, default="manual", db_index=True
    )
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    duration_ms = models.IntegerField("耗时(ms)", default=0)
    total_requests = models.IntegerField("总请求数", default=0)
    avg_tps = models.FloatField("平均 TPS", default=0.0)
    p50_response_time = models.IntegerField("P50 响应时间(ms)", default=0)
    p95_response_time = models.IntegerField("P95 响应时间(ms)", default=0)
    p99_response_time = models.IntegerField("P99 响应时间(ms)", default=0)
    error_rate = models.FloatField("错误率", default=0.0)
    status_code_dist = models.JSONField("状态码分布", default=dict, blank=True)
    csv_path = models.CharField("CSV 结果路径", max_length=500, blank=True, default="")
    report_path = models.CharField("报告路径", max_length=500, blank=True, default="")
    summary = models.JSONField("汇总", default=dict, blank=True)
    celery_task_id = models.CharField("Celery 任务 ID", max_length=128, blank=True, default="")
    error_message = models.TextField("错误信息", blank=True, default="")

    class Meta:
        db_table = "aits_performance_execution"
        verbose_name = "性能测试执行"
        verbose_name_plural = "性能测试执行"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "status"]),
            models.Index(fields=["project", "trigger_type"]),
            models.Index(fields=["scenario", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"

    @property
    def is_finished(self) -> bool:
        return self.status in EXECUTION_TERMINAL_STATUS


class AiDiagnosisRecord(TimeStampedModel):
    """LLM / rules based diagnosis attached to an execution or Grafana alert.

    ``project`` is nullable so alerts arriving from Grafana without a project
    label (or referencing an execution that was deleted) are still recorded
    instead of being dropped by the webhook.
    """

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ai_diagnosis_records",
        verbose_name="项目",
    )
    execution = models.ForeignKey(
        PerformanceExecution,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="diagnosis_records",
        verbose_name="性能执行",
    )
    source = models.CharField(
        "来源", max_length=16, choices=DIAGNOSIS_SOURCES, default="manual", db_index=True
    )
    alert_name = models.CharField("告警名称", max_length=255, blank=True, default="")
    severity = models.CharField("级别", max_length=32, blank=True, default="")
    grafana_url = models.CharField("Grafana 链接", max_length=500, blank=True, default="")
    diagnosis_content = models.TextField("诊断结论", blank=True, default="")
    status = models.CharField(
        "处理状态", max_length=16, choices=DIAGNOSIS_STATUS, default="pending", db_index=True
    )
    notified_at = models.DateTimeField("通知时间", null=True, blank=True)
    resolved_at = models.DateTimeField("解决时间", null=True, blank=True)
    raw_payload = models.JSONField("原始载荷", default=dict, blank=True)

    class Meta:
        db_table = "aits_ai_diagnosis_record"
        verbose_name = "AI 诊断记录"
        verbose_name_plural = "AI 诊断记录"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "status"]),
            models.Index(fields=["project", "source"]),
        ]

    def __str__(self) -> str:
        return f"{self.project_id}:{self.alert_name or self.source}"
