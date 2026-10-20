"""Domain models for the API 测试 module.

Contract: ``docs/ARCHITECTURE.md`` §2.3.
Every project scoped model uses one of the reserved reverse names:
``api_specifications`` / ``api_modules`` / ``api_cases`` / ``api_suites`` /
``api_executions`` (see §1.10).  ``APIEndpoint`` uses ``api_endpoints`` which is
reserved for this app as well.
"""

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel

# ---------------------------------------------------------------------------
# choices (string constants only - no magic numbers)
# ---------------------------------------------------------------------------
SPEC_SOURCE_TYPES = (
    ("openapi", "OpenAPI 3"),
    ("swagger", "Swagger 2"),
    ("postman", "Postman Collection"),
)

SPEC_STATUS = (
    ("pending", "待解析"),
    ("parsed", "已解析"),
    ("failed", "解析失败"),
)

HTTP_METHODS = (
    ("get", "GET"),
    ("post", "POST"),
    ("put", "PUT"),
    ("patch", "PATCH"),
    ("delete", "DELETE"),
    ("head", "HEAD"),
    ("options", "OPTIONS"),
    ("trace", "TRACE"),
)

CASE_TYPES = (
    ("endpoint", "单接口"),
    ("scenario", "场景"),
)

TEST_TYPES = (
    ("positive", "正向"),
    ("negative", "反向"),
    ("boundary", "边界"),
    ("security", "安全"),
    ("performance", "性能"),
)

SOURCE_TYPES = (
    ("manual", "手动"),
    ("ai", "AI 生成"),
    ("postman", "Postman"),
)

EXECUTION_STATUS = (
    ("pending", "等待中"),
    ("running", "执行中"),
    ("passed", "通过"),
    ("failed", "失败"),
    ("error", "错误"),
    ("cancelled", "已取消"),
)

TRIGGER_TYPES = (
    ("manual", "手动"),
    ("scheduled", "定时"),
    ("api", "API 调用"),
)

EXECUTION_TERMINAL_STATUS = {"passed", "failed", "error", "cancelled"}


class APISpecification(TimeStampedModel):
    """An imported OpenAPI / Swagger / Postman specification."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="api_specifications",
        verbose_name="项目",
    )
    name = models.CharField("规范名称", max_length=255)
    source_type = models.CharField(
        "来源类型", max_length=16, choices=SPEC_SOURCE_TYPES, default="openapi", db_index=True
    )
    version = models.CharField("版本", max_length=64, blank=True, default="")
    spec_data = models.JSONField("规范内容", default=dict, blank=True)
    file = models.ForeignKey(
        "projects.UploadedFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="源文件",
    )
    base_url = models.CharField("Base URL", max_length=500, blank=True, default="")
    status = models.CharField(
        "状态", max_length=16, choices=SPEC_STATUS, default="parsed", db_index=True
    )
    endpoint_count = models.IntegerField("接口数量", default=0)
    error_message = models.TextField("错误信息", blank=True, default="")

    class Meta:
        db_table = "aits_api_specification"
        verbose_name = "API 规范"
        verbose_name_plural = "API 规范"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "source_type"]),
            models.Index(fields=["project", "status"]),
        ]

    def __str__(self):
        return f"{self.project_id}:{self.name}"


class APIModule(TimeStampedModel):
    """Tree module used to organise endpoints / cases."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="api_modules",
        verbose_name="项目",
    )
    spec = models.ForeignKey(
        APISpecification,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modules",
        verbose_name="所属规范",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="父模块",
    )
    name = models.CharField("模块名称", max_length=128)
    description = models.TextField("描述", blank=True, default="")
    order = models.IntegerField("排序", default=0)

    class Meta:
        db_table = "aits_api_module"
        verbose_name = "API 模块"
        verbose_name_plural = "API 模块"
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["project", "parent"])]

    def __str__(self):
        return self.name

    @property
    def full_path(self) -> str:
        names = [self.name]
        node = self.parent
        depth = 0
        while node is not None and depth < 20:
            names.append(node.name)
            node = node.parent
            depth += 1
        return "/".join(reversed(names))


