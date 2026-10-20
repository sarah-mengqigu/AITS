"""DRF serializers for the AI 核心 module."""

from __future__ import annotations

from rest_framework import serializers

from apps.ai_core.models import (
    LLMConfiguration,
    LLMUsageLog,
    MCPConfiguration,
    MCPTool,
    RAGConfiguration,
    is_masked_api_key,
    mask_api_key,
)


class MaskedApiKeyField(serializers.CharField):
    """Write a real key, read back only ``sk-****last4``."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_blank", True)
        kwargs.setdefault("max_length", 512)
        super().__init__(**kwargs)

    def to_representation(self, value):
        return mask_api_key(value)

    def to_internal_value(self, data):
        if data is None:
            return ""
        return super().to_internal_value(data)


class LLMConfigurationSerializer(serializers.ModelSerializer):
    api_key = MaskedApiKeyField()

    class Meta:
        model = LLMConfiguration
        fields = (
            "id",
            "project",
            "name",
            "provider",
            "model_name",
            "api_key",
            "base_url",
            "model_type",
            "temperature",
            "max_tokens",
            "is_default",
            "is_active",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_temperature(self, value):
        if value is None or not (0 <= float(value) <= 2):
            raise serializers.ValidationError("temperature 必须在 0~2 之间")
        return value

    def validate_max_tokens(self, value):
        if value is not None and int(value) < 1:
            raise serializers.ValidationError("max_tokens 必须大于 0")
        return value

    def create(self, validated_data):
        if is_masked_api_key(validated_data.get("api_key")):
            validated_data["api_key"] = ""
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Echoed masked values must never overwrite the real key.
        if is_masked_api_key(validated_data.get("api_key")):
            validated_data.pop("api_key", None)
        return super().update(instance, validated_data)


class RAGConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = RAGConfiguration
        fields = (
            "id",
            "project",
            "name",
            "vector_store",
            "embedding_mode",
            "embedding_model",
            "embedding_path",
            "chunk_size",
            "chunk_overlap",
            "collection_name",
            "connection",
            "is_default",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        chunk_size = attrs.get(
            "chunk_size", getattr(self.instance, "chunk_size", 1000)
        )
        chunk_overlap = attrs.get(
            "chunk_overlap", getattr(self.instance, "chunk_overlap", 200)
        )
        if int(chunk_size) < 1:
            raise serializers.ValidationError({"chunk_size": "chunk_size 必须为正整数"})
        if int(chunk_overlap) >= int(chunk_size):
            raise serializers.ValidationError(
                {"chunk_overlap": "chunk_overlap 必须小于 chunk_size"}
            )
        return attrs


class MCPToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = MCPTool
        fields = (
            "id",
            "config",
            "name",
            "description",
            "input_schema",
            "is_enabled",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class MCPConfigurationSerializer(serializers.ModelSerializer):
    tool_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = MCPConfiguration
        fields = (
            "id",
            "project",
            "name",
            "transport",
            "server_config",
            "is_active",
            "last_status",
            "tool_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "last_status", "tool_count", "created_at", "updated_at")


class LLMUsageLogSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True, default="")
    model_name = serializers.CharField(source="config.model_name", read_only=True, default="")
    provider = serializers.CharField(source="config.provider", read_only=True, default="")

    class Meta:
        model = LLMUsageLog
        fields = (
            "id",
            "project",
            "project_name",
            "config",
            "model_name",
            "provider",
            "agent_name",
            "task_type",
            "task_id",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "response_time_ms",
            "success",
            "error_message",
            "request_preview",
            "response_preview",
            "created_at",
        )
        read_only_fields = fields
