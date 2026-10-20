"""Project / membership / environment domain models."""

from django.conf import settings
from django.core.validators import MinLengthValidator
from django.db import models

from apps.common.models import TimeStampedModel

PROJECT_TYPES = (
    ("api", "API 接口测试"),
    ("web", "Web UI 测试"),
    ("app", "移动端 App 测试"),
    ("perf", "性能测试"),
)

PROJECT_ROLES = (
    ("owner", "拥有者"),
    ("admin", "管理员"),
    ("editor", "编辑"),
    ("viewer", "只读"),
)

ENVIRONMENT_TYPES = (
    ("dev", "开发环境"),
    ("test", "测试环境"),
    ("staging", "预发布环境"),
    ("prod", "生产环境"),
    ("custom", "自定义"),
)


class Project(TimeStampedModel):
    name = models.CharField("项目名称", max_length=128, validators=[MinLengthValidator(1)])
    description = models.TextField("项目描述", blank=True, default="")
    project_type = models.CharField("项目类型", max_length=16, choices=PROJECT_TYPES,
                                    default="api", db_index=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name="owned_projects", verbose_name="拥有者")
    is_active = models.BooleanField("是否启用", default=True)
    sonic_project_id = models.CharField("Sonic 项目 ID", max_length=64, blank=True, default="")
    # Perf projects may consume API projects as load sources.
    linked_api_projects = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="linked_by_perf_projects",
        verbose_name="关联的 API 项目",
    )
    tags = models.JSONField("标签", default=list, blank=True)
    settings = models.JSONField("扩展配置", default=dict, blank=True)

    class Meta:
        db_table = "aits_project"
        verbose_name = "项目"
        verbose_name_plural = "项目"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project_type", "is_active"])]

    def __str__(self):
        return self.name

    @property
    def member_count(self) -> int:
        return self.members.count()

    def user_role(self, user):
        from apps.common.permissions import get_user_role

        return get_user_role(user, self)


class ProjectMember(TimeStampedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members",
                                verbose_name="项目")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="project_memberships", verbose_name="用户")
    role = models.CharField("角色", max_length=16, choices=PROJECT_ROLES, default="editor")
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="+")

    class Meta:
        db_table = "aits_project_member"
        verbose_name = "项目成员"
        verbose_name_plural = "项目成员"
        unique_together = ("project", "user")
        ordering = ["role", "id"]

    def __str__(self):
        return f"{self.project.name}/{self.user} ({self.role})"


class Environment(TimeStampedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="environments",
                                verbose_name="项目")
    name = models.CharField("环境名称", max_length=64)
    env_type = models.CharField("环境类型", max_length=16, choices=ENVIRONMENT_TYPES,
                                default="test")
    base_url = models.URLField("Base URL", max_length=500, blank=True, default="")
    variables = models.JSONField("环境变量", default=dict, blank=True)
    headers = models.JSONField("公共请求头", default=dict, blank=True)
    is_default = models.BooleanField("是否默认", default=False)
    description = models.CharField("说明", max_length=255, blank=True, default="")

    class Meta:
        db_table = "aits_environment"
        verbose_name = "环境"
        verbose_name_plural = "环境"
        unique_together = ("project", "name")
        ordering = ["-is_default", "id"]

    def __str__(self):
        return f"{self.project.name}/{self.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            Environment.objects.filter(project=self.project).exclude(pk=self.pk).update(
                is_default=False
            )


class UploadedFile(TimeStampedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="files",
                                null=True, blank=True, verbose_name="项目")
    original_name = models.CharField("原始文件名", max_length=255)
    stored_path = models.CharField("存储路径", max_length=500)
    sha256 = models.CharField("SHA256", max_length=64, db_index=True)
    size = models.BigIntegerField("文件大小", default=0)
    content_type = models.CharField("MIME 类型", max_length=128, blank=True, default="")
    purpose = models.CharField("用途", max_length=32, blank=True, default="generic")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name="+")

    class Meta:
        db_table = "aits_uploaded_file"
        verbose_name = "上传文件"
        verbose_name_plural = "上传文件"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["sha256"])]

    def __str__(self):
        return self.original_name

    @property
    def url(self) -> str:
        return f"/media/{self.stored_path}"


class ProjectThirdPartyConfig(TimeStampedModel):
    """One row per project - third party integrations (IM webhooks etc.)."""

    project = models.OneToOneField(Project, on_delete=models.CASCADE,
                                   related_name="third_party_config", verbose_name="项目")
    dingtalk_webhook = models.URLField("钉钉 Webhook", max_length=500, blank=True, default="")
    wecom_webhook = models.URLField("企业微信 Webhook", max_length=500, blank=True, default="")
    feishu_webhook = models.URLField("飞书 Webhook", max_length=500, blank=True, default="")
    gitlab_url = models.URLField("GitLab 地址", max_length=500, blank=True, default="")
    gitlab_token = models.CharField("GitLab Token", max_length=255, blank=True, default="")
    extra = models.JSONField("扩展配置", default=dict, blank=True)

    class Meta:
        db_table = "aits_project_third_party_config"
        verbose_name = "项目第三方配置"
        verbose_name_plural = "项目第三方配置"

    def __str__(self):
        return f"{self.project.name} 第三方配置"


class KnowledgeDocument(TimeStampedModel):
    """RAG knowledge base document bound to a project."""

    STATUS_CHOICES = (
        ("pending", "待索引"),
        ("processing", "索引中"),
        ("indexed", "已索引"),
        ("failed", "索引失败"),
    )

    project = models.ForeignKey(Project, on_delete=models.CASCADE,
                                related_name="knowledge_documents", verbose_name="项目")
    title = models.CharField("标题", max_length=255)
    content = models.TextField("正文", blank=True, default="")
    source_file = models.ForeignKey(UploadedFile, on_delete=models.SET_NULL, null=True,
                                    blank=True, related_name="+")
    status = models.CharField("索引状态", max_length=16, choices=STATUS_CHOICES,
                              default="pending", db_index=True)
    chunk_count = models.IntegerField("分块数量", default=0)
    error_message = models.TextField("错误信息", blank=True, default="")
    indexed_at = models.DateTimeField("索引时间", null=True, blank=True)
    metadata = models.JSONField("元数据", default=dict, blank=True)

    class Meta:
        db_table = "aits_knowledge_document"
        verbose_name = "知识库文档"
        verbose_name_plural = "知识库文档"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
