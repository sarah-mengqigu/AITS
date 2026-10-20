"""Models for the 移动端 App 测试 module (ARCHITECTURE §2.5).

Domain objects
--------------
* :class:`AppTestModule`      - tree of test modules (self referencing parent)
* :class:`AppTestApplication` - the App under test (Android package / iOS bundle)
* :class:`AppTestCase`        - structured AITS steps + Sonic compatible snapshot
* :class:`AppTestSuite`       - ordered bundle of cases executed on one device
* :class:`AppTestRun`         - one run of a suite (or a single ad-hoc case)

Every model inherits :class:`apps.common.models.TimeStampedModel`; every project
bound model uses the ``related_name`` values assigned in
``docs/ARCHITECTURE.md`` §1.10 (``app_modules``, ``app_applications``,
``app_cases``, ``app_suites``, ``app_runs``).
"""

from django.db import models

from apps.common.models import TimeStampedModel

# ---------------------------------------------------------------------------
# enumerations (string constants only - no magic numbers, see §1.3)
# ---------------------------------------------------------------------------
PLATFORM_CHOICES = (
    ("android", "Android"),
    ("ios", "iOS"),
)

CASE_SOURCE_CHOICES = (
    ("manual", "手工创建"),
    ("ai", "AI 生成"),
    ("sonic", "Sonic 同步"),
)

PRIORITY_CHOICES = (
    ("low", "低"),
    ("medium", "中"),
    ("high", "高"),
    ("critical", "紧急"),
)

RUN_STATUS_CHOICES = (
    ("pending", "待执行"),
    ("running", "执行中"),
    ("passed", "通过"),
    ("failed", "失败"),
    ("error", "错误"),
    ("cancelled", "已取消"),
)

TRIGGER_TYPE_CHOICES = (
    ("manual", "手动触发"),
    ("scheduled", "定时触发"),
    ("api", "API 触发"),
)

#: statuses after which a run is terminal (cannot be cancelled anymore)
TERMINAL_RUN_STATUSES = ("passed", "failed", "error", "cancelled")

#: AITS internal step actions (kept in sync with ``services.case_converter``)
APP_STEP_ACTIONS = (
    "tap",
    "click",
    "input",
    "fill",
    "swipe",
    "assert",
    "assert_text",
    "wait",
    "back",
    "start_app",
    "stop_app",
)


class AppTestModule(TimeStampedModel):
    """A node of the App test module tree."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="app_modules",
        verbose_name="项目",
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children",
        verbose_name="上级模块",
    )
    name = models.CharField("模块名称", max_length=128)
    description = models.TextField("模块描述", blank=True, default="")
    order = models.IntegerField("排序", default=0)

    class Meta:
        db_table = "aits_app_test_module"
        verbose_name = "App 测试模块"
        verbose_name_plural = "App 测试模块"
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["project", "parent"])]

    def __str__(self):
        return self.name

    @property
    def case_count(self) -> int:
        return self.cases.count()


class AppTestApplication(TimeStampedModel):
    """The mobile application under test."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="app_applications",
        verbose_name="项目",
    )
    name = models.CharField("应用名称", max_length=128)
    platform = models.CharField(
        "平台", max_length=16, choices=PLATFORM_CHOICES, default="android", db_index=True
    )
    package_name = models.CharField("Android 包名", max_length=255, blank=True, default="")
    bundle_id = models.CharField("iOS Bundle ID", max_length=255, blank=True, default="")
    app_version = models.CharField("版本号", max_length=64, blank=True, default="")
    description = models.TextField("应用描述", blank=True, default="")

    class Meta:
        db_table = "aits_app_test_application"
        verbose_name = "App 应用"
        verbose_name_plural = "App 应用"
        ordering = ["-created_at", "id"]
        indexes = [models.Index(fields=["project", "platform"])]

    def __str__(self):
        return f"{self.name} ({self.platform})"

    @property
    def app_identifier(self) -> str:
        """Package name on Android, bundle id on iOS."""
        if self.platform == "ios":
            return self.bundle_id or self.package_name
        return self.package_name or self.bundle_id


