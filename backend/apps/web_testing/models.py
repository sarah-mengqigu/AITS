"""Models for the Web UI 测试 module (ARCHITECTURE §2.4).

Domain objects
--------------
* :class:`WebUITestModule`      - tree of test modules (self referencing parent)
* :class:`WebUITestCase`        - UI test case (natural language / structured steps)
* :class:`WebUITestSuite`       - ordered bundle of cases
* :class:`WebUITestExecution`   - one run of a suite or a single case
* :class:`WebUITestCaseExecutionDetail` - per case result of an execution
* :class:`WebPage` / :class:`WebElement` - Page Object Model (POM)
* :class:`MidSceneScript`       - generated MidScene YAML / Python script

Every model inherits :class:`apps.common.models.TimeStampedModel` and every
project bound model uses the ``related_name`` values assigned in
``docs/ARCHITECTURE.md`` §1.10 (``web_modules``, ``web_cases``, ``web_suites``,
``web_executions``, ``web_pages``, ``midscene_scripts``).
"""

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel

# ---------------------------------------------------------------------------
# enumerations (string constants only - no magic numbers, see §1.3)
# ---------------------------------------------------------------------------
CASE_TYPE_CHOICES = (
    ("ui", "UI 用例"),
    ("api_mixed", "接口混合用例"),
)

SCRIPT_TYPE_CHOICES = (
    ("playwright", "Playwright"),
    ("midscene", "MidScene"),
)

CASE_SOURCE_CHOICES = (
    ("manual", "手工创建"),
    ("ai", "AI 生成"),
    ("recording", "录制"),
)

PRIORITY_CHOICES = (
    ("low", "低"),
    ("medium", "中"),
    ("high", "高"),
    ("critical", "紧急"),
)

BROWSER_CHOICES = (
    ("chromium", "Chromium"),
    ("firefox", "Firefox"),
    ("webkit", "WebKit"),
)

EXECUTION_STATUS_CHOICES = (
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

CASE_STATUS_CHOICES = (
    ("pending", "待执行"),
    ("running", "执行中"),
    ("passed", "通过"),
    ("failed", "失败"),
    ("skipped", "跳过"),
    ("error", "错误"),
)

LOCATOR_TYPE_CHOICES = (
    ("css", "CSS 选择器"),
    ("xpath", "XPath"),
    ("text", "文本"),
    ("role", "ARIA Role"),
    ("id", "元素 ID"),
    ("testid", "Test ID"),
)

MIDSCENE_SCRIPT_TYPE_CHOICES = (
    ("yaml", "YAML"),
    ("python", "Python"),
)

MIDSCENE_STATUS_CHOICES = (
    ("draft", "草稿"),
    ("generated", "已生成"),
    ("failed", "生成失败"),
)

#: statuses after which an execution is terminal (cannot be cancelled anymore)
TERMINAL_EXECUTION_STATUSES = ("passed", "failed", "error", "cancelled")


class WebUITestModule(TimeStampedModel):
    """A node of the Web UI test module tree."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="web_modules",
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
        db_table = "aits_web_ui_test_module"
        verbose_name = "Web UI 测试模块"
        verbose_name_plural = "Web UI 测试模块"
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["project", "parent"])]

    def __str__(self):
        return self.name

    @property
    def case_count(self) -> int:
        return self.cases.count()


class WebUITestCase(TimeStampedModel):
    """A Web UI test case: structured steps + generated script."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="web_cases",
        verbose_name="项目",
    )
    module = models.ForeignKey(
        WebUITestModule, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="cases", verbose_name="所属模块",
    )
    name = models.CharField("用例名称", max_length=255)
    description = models.TextField("用例描述", blank=True, default="")
    case_type = models.CharField(
        "用例类型", max_length=16, choices=CASE_TYPE_CHOICES, default="ui", db_index=True
    )
    steps = models.JSONField("测试步骤", default=list, blank=True)
    script = models.TextField("生成脚本", blank=True, default="")
    script_type = models.CharField(
        "脚本类型", max_length=16, choices=SCRIPT_TYPE_CHOICES, default="playwright"
    )
    pom_refs = models.JSONField("POM 页面引用", default=list, blank=True)
    assertions = models.JSONField("断言", default=list, blank=True)
    source = models.CharField(
        "来源", max_length=16, choices=CASE_SOURCE_CHOICES, default="manual"
    )
    priority = models.CharField(
        "优先级", max_length=16, choices=PRIORITY_CHOICES, default="medium"
    )
    is_active = models.BooleanField("是否启用", default=True, db_index=True)

    class Meta:
        db_table = "aits_web_ui_test_case"
        verbose_name = "Web UI 测试用例"
        verbose_name_plural = "Web UI 测试用例"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "module"])]

    def __str__(self):
        return self.name

    @property
    def step_count(self) -> int:
        return len(self.steps or [])

    @property
    def pom_page_ids(self) -> list:
        ids = []
        for ref in self.pom_refs or []:
            if isinstance(ref, dict):
                ref = ref.get("page_id") or ref.get("id")
            try:
                ids.append(int(ref))
            except (TypeError, ValueError):
                continue
        return ids


