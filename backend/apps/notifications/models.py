"""通知中心领域模型。

分层（见 docs/ARCHITECTURE.md §2.9 / 设计文档 §7）：

    NotificationChannel (全局渠道)
        └── NotificationReceiver (项目级接收对象)

    EmailConfig   (SMTP 单例配置，独立于渠道)
    NotificationLog (每次发送的审计日志)

说明：
* ``NotificationReceiver.project`` 允许为空，表示全局接收对象（仅 is_staff 可维护）。
* ``NotificationLog`` 通过整数 + 名称字段弱引用 scheduled_tasks，避免与尚未完成的
  ``apps.scheduled_tasks`` 产生迁移/导入耦合，可独立测试。
"""

from django.db import models

from apps.common.models import TimeStampedModel

# ---------------------------------------------------------------------------
# channel codes
# ---------------------------------------------------------------------------
CHANNEL_DINGTALK = "dingtalk"
CHANNEL_WECHAT_WORK = "wechat_work"
CHANNEL_FEISHU = "feishu"
CHANNEL_EMAIL = "email"
CHANNEL_WEBHOOK = "webhook"

CHANNEL_CHOICES = (
    (CHANNEL_DINGTALK, "钉钉"),
    (CHANNEL_WECHAT_WORK, "企业微信"),
    (CHANNEL_FEISHU, "飞书"),
    (CHANNEL_EMAIL, "邮件"),
    (CHANNEL_WEBHOOK, "Webhook"),
)

CHANNEL_CODES = tuple(code for code, _label in CHANNEL_CHOICES)

#: 通过 HTTP webhook 投递的渠道（email 走 SMTP）
WEBHOOK_CHANNEL_CODES = (
    CHANNEL_DINGTALK,
    CHANNEL_WECHAT_WORK,
    CHANNEL_FEISHU,
    CHANNEL_WEBHOOK,
)

LOG_STATUS_SUCCESS = "success"
LOG_STATUS_FAILED = "failed"
LOG_STATUS_CHOICES = (
    (LOG_STATUS_SUCCESS, "成功"),
    (LOG_STATUS_FAILED, "失败"),
)

TRIGGER_ALWAYS = "always"
TRIGGER_FAIL = "fail"
TRIGGER_CONDITION_CHOICES = (
    (TRIGGER_ALWAYS, "总是通知"),
    (TRIGGER_FAIL, "仅失败时通知"),
)


class NotificationChannel(TimeStampedModel):
    """全局通知渠道元数据（钉钉 / 企微 / 飞书 / 邮件 / 通用 Webhook）。"""

    channel_code = models.CharField(
        "渠道编码", max_length=32, choices=CHANNEL_CHOICES, unique=True, db_index=True
    )
    name = models.CharField("渠道名称", max_length=64)
    description = models.TextField("渠道说明", blank=True, default="")
    is_active = models.BooleanField("是否启用", default=True, db_index=True)
    config_schema = models.JSONField("配置模板", default=dict, blank=True)

    class Meta:
        db_table = "aits_notification_channel"
        verbose_name = "通知渠道"
        verbose_name_plural = "通知渠道"
        ordering = ["id"]

    def __str__(self):
        return f"{self.name}({self.channel_code})"


class NotificationReceiver(TimeStampedModel):
    """项目级通知接收对象：渠道 + Webhook 地址或邮箱列表。"""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notification_receivers",
        verbose_name="项目",
    )
    name = models.CharField("接收对象名称", max_length=128)
    channel = models.ForeignKey(
        NotificationChannel,
        on_delete=models.PROTECT,
        related_name="receivers",
        verbose_name="通知渠道",
    )
    webhook_url = models.URLField("Webhook 地址", max_length=500, blank=True, default="")
    target_address = models.TextField(
        "目标地址", blank=True, default="", help_text="邮件接收地址，多个用逗号分隔"
    )
    is_active = models.BooleanField("是否启用", default=True, db_index=True)
    description = models.TextField("说明", blank=True, default="")
    metadata = models.JSONField("扩展元数据", default=dict, blank=True)

    class Meta:
        db_table = "aits_notification_receiver"
        verbose_name = "通知接收对象"
        verbose_name_plural = "通知接收对象"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "is_active"])]

    def __str__(self):
        return self.name

    @property
    def channel_code(self) -> str:
        return self.channel.channel_code if self.channel_id else ""

    def email_targets(self) -> list:
        """Return the comma separated ``target_address`` as a clean list."""
        raw = (self.target_address or "").replace(";", ",").replace("，", ",")
        return [item.strip() for item in raw.split(",") if item.strip()]


class EmailConfig(TimeStampedModel):
    """SMTP 配置（单例语义：最多只有一条 ``is_active=True`` 的记录）。"""

    host = models.CharField("SMTP 主机", max_length=255, blank=True, default="")
    port = models.IntegerField("端口", default=465)
    username = models.CharField("用户名", max_length=255, blank=True, default="")
    password = models.CharField("密码/授权码", max_length=255, blank=True, default="")
    from_email = models.EmailField("发件人", blank=True, default="")
    use_ssl = models.BooleanField("使用 SSL", default=True)
    use_tls = models.BooleanField("使用 TLS", default=False)
    is_active = models.BooleanField("是否启用", default=True, db_index=True)

    class Meta:
        db_table = "aits_email_config"
        verbose_name = "邮件配置"
        verbose_name_plural = "邮件配置"
        ordering = ["-is_active", "-updated_at"]

    def __str__(self):
        return f"{self.host or '(未配置)'}:{self.port}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # 单例语义：启用当前配置时，其余配置自动停用。
        if self.is_active:
            EmailConfig.objects.exclude(pk=self.pk).filter(is_active=True).update(
                is_active=False
            )

    @classmethod
    def get_solo(cls):
        """Return the currently active config (fallback: the newest one)."""
        return cls.objects.filter(is_active=True).order_by("-updated_at").first() or (
            cls.objects.order_by("-updated_at").first()
        )


class NotificationLog(TimeStampedModel):
    """一次渠道发送的审计日志；单渠道失败也要落库。"""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notification_logs",
        verbose_name="项目",
    )
    receiver = models.ForeignKey(
        NotificationReceiver,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
        verbose_name="接收对象",
    )
    channel_code = models.CharField(
        "渠道编码", max_length=32, choices=CHANNEL_CHOICES, db_index=True
    )
    title = models.CharField("标题", max_length=255)
    content = models.TextField("内容", blank=True, default="")
    status = models.CharField(
        "发送状态", max_length=16, choices=LOG_STATUS_CHOICES, default=LOG_STATUS_SUCCESS,
        db_index=True,
    )
    error_message = models.TextField("错误信息", blank=True, default="")
    payload = models.JSONField("请求载荷", default=dict, blank=True)
    # 弱引用 scheduled_tasks，避免跨 app 硬依赖（该 app 尚未完成时仍可独立迁移/测试）。
    scheduled_task_id = models.IntegerField("定时任务 ID", null=True, blank=True, db_index=True)
    scheduled_task_name = models.CharField("定时任务名称", max_length=255, blank=True, default="")
    task_execution_log_id = models.IntegerField(
        "任务执行记录 ID", null=True, blank=True, db_index=True
    )

    class Meta:
        db_table = "aits_notification_log"
        verbose_name = "通知日志"
        verbose_name_plural = "通知日志"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "status"]),
            models.Index(fields=["channel_code", "status"]),
        ]

    def __str__(self):
        return f"{self.channel_code}:{self.title}:{self.status}"