class AppTestCase(TimeStampedModel):
    """A mobile UI test case.

    ``steps`` holds the AITS internal steps (``[{action, target, value, expect,
    description}]``); ``sonic_steps`` keeps the Sonic compatible snapshot that is
    pushed to the Sonic server when the case runs.
    """

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="app_cases",
        verbose_name="项目",
    )
    module = models.ForeignKey(
        AppTestModule, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="cases", verbose_name="所属模块",
    )
    application = models.ForeignKey(
        AppTestApplication, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="cases", verbose_name="所属应用",
    )
    name = models.CharField("用例名称", max_length=255)
    description = models.TextField("用例描述", blank=True, default="")
    steps = models.JSONField("测试步骤", default=list, blank=True)
    sonic_steps = models.JSONField("Sonic 步骤快照", default=list, blank=True)
    source = models.CharField(
        "来源", max_length=16, choices=CASE_SOURCE_CHOICES, default="manual", db_index=True
    )
    priority = models.CharField(
        "优先级", max_length=16, choices=PRIORITY_CHOICES, default="medium", db_index=True
    )
    is_active = models.BooleanField("是否启用", default=True, db_index=True)

    class Meta:
        db_table = "aits_app_test_case"
        verbose_name = "App 测试用例"
        verbose_name_plural = "App 测试用例"
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(fields=["project", "module"]),
            models.Index(fields=["project", "is_active"]),
        ]

    def __str__(self):
        return self.name

    @property
    def step_count(self) -> int:
        return len(self.steps or [])


class AppTestSuite(TimeStampedModel):
    """A bundle of cases that runs on a single mobile device."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="app_suites",
        verbose_name="项目",
    )
    name = models.CharField("套件名称", max_length=255)
    description = models.TextField("套件描述", blank=True, default="")
    case_ids = models.JSONField("用例 ID 列表", default=list, blank=True)
    application = models.ForeignKey(
        AppTestApplication, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="suites", verbose_name="所属应用",
    )
    device_config = models.JSONField("设备配置", default=dict, blank=True)
    is_active = models.BooleanField("是否启用", default=True, db_index=True)

    class Meta:
        db_table = "aits_app_test_suite"
        verbose_name = "App 测试套件"
        verbose_name_plural = "App 测试套件"
        ordering = ["-created_at", "id"]

    def __str__(self):
        return self.name

    @property
    def case_count(self) -> int:
        return len(self.case_ids or [])


class AppTestRun(TimeStampedModel):
    """One execution of a suite (or a one-off single case run)."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="app_runs",
        verbose_name="项目",
    )
    suite = models.ForeignKey(
        AppTestSuite, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="runs", verbose_name="测试套件",
    )
    name = models.CharField("执行名称", max_length=255)
    status = models.CharField(
        "状态", max_length=16, choices=RUN_STATUS_CHOICES, default="pending", db_index=True
    )
    trigger_type = models.CharField(
        "触发方式", max_length=16, choices=TRIGGER_TYPE_CHOICES, default="manual"
    )
    device_udid = models.CharField("设备 UDID", max_length=128, blank=True, default="")
    device_id = models.CharField("Sonic 设备 ID", max_length=128, blank=True, default="")
    device_name = models.CharField("设备名称", max_length=128, blank=True, default="")
    platform = models.CharField("平台", max_length=16, blank=True, default="")
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    duration_ms = models.BigIntegerField("耗时(ms)", default=0)
    total = models.IntegerField("用例总数", default=0)
    passed = models.IntegerField("通过数", default=0)
    failed = models.IntegerField("失败数", default=0)
    skipped = models.IntegerField("跳过数", default=0)
    pass_rate = models.FloatField("通过率(%)", default=0.0)
    sonic_suite_id = models.CharField("Sonic 套件 ID", max_length=128, blank=True, default="")
    report_path = models.CharField("报告路径", max_length=500, blank=True, default="")
    summary = models.JSONField("执行摘要", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True, default="")

    class Meta:
        db_table = "aits_app_test_run"
        verbose_name = "App 测试执行"
        verbose_name_plural = "App 测试执行"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["project", "status"]),
            models.Index(fields=["project", "created_at"]),
        ]

    def __str__(self):
        return f"{self.name} [{self.status}]"

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_RUN_STATUSES