class APIEndpoint(TimeStampedModel):
    """A single operation extracted from a specification."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="api_endpoints",
        verbose_name="项目",
    )
    spec = models.ForeignKey(
        APISpecification,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="endpoints",
        verbose_name="所属规范",
    )
    module = models.ForeignKey(
        APIModule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="endpoints",
        verbose_name="所属模块",
    )
    path = models.CharField("路径", max_length=1000)
    method = models.CharField("方法", max_length=16, choices=HTTP_METHODS, default="get")
    operation_id = models.CharField("operationId", max_length=255, blank=True, default="")
    summary = models.CharField("摘要", max_length=500, blank=True, default="")
    description = models.TextField("描述", blank=True, default="")
    parameters = models.JSONField("参数", default=list, blank=True)
    request_body = models.JSONField("请求体", default=dict, blank=True)
    responses = models.JSONField("响应", default=dict, blank=True)
    headers = models.JSONField("请求头", default=dict, blank=True)
    is_active = models.BooleanField("是否启用", default=True)

    class Meta:
        db_table = "aits_api_endpoint"
        verbose_name = "API 端点"
        verbose_name_plural = "API 端点"
        ordering = ["path", "method", "id"]
        indexes = [
            models.Index(fields=["project", "method"]),
            models.Index(fields=["spec", "path"]),
        ]

    def __str__(self):
        return f"{self.method.upper()} {self.path}"

    @property
    def display_name(self) -> str:
        return self.summary or self.operation_id or f"{self.method.upper()} {self.path}"


class APITestCase(TimeStampedModel):
    """Reusable API test case (single endpoint or multi-step scenario)."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="api_cases",
        verbose_name="项目",
    )
    endpoint = models.ForeignKey(
        APIEndpoint,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="test_cases",
        verbose_name="关联端点",
    )
    module = models.ForeignKey(
        APIModule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="test_cases",
        verbose_name="所属模块",
    )
    name = models.CharField("用例名称", max_length=255)
    case_type = models.CharField(
        "用例类型", max_length=16, choices=CASE_TYPES, default="endpoint"
    )
    test_type = models.CharField(
        "测试类型", max_length=16, choices=TEST_TYPES, default="positive", db_index=True
    )
    description = models.TextField("描述", blank=True, default="")
    request_config = models.JSONField("请求配置", default=dict, blank=True)
    assertions = models.JSONField("断言", default=list, blank=True)
    extract = models.JSONField("变量提取", default=dict, blank=True)
    hooks = models.JSONField("钩子", default=dict, blank=True)
    script_yaml = models.TextField("HttpRunner YAML", blank=True, default="")
    source = models.CharField(
        "来源", max_length=16, choices=SOURCE_TYPES, default="manual", db_index=True
    )
    priority = models.IntegerField("优先级", default=2)
    is_active = models.BooleanField("是否启用", default=True)

    class Meta:
        db_table = "aits_api_test_case"
        verbose_name = "API 测试用例"
        verbose_name_plural = "API 测试用例"
        ordering = ["priority", "id"]
        indexes = [
            models.Index(fields=["project", "case_type"]),
            models.Index(fields=["project", "test_type"]),
        ]

    def __str__(self):
        return self.name


