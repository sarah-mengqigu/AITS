"""AI 核心模块模型：LLM 配置 / RAG 配置 / MCP 配置与工具 / 用量日志。

契约见 ``docs/ARCHITECTURE.md`` §2.7。所有模型继承 ``TimeStampedModel``，
``project`` 为空表示全局配置（仅 staff 可写）。
"""

from datetime import timedelta

from django.db import models, transaction
from django.utils import timezone

from apps.common.models import TimeStampedModel

PROVIDER_CHOICES = (
    ("openai", "OpenAI"),
    ("deepseek", "DeepSeek"),
    ("qwen", "通义千问"),
    ("huggingface", "HuggingFace"),
    ("azure", "Azure OpenAI"),
    ("mock", "Mock（离线确定性）"),
)

MODEL_TYPE_CHOICES = (
    ("text", "文本"),
    ("vision", "视觉"),
)

VECTOR_STORE_CHOICES = (
    ("chroma", "Chroma"),
    ("milvus", "Milvus"),
)

EMBEDDING_MODE_CHOICES = (
    ("local", "本地哈希嵌入"),
    ("remote", "远程嵌入服务"),
)

MCP_TRANSPORT_CHOICES = (
    ("stdio", "stdio"),
    ("sse", "SSE"),
    ("streamable_http", "Streamable HTTP"),
)


def mask_api_key(raw: str) -> str:
    """Only ever echo ``sk-****last4`` for a stored API key."""
    raw = raw or ""
    if not raw:
        return ""
    tail = raw[-4:] if len(raw) >= 4 else raw
    return f"sk-****{tail}"


def is_masked_api_key(value: str) -> bool:
    return isinstance(value, str) and value.startswith("sk-****")


class LLMConfiguration(TimeStampedModel):
    """One LLM endpoint configuration (project scoped or global)."""

    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="llm_configs",
        verbose_name="项目",
    )
    name = models.CharField("配置名称", max_length=128)
    provider = models.CharField(
        "提供商", max_length=32, choices=PROVIDER_CHOICES, default="openai", db_index=True
    )
    model_name = models.CharField("模型名称", max_length=128, blank=True, default="")
    api_key = models.TextField("API Key", blank=True, default="")
    base_url = models.CharField("Base URL", max_length=500, blank=True, default="")
    model_type = models.CharField(
        "模型类型", max_length=16, choices=MODEL_TYPE_CHOICES, default="text", db_index=True
    )
    temperature = models.FloatField("温度", default=0.7)
    max_tokens = models.IntegerField("最大 Token", default=2048)
    is_default = models.BooleanField("是否默认", default=False, db_index=True)
    is_active = models.BooleanField("是否启用", default=True, db_index=True)
    extra = models.JSONField("扩展参数", default=dict, blank=True)

    class Meta:
        db_table = "aits_llm_configuration"
        verbose_name = "LLM 配置"
        verbose_name_plural = "LLM 配置"
        ordering = ["-is_default", "-updated_at", "-id"]
        indexes = [models.Index(fields=["project", "model_type", "is_default"])]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "model_type", "name"],
                name="uniq_llm_config_project_type_name",
            )
        ]

    def __str__(self):
        scope = self.project.name if self.project_id else "全局"
        return f"{scope}/{self.name}({self.provider})"

    def save(self, *args, **kwargs):
        # One default per (project, model_type): flip the siblings off first.
        if self.is_default:
            siblings = LLMConfiguration.objects.filter(
                project=self.project, model_type=self.model_type
            )
            if self.pk:
                siblings = siblings.exclude(pk=self.pk)
            siblings.update(is_default=False)
        super().save(*args, **kwargs)

    @property
    def masked_api_key(self) -> str:
        return mask_api_key(self.api_key)

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.provider != "mock")

    def usage_stat(self, days: int = 30) -> dict:
        since = timezone.now() - timedelta(days=days)
        agg = self.usage_logs.filter(created_at__gte=since).aggregate(
            requests=models.Count("id"),
            prompt_tokens=models.Sum("prompt_tokens"),
            completion_tokens=models.Sum("completion_tokens"),
            total_tokens=models.Sum("total_tokens"),
        )
        return {key: value or 0 for key, value in agg.items()}


