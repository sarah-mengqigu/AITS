"""Django admin registration for AI 核心 models."""

from django.contrib import admin

from apps.ai_core.models import (
    LLMConfiguration,
    LLMUsageLog,
    MCPConfiguration,
    MCPTool,
    RAGConfiguration,
)


@admin.register(LLMConfiguration)
class LLMConfigurationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "provider",
        "model_name",
        "model_type",
        "project",
        "is_default",
        "is_active",
    )
    list_filter = ("provider", "model_type", "is_default", "is_active")
    search_fields = ("name", "model_name", "base_url")


@admin.register(RAGConfiguration)
class RAGConfigurationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "vector_store",
        "embedding_mode",
        "chunk_size",
        "chunk_overlap",
        "project",
        "is_default",
    )
    list_filter = ("vector_store", "embedding_mode", "is_default")
    search_fields = ("name", "collection_name")


class MCPToolInline(admin.TabularInline):
    model = MCPTool
    extra = 0


@admin.register(MCPConfiguration)
class MCPConfigurationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "transport", "project", "is_active", "last_status")
    list_filter = ("transport", "is_active", "last_status")
    search_fields = ("name",)
    inlines = [MCPToolInline]


@admin.register(MCPTool)
class MCPToolAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "config", "is_enabled")
    list_filter = ("is_enabled",)
    search_fields = ("name", "description")


@admin.register(LLMUsageLog)
class LLMUsageLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "agent_name",
        "task_type",
        "total_tokens",
        "success",
        "response_time_ms",
        "project",
        "created_at",
    )
    list_filter = ("success", "agent_name", "task_type")
    search_fields = ("agent_name", "task_id", "error_message")
    readonly_fields = tuple(field.name for field in LLMUsageLog._meta.fields)