class WebUITestSuite(TimeStampedModel):
    """A named collection of cases that is executed together."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="web_suites",
        verbose_name="项目",
    )
    name = models.CharField("套件名称", max_length=255)
    description = models.TextField("套件描述", blank=True, default="")
    case_ids = models.JSONField("用例 ID 列表", default=list, blank=True)
    environment = models.ForeignKey(
        "projects.Environment", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="执行环境",
    )
    browser = models.CharField(
        "浏览器", max_length=16, choices=BROWSER_CHOICES, default="chromium"
    )
    headless = models.BooleanField("无头模式", default=True)
    config = models.JSONField("执行配置", default=dict, blank=True)
    is_active = models.BooleanField("是否启用", default=True, db_index=True)

    class Meta:
        db_table = "aits_web_ui_test_suite"
        verbose_name = "Web UI 测试套件"
        verbose_name_plural = "Web UI 测试套件"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def case_count(self) -> int:
        return len(self.case_ids or [])

    def resolve_cases(self):
        """Return the case instances referenced by ``case_ids`` (ordered)."""
        ids = [cid for cid in (self.case_ids or []) if cid is not None]
        if not ids:
            return []
        cases = {
            case.id: case
            for case in WebUITestCase.objects.filter(
                project=self.project, id__in=ids
            ).select_related("project", "module")
        }
        ordered = [cases[cid] for cid in ids if cid in cases]
        return ordered


class WebUITestExecution(TimeStampedModel):
    """One execution of a suite (``suite`` set) or a single case."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="web_executions",
        verbose_name="项目",
    )
    suite = models.ForeignKey(
        WebUITestSuite, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="executions", verbose_name="测试套件",
    )
    name = models.CharField("执行名称", max_length=255)
    status = models.CharField(
        "执行状态", max_length=16, choices=EXECUTION_STATUS_CHOICES,
        default="pending", db_index=True,
    )
    trigger_type = models.CharField(
        "触发方式", max_length=16, choices=TRIGGER_TYPE_CHOICES, default="manual"
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="触发人",
    )
    browser = models.CharField(
        "浏览器", max_length=16, choices=BROWSER_CHOICES, default="chromium"
    )
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    duration_ms = models.IntegerField("耗时(毫秒)", default=0)
    total = models.IntegerField("用例总数", default=0)
    passed = models.IntegerField("通过数", default=0)
    failed = models.IntegerField("失败数", default=0)
    skipped = models.IntegerField("跳过数", default=0)
    pass_rate = models.FloatField("通过率", default=0.0)
    report_path = models.CharField("报告路径", max_length=500, blank=True, default="")
    allure_results_path = models.CharField(
        "Allure 结果路径", max_length=500, blank=True, default=""
    )
    summary = models.JSONField("执行摘要", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True, default="")

    class Meta:
        db_table = "aits_web_ui_test_execution"
        verbose_name = "Web UI 测试执行"
        verbose_name_plural = "Web UI 测试执行"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "status"])]

    def __str__(self):
        return f"{self.name} ({self.status})"

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_EXECUTION_STATUSES

    def compute_pass_rate(self) -> float:
        executed = (self.passed or 0) + (self.failed or 0)
        if not executed:
            return 0.0
        return round((self.passed or 0) * 100.0 / executed, 2)