class RAGConfiguration(TimeStampedModel):
    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="rag_configs",
        verbose_name="项目",
    )
    name = models.CharField("配置名称", max_length=128)
    vector_store = models.CharField(
        "向量库", max_length=16, choices=VECTOR_STORE_CHOICES, default="chroma"
    )
    embedding_mode = models.CharField(
        "嵌入模式", max_length=16, choices=EMBEDDING_MODE_CHOICES, default="local"
    )
    embedding_model = models.CharField(
        "嵌入模型", max_length=128, blank=True, default="aits-hash-64"
    )
    embedding_path = models.CharField("嵌入模型路径", max_length=500, blank=True, default="")
    chunk_size = models.PositiveIntegerField("分块大小", default=1000)
    chunk_overlap = models.PositiveIntegerField("分块重叠", default=200)
    collection_name = models.CharField("集合名称", max_length=128, blank=True, default="")
    connection = models.JSONField("连接配置", default=dict, blank=True)
    is_default = models.BooleanField("是否默认", default=False, db_index=True)

    class Meta:
        db_table = "aits_rag_configuration"
        verbose_name = "RAG 配置"
        verbose_name_plural = "RAG 配置"
        ordering = ["-is_default", "-updated_at", "-id"]
        indexes = [models.Index(fields=["project", "is_default"])]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"], name="uniq_rag_config_project_name"
            )
        ]

    def __str__(self):
        scope = self.project.name if self.project_id else "全局"
        return f"{scope}/{self.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            RAGConfiguration.objects.filter(project=self.project).exclude(pk=self.pk).update(
                is_default=False
            )

    @property
    def effective_chunk_overlap(self) -> int:
        size = int(self.chunk_size or 0)
        if size <= 0:
            return 0
        return min(int(self.chunk_overlap or 0), max(size - 1, 0))