class APITestSuite(TimeStampedModel):
    """Ordered collection of test case ids plus run config."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="api_suites",
        verbose_name="项目",
    )
    name = models.CharField("套件名称", max_length=255)
    description = models.TextField("描述", blank=True, default="")
    environment = models.ForeignKey(
        "projects.Environment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="执行环境",
    )
    case_ids = models.JSONField("用例 ID 列表", default=list, blank=True)
    config = models.JSONField("执行配置", default=dict, blank=True)
    source = models.CharField(
        "来源", max_length=16, choices=SOURCE_TYPES, default="manual", db_index=True
    )
    is_active = models.BooleanField("是否启用", default=True)

    class Meta:
        db_table = "aits_api_test_suite"
        verbose_name = "API 测试套件"
        verbose_name_plural = "API 测试套件"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "is_active"])]

    def __str__(self):
        return self.name

    def ordered_case_ids(self) -> list[int]:
        """Return de-duplicated integer case ids while preserving order."""
        seen: set[int] = set()
        result: list[int] = []
        for raw in self.case_ids or []:
            try:
                case_id = int(raw)
            except (TypeError, ValueError):
                continue
            if case_id in seen:
                continue
            seen.add(case_id)
            result.append(case_id)
        return result


class APITestExecution(TimeStampedModel):
    """One suite (or single case) execution."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="api_executions",
        verbose_name="项目",
    )
    suite = models.ForeignKey(
        APITestSuite,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="executions",
        verbose_name="套件",
    )
    name = models.CharField("执行名称", max_length=255)
    environment = models.ForeignKey(
        "projects.Environment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="执行环境",
    )
    status = models.CharField(
        "状态", max_length=16, choices=EXECUTION_STATUS, default="pending", db_index=True
    )
    trigger_type = models.CharField(
        "触发方式", max_length=16, choices=TRIGGER_TYPES, default="manual", db_index=True
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="触发人",
    )
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    duration_ms = models.IntegerField("耗时(ms)", default=0)
    total = models.IntegerField("总数", default=0)
    passed = models.IntegerField("通过", default=0)
    failed = models.IntegerField("失败", default=0)
    skipped = models.IntegerField("跳过", default=0)
    pass_rate = models.FloatField("通过率", default=0.0)
    report_path = models.CharField("报告路径", max_length=500, blank=True, default="")
    summary = models.JSONField("汇总", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True, default="")

    class Meta:
        db_table = "aits_api_test_execution"
        verbose_name = "API 测试执行"
        verbose_name_plural = "API 测试执行"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "status"]),
            models.Index(fields=["project", "trigger_type"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.status})"

    @property
    def is_finished(self) -> bool:
        return self.status in EXECUTION_TERMINAL_STATUS

    def compute_pass_rate(self) -> float:
        executed = self.total - self.skipped
        if executed <= 0:
            return 0.0
        return round(self.passed / executed * 100, 2)


class APITestCaseExecutionDetail(TimeStampedModel):
    """Per test case result inside an execution."""

    execution = models.ForeignKey(
        APITestExecution,
        on_delete=models.CASCADE,
        related_name="case_details",
        verbose_name="执行",
    )
    test_case = models.ForeignKey(
        APITestCase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="execution_details",
        verbose_name="用例",
    )
    case_name = models.CharField("用例名称", max_length=255)
    status = models.CharField("状态", max_length=16, default="pending", db_index=True)
    duration_ms = models.IntegerField("耗时(ms)", default=0)
    request = models.JSONField("请求", default=dict, blank=True)
    response = models.JSONField("响应", default=dict, blank=True)
    assertions = models.JSONField("断言结果", default=list, blank=True)
    error_message = models.TextField("错误信息", blank=True, default="")
    step_log = models.JSONField("步骤日志", default=list, blank=True)
    order = models.IntegerField("顺序", default=0)

    class Meta:
        db_table = "aits_api_case_execution_detail"
        verbose_name = "API 用例执行明细"
        verbose_name_plural = "API 用例执行明细"
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["execution", "status"])]

    def __str__(self):
        return f"{self.case_name} - {self.status}"


class APITestSuiteExecutionDetail(TimeStampedModel):
    """Suite level aggregated result inside an execution."""

    execution = models.ForeignKey(
        APITestExecution,
        on_delete=models.CASCADE,
        related_name="suite_details",
        verbose_name="执行",
    )
    suite = models.ForeignKey(
        APITestSuite,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="execution_details",
        verbose_name="套件",
    )
    suite_name = models.CharField("套件名称", max_length=255)
    status = models.CharField("状态", max_length=16, default="pending", db_index=True)
    total = models.IntegerField("总数", default=0)
    passed = models.IntegerField("通过", default=0)
    failed = models.IntegerField("失败", default=0)
    duration_ms = models.IntegerField("耗时(ms)", default=0)
    detail = models.JSONField("明细", default=dict, blank=True)

    class Meta:
        db_table = "aits_api_suite_execution_detail"
        verbose_name = "API 套件执行明细"
        verbose_name_plural = "API 套件执行明细"
        ordering = ["id"]

    def __str__(self):
        return f"{self.suite_name} - {self.status}"
