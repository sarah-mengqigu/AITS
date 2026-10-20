"""Domain models of the 定时任务 module (ARCHITECTURE §2.8).

Two models:

* :class:`ScheduledTask` — the cron definition owned by a project.  Every save
  keeps a ``django_celery_beat.PeriodicTask`` in sync (see
  :meth:`ScheduledTask.sync_periodic_task` and ``signals.py``).
* :class:`TaskExecutionLog` — one execution attempt, aggregating the stats of
  every suite configured on the task.

The beat plumbing lives here (rather than in ``signals.py``) so it can be
unit-tested without touching the signal wiring.
"""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models

from apps.common.models import TimeStampedModel
from apps.scheduled_tasks.services import cron as cron_utils

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# suite types
# ---------------------------------------------------------------------------
SUITE_TYPE_WEB = "web"
SUITE_TYPE_APP = "app"
SUITE_TYPE_API = "api"

SUITE_TYPE_CHOICES = (
    (SUITE_TYPE_WEB, "Web UI 测试"),
    (SUITE_TYPE_APP, "移动端 App 测试"),
    (SUITE_TYPE_API, "API 接口测试"),
)
SUITE_TYPE_VALUES = tuple(value for value, _label in SUITE_TYPE_CHOICES)

# ---------------------------------------------------------------------------
# notification trigger condition (mirrors apps.notifications.models)
# ---------------------------------------------------------------------------
TRIGGER_ALWAYS = "always"
TRIGGER_FAIL = "fail"
TRIGGER_CONDITION_CHOICES = (
    (TRIGGER_ALWAYS, "总是通知"),
    (TRIGGER_FAIL, "仅失败时通知"),
)
TRIGGER_CONDITION_VALUES = tuple(value for value, _label in TRIGGER_CONDITION_CHOICES)

# ---------------------------------------------------------------------------
# execution status
# ---------------------------------------------------------------------------
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"

EXECUTION_STATUS_CHOICES = (
    (STATUS_PENDING, "待执行"),
    (STATUS_RUNNING, "执行中"),
    (STATUS_PASSED, "通过"),
    (STATUS_FAILED, "失败"),
    (STATUS_ERROR, "异常"),
    (STATUS_CANCELLED, "已取消"),
)
EXECUTION_STATUS_VALUES = tuple(value for value, _label in EXECUTION_STATUS_CHOICES)
TERMINAL_EXECUTION_STATUSES = frozenset(
    {STATUS_PASSED, STATUS_FAILED, STATUS_ERROR, STATUS_CANCELLED}
)

# ---------------------------------------------------------------------------
# celery beat wiring
# ---------------------------------------------------------------------------
#: ``PeriodicTask.name`` is ``aits:scheduled_task:<id>`` (stable, unique).
PERIODIC_TASK_NAME_TEMPLATE = "aits:scheduled_task:{task_id}"
#: Celery task invoked by beat — must match ``tasks.run_scheduled_task``.
SCHEDULED_TASK_ROUTE = "apps.scheduled_tasks.tasks.run_scheduled_task"

DEFAULT_TASK_TIMEZONE = cron_utils.DEFAULT_TIMEZONE


def periodic_task_name_for(task_id) -> str:
    """Return the beat ``PeriodicTask.name`` for ``task_id``."""
    if task_id in (None, ""):
        return ""
    return PERIODIC_TASK_NAME_TEMPLATE.format(task_id=task_id)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def normalize_suite_ids(value) -> list[int]:
    """Return ``value`` as a **non empty** list of positive ints.

    Accepts ``[1, 2]``, ``["1", "2"]`` and ``[{"id": 1}]``.  Raises
    :class:`ValueError` (translated to a field error by the serializers).
    """
    if value in (None, ""):
        raise ValueError("suite_ids 不能为空，至少选择一个测试套件")
    if not isinstance(value, (list, tuple)):
        raise ValueError("suite_ids 必须是整数数组")
    cleaned: list[int] = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("id") or item.get("suite_id")
        if isinstance(item, bool):
            raise ValueError(f"suite_ids 含非法 ID: {item}")
        try:
            number = int(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"suite_ids 含非法 ID: {item}") from exc
        if number <= 0:
            raise ValueError(f"suite_ids 含非法 ID: {item}")
        cleaned.append(number)
    if not cleaned:
        raise ValueError("suite_ids 不能为空，至少选择一个测试套件")
    return cleaned