class MCPConfiguration(TimeStampedModel):
    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="mcp_configs",
        verbose_name="项目",
    )
    name = models.CharField("配置名称", max_length=128)
    transport = models.CharField(
        "传输方式", max_length=32, choices=MCP_TRANSPORT_CHOICES, default="stdio"
    )
    server_config = models.JSONField("服务端配置", default=dict, blank=True)
    is_active = models.BooleanField("是否启用", default=True, db_index=True)
    last_status = models.CharField("最近状态", max_length=32, blank=True, default="unknown")

    class Meta:
        db_table = "aits_mcp_configuration"
        verbose_name = "MCP 配置"
        verbose_name_plural = "MCP 配置"
        ordering = ["-updated_at", "-id"]
        indexes = [models.Index(fields=["project", "is_active"])]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"], name="uniq_mcp_config_project_name"
            )
        ]

    def __str__(self):
        scope = self.project.name if self.project_id else "全局"
        return f"{scope}/{self.name}"

    # ------------------------------------------------------------------
    # tool discovery (offline / deterministic; no network in mock mode)
    # ------------------------------------------------------------------
    def _declared_tools(self) -> list[dict]:
        """Tools declared in ``server_config['tools']``."""
        config = self.server_config or {}
        raw = config.get("tools")
        if isinstance(raw, dict):  # {"tools": {"list_files": {...}}}
            raw = [dict(spec or {}, name=name) for name, spec in raw.items()]
        if not isinstance(raw, list):
            return []
        tools = []
        for item in raw:
            if isinstance(item, str):
                item = {"name": item}
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("tool") or ""
            if not name:
                continue
            tools.append(
                {
                    "name": str(name),
                    "description": str(item.get("description") or ""),
                    "input_schema": item.get("input_schema")
                    or item.get("inputSchema")
                    or item.get("schema")
                    or {},
                }
            )
        return tools

    def _fallback_tools(self) -> list[dict]:
        """Deterministic placeholder tool so offline runs still see something."""
        slug = "".join(ch if ch.isalnum() else "_" for ch in (self.name or "mcp")).lower()
        slug = slug.strip("_") or "mcp"
        return [
            {
                "name": f"{slug}_ping",
                "description": "离线占位工具：探测 MCP 服务是否可达",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]

    def discover_tools(self) -> list[dict]:
        tools = self._declared_tools()
        if tools:
            return tools
        return self._fallback_tools()

    def langchain_tools(self) -> list:
        """Expose the discovered tools as LangChain ``StructuredTool`` objects."""
        from apps.ai_core.services.langchain_bridge import build_mcp_tools

        return build_mcp_tools(self)

    def refresh_tools(self) -> dict:
        """Sync ``MCPTool`` rows from the server config.

        Returns ``{"status", "count", "tools"}`` where ``tools`` is a list of dicts.
        """
        tools = self.discover_tools()
        names = [tool["name"] for tool in tools]
        with transaction.atomic():
            if names:
                MCPTool.objects.filter(config=self).exclude(name__in=names).delete()
            else:
                MCPTool.objects.filter(config=self).delete()
            for spec in tools:
                MCPTool.objects.update_or_create(
                    config=self,
                    name=spec["name"],
                    defaults={
                        "description": spec.get("description") or "",
                        "input_schema": spec.get("input_schema") or {},
                    },
                )
            self.last_status = "connected" if self.is_active else "disabled"
            self.save(update_fields=["last_status", "updated_at"])
        return {
            "status": self.last_status,
            "count": len(tools),
            "tools": [
                {
                    "name": tool["name"],
                    "description": tool.get("description") or "",
                    "input_schema": tool.get("input_schema") or {},
                }
                for tool in tools
            ],
        }

    @property
    def tool_count(self) -> int:
        return self.tools.count()


class MCPTool(TimeStampedModel):
    config = models.ForeignKey(
        MCPConfiguration, on_delete=models.CASCADE, related_name="tools", verbose_name="MCP 配置"
    )
    name = models.CharField("工具名称", max_length=128)
    description = models.TextField("工具描述", blank=True, default="")
    input_schema = models.JSONField("入参 Schema", default=dict, blank=True)
    is_enabled = models.BooleanField("是否启用", default=True)

    class Meta:
        db_table = "aits_mcp_tool"
        verbose_name = "MCP 工具"
        verbose_name_plural = "MCP 工具"
        ordering = ["name", "id"]
        unique_together = ("config", "name")
        indexes = [models.Index(fields=["config", "is_enabled"])]

    def __str__(self):
        return f"{self.config.name}/{self.name}"


class LLMUsageLog(TimeStampedModel):
    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="llm_usage_logs",
        verbose_name="项目",
    )
    config = models.ForeignKey(
        LLMConfiguration,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="usage_logs",
        verbose_name="LLM 配置",
    )
    agent_name = models.CharField(
        "Agent 名称", max_length=64, blank=True, default="", db_index=True
    )
    task_type = models.CharField("任务类型", max_length=64, blank=True, default="", db_index=True)
    task_id = models.CharField("任务 ID", max_length=64, blank=True, default="", db_index=True)
    prompt_tokens = models.IntegerField("Prompt Token", default=0)
    completion_tokens = models.IntegerField("Completion Token", default=0)
    total_tokens = models.IntegerField("总 Token", default=0)
    response_time_ms = models.IntegerField("响应耗时(ms)", default=0)
    success = models.BooleanField("是否成功", default=True, db_index=True)
    error_message = models.TextField("错误信息", blank=True, default="")
    request_preview = models.TextField("请求预览", blank=True, default="")
    response_preview = models.TextField("响应预览", blank=True, default="")

    class Meta:
        db_table = "aits_llm_usage_log"
        verbose_name = "LLM 用量日志"
        verbose_name_plural = "LLM 用量日志"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["project", "agent_name"]),
            models.Index(fields=["config", "created_at"]),
        ]

    def __str__(self):
        return f"{self.agent_name or 'llm'}:{self.total_tokens}tok"