class WebUITestCaseExecutionDetail(TimeStampedModel):
    """Per case result belonging to an :class:`WebUITestExecution`."""

    execution = models.ForeignKey(
        WebUITestExecution, on_delete=models.CASCADE, related_name="details",
        verbose_name="执行记录",
    )
    test_case = models.ForeignKey(
        WebUITestCase, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="execution_details", verbose_name="测试用例",
    )
    case_name = models.CharField("用例名称", max_length=255)
    status = models.CharField(
        "用例状态", max_length=16, choices=CASE_STATUS_CHOICES, default="pending",
        db_index=True,
    )
    duration_ms = models.IntegerField("耗时(毫秒)", default=0)
    steps = models.JSONField("步骤结果", default=list, blank=True)
    screenshots = models.JSONField("截图", default=list, blank=True)
    error_message = models.TextField("错误信息", blank=True, default="")
    step_log = models.JSONField("步骤日志", default=list, blank=True)

    class Meta:
        db_table = "aits_web_ui_case_execution_detail"
        verbose_name = "Web UI 用例执行明细"
        verbose_name_plural = "Web UI 用例执行明细"
        ordering = ["id"]

    def __str__(self):
        return f"{self.case_name} ({self.status})"


class WebPage(TimeStampedModel):
    """A page of the system under test (Page Object Model root)."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="web_pages",
        verbose_name="项目",
    )
    name = models.CharField("页面名称", max_length=128)
    url = models.CharField("页面地址", max_length=500, blank=True, default="")
    description = models.TextField("页面描述", blank=True, default="")

    class Meta:
        db_table = "aits_web_page"
        verbose_name = "Web 页面(POM)"
        verbose_name_plural = "Web 页面(POM)"
        ordering = ["-created_at"]
        unique_together = ("project", "name")

    def __str__(self):
        return self.name

    @property
    def element_count(self) -> int:
        return self.elements.count()


class WebElement(TimeStampedModel):
    """A locatable element of a :class:`WebPage` (POM element)."""

    page = models.ForeignKey(
        WebPage, on_delete=models.CASCADE, related_name="elements",
        verbose_name="所属页面",
    )
    name = models.CharField("元素名称", max_length=128)
    locator_type = models.CharField(
        "定位方式", max_length=16, choices=LOCATOR_TYPE_CHOICES, default="css"
    )
    locator_value = models.CharField("定位值", max_length=500)
    description = models.CharField("元素描述", max_length=255, blank=True, default="")
    alternatives = models.JSONField("备选定位", default=list, blank=True)

    class Meta:
        db_table = "aits_web_element"
        verbose_name = "Web 页面元素(POM)"
        verbose_name_plural = "Web 页面元素(POM)"
        ordering = ["id"]
        unique_together = ("page", "name")

    def __str__(self):
        return f"{self.page.name}/{self.name}"

    @property
    def project(self):
        """Convenience accessor so generic project scoping helpers work."""
        return self.page.project if self.page_id else None

    def locators(self) -> list:
        """Primary locator first, then all usable ``alternatives``."""
        result = [(self.locator_type, self.locator_value)]
        for item in self.alternatives or []:
            if isinstance(item, dict):
                locator_type = item.get("locator_type") or item.get("type") or "css"
                value = item.get("locator_value") or item.get("value") or ""
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                locator_type, value = item[0], item[1]
            else:
                locator_type, value = "css", str(item)
            if value:
                result.append((str(locator_type), str(value)))
        return result


class MidSceneScript(TimeStampedModel):
    """A MidScene (YAML/Python) script, optionally bound to a test case."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="midscene_scripts",
        verbose_name="项目",
    )
    name = models.CharField("脚本名称", max_length=255)
    description = models.TextField("脚本描述", blank=True, default="")
    script_type = models.CharField(
        "脚本类型", max_length=16, choices=MIDSCENE_SCRIPT_TYPE_CHOICES, default="yaml"
    )
    content = models.TextField("脚本内容", blank=True, default="")
    case = models.ForeignKey(
        WebUITestCase, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="midscene_scripts", verbose_name="关联用例",
    )
    status = models.CharField(
        "状态", max_length=16, choices=MIDSCENE_STATUS_CHOICES, default="draft",
        db_index=True,
    )

    class Meta:
        db_table = "aits_midscene_script"
        verbose_name = "MidScene 脚本"
        verbose_name_plural = "MidScene 脚本"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