def normalize_suite_ids_quietly(value) -> list[int]:
    """Best effort variant used for defensive reads (never raises)."""
    try:
        return normalize_suite_ids(value)
    except ValueError:
        return []


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------
class ScheduledTask(TimeStampedModel):
    """A cron scheduled test execution owned by a project."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="scheduled_tasks",
        verbose_name="项目",
    )
    name = models.CharField("任务名称", max_length=255)
    suite_type = models.CharField(
        "套件类型", max_length=16, choices=SUITE_TYPE_CHOICES, default=SUITE_TYPE_API,
        db_index=True,
    )
    suite_ids = models.JSONField("套件 ID 列表", default=list, blank=True)
    cron_expression = models.CharField("cron 表达式", max_length=128)
    timezone = models.CharField("时区", max_length=64, default=DEFAULT_TASK_TIMEZONE)
    trigger_condition = models.CharField(
        "通知条件", max_length=16, choices=TRIGGER_CONDITION_CHOICES,
        default=TRIGGER_ALWAYS,
    )
    environment = models.ForeignKey(
        "projects.Environment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_tasks",
        verbose_name="执行环境",
    )
    app_run_config = models.JSONField("App 运行配置", default=dict, blank=True)
    notice_targets = models.ManyToManyField(
        "notifications.NotificationReceiver",
        blank=True,
        related_name="scheduled_tasks",
        verbose_name="通知接收对象",
    )
    is_enabled = models.BooleanField("是否启用", default=True, db_index=True)
    last_run_at = models.DateTimeField("上次执行时间", null=True, blank=True)
    next_run_at = models.DateTimeField("下次执行时间", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="创建人",
    )
    description = models.TextField("任务描述", blank=True, default="")

    class Meta:
        db_table = "aits_scheduled_task"
        verbose_name = "定时任务"
        verbose_name_plural = "定时任务"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "is_enabled"]),
            models.Index(fields=["suite_type", "is_enabled"]),
        ]

    def __str__(self):
        return f"{self.name}({self.cron_expression})"

    # -- helpers -----------------------------------------------------------
    @property
    def periodic_task_name(self) -> str:
        """Beat task name, stable across updates (``aits:scheduled_task:<id>``)."""
        return periodic_task_name_for(self.pk) or PERIODIC_TASK_NAME_TEMPLATE.format(
            task_id="new"
        )

    @property
    def suite_id_list(self) -> list[int]:
        return normalize_suite_ids_quietly(self.suite_ids)

    def compute_next_run_at(self, base=None):
        """Return the next fire time (``None`` when the cron is invalid)."""
        try:
            return cron_utils.next_run(
                self.cron_expression, timezone_name=self.timezone, base=base
            )
        except cron_utils.CronError:
            return None

    # -- validation --------------------------------------------------------
    def clean(self):
        super().clean()
        errors: dict[str, str] = {}
        try:
            self.cron_expression = cron_utils.validate_cron(self.cron_expression)
        except cron_utils.CronError as exc:
            errors["cron_expression"] = str(exc)
        try:
            cron_utils.resolve_timezone(self.timezone)
        except cron_utils.CronError as exc:
            errors["timezone"] = str(exc)
        try:
            self.suite_ids = normalize_suite_ids(self.suite_ids)
        except ValueError as exc:
            errors["suite_ids"] = str(exc)
        if errors:
            raise DjangoValidationError(errors)

    def save(self, *args, **kwargs):
        if self.app_run_config is None:
            self.app_run_config = {}
        if self.suite_ids is None:
            self.suite_ids = []
        if not self.timezone:
            self.timezone = DEFAULT_TASK_TIMEZONE
        if self.next_run_at is None and self.cron_expression:
            computed = self.compute_next_run_at()
            if computed is not None:
                self.next_run_at = computed
                update_fields = kwargs.get("update_fields")
                if update_fields is not None and "next_run_at" not in update_fields:
                    kwargs["update_fields"] = list(update_fields) + ["next_run_at"]
        super().save(*args, **kwargs)

    # -- celery beat sync --------------------------------------------------
    def sync_periodic_task(self):
        """Create/update the ``PeriodicTask`` mirroring this task (idempotent)."""
        from django_celery_beat.models import PeriodicTask

        if self.pk is None:
            return None
        name = self.periodic_task_name
        try:
            crontab = cron_utils.get_crontab_schedule(
                self.cron_expression, self.timezone
            )
        except Exception as exc:
            logger.warning(
                "scheduled task %s has an unusable cron (%r): %s",
                self.pk, self.cron_expression, exc,
            )
            # Never leave a stale beat entry behind when the cron broke.
            PeriodicTask.objects.filter(name=name).update(enabled=False)
            return None

        defaults = {
            "task": SCHEDULED_TASK_ROUTE,
            "crontab": crontab,
            "interval": None,
            "solar": None,
            "clocked": None,
            "args": json.dumps([self.pk]),
            "kwargs": "{}",
            "enabled": bool(self.is_enabled),
            "one_off": False,
            "description": f"AITS 定时任务 #{self.pk}: {self.name}"[:255],
        }
        periodic, _created = PeriodicTask.objects.update_or_create(
            name=name, defaults=defaults
        )
        return periodic

    @staticmethod
    def delete_periodic_task_by_name(name: str) -> int:
        """Delete the beat row called ``name`` (returns deleted row count)."""
        from django_celery_beat.models import PeriodicTask

        if not name:
            return 0
        try:
            deleted, _details = PeriodicTask.objects.filter(name=name).delete()
            return int(deleted)
        except Exception:  # pragma: no cover - defensive
            logger.warning("failed to delete periodic task %s", name, exc_info=True)
            return 0

    def delete_periodic_task(self, name: str | None = None) -> int:
        return self.delete_periodic_task_by_name(name or periodic_task_name_for(self.pk))

    @property
    def periodic_task(self):
        """Return the mirrored beat row (``None`` when not synced yet)."""
        from django_celery_beat.models import PeriodicTask

        if self.pk is None:
            return None
        return PeriodicTask.objects.filter(name=self.periodic_task_name).first()


class TaskExecutionLog(TimeStampedModel):
    """One execution attempt of a :class:`ScheduledTask` (all suites aggregated)."""

    task = models.ForeignKey(
        ScheduledTask,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="logs",
        verbose_name="定时任务",
    )
    scheduled_task_name = models.CharField("任务名称", max_length=255, blank=True, default="")
    suite_type = models.CharField(
        "套件类型", max_length=16, choices=SUITE_TYPE_CHOICES, default=SUITE_TYPE_API,
        db_index=True,
    )
    status = models.CharField(
        "执行状态", max_length=16, choices=EXECUTION_STATUS_CHOICES,
        default=STATUS_PENDING, db_index=True,
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
    total = models.IntegerField("用例总数", default=0)
    passed = models.IntegerField("通过", default=0)
    failed = models.IntegerField("失败", default=0)
    skipped = models.IntegerField("跳过", default=0)
    pass_rate = models.FloatField("通过率", default=0.0)
    report_urls = models.JSONField("报告地址", default=list, blank=True)
    step_log = models.JSONField("执行明细", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True, default="")
    celery_task_id = models.CharField("Celery 任务 ID", max_length=255, blank=True, default="")

    class Meta:
        db_table = "aits_task_execution_log"
        verbose_name = "定时任务执行记录"
        verbose_name_plural = "定时任务执行记录"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["task", "status"]),
            models.Index(fields=["suite_type", "status"]),
        ]

    def __str__(self):
        return f"{self.scheduled_task_name or '-'}:{self.status}"

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_EXECUTION_STATUSES
