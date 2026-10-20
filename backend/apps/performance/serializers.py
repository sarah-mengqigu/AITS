"""Serializers for the 性能测试 module (``/api/performance/``)."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.api.api_exception_handler import BusinessError
from apps.performance.models import (
    AiDiagnosisRecord,
    LoadConfiguration,
    PerformanceExecution,
    PerformanceScenario,
)


class LoadConfigurationSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = LoadConfiguration
        fields = (
            "id",
            "project",
            "project_name",
            "name",
            "users",
            "spawn_rate",
            "duration_seconds",
            "host",
            "config",
            "description",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_users(self, value):
        if value is None or value < 1:
            raise serializers.ValidationError("并发用户数必须大于 0")
        return value

    def validate_spawn_rate(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("并发增长率必须大于 0")
        return value

    def validate_duration_seconds(self, value):
        if value is None or value < 1:
            raise serializers.ValidationError("持续时间必须大于 0 秒")
        return value

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        project = attrs.get("project") or getattr(instance, "project", None)
        if project is None:
            raise serializers.ValidationError({"project": "必须指定项目"})
        return attrs


class PerformanceScenarioSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True)
    source_suite_name = serializers.CharField(source="source_suite.name", read_only=True,
                                              allow_null=True)
    source_case_name = serializers.CharField(source="source_case.name", read_only=True,
                                             allow_null=True)
    config_name = serializers.CharField(source="config.name", read_only=True, allow_null=True)

    class Meta:
        model = PerformanceScenario
        fields = (
            "id",
            "project",
            "project_name",
            "name",
            "description",
            "source_type",
            "source_suite",
            "source_suite_name",
            "source_case",
            "source_case_name",
            "custom_script",
            "endpoint_count",
            "config",
            "config_name",
            "variables",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        project = attrs.get("project") or getattr(instance, "project", None)
        if project is None:
            raise serializers.ValidationError({"project": "必须指定项目"})
        source_type = attrs.get("source_type") or getattr(
            instance, "source_type", "api_suite"
        )
        suite = attrs.get("source_suite", getattr(instance, "source_suite", None))
        case = attrs.get("source_case", getattr(instance, "source_case", None))
        # A performance project may consume API projects through
        # ``Project.linked_api_projects``; both are valid sources.
        allowed_projects = {project.id}
        try:
            allowed_projects.update(
                project.linked_api_projects.values_list("id", flat=True)
            )
        except Exception:  # noqa: BLE001 - M2M always exists, defensive only
            pass
        if source_type == "api_suite":
            if suite is None:
                raise serializers.ValidationError(
                    {"source_suite": "api_suite 场景必须选择来源 API 套件"}
                )
            if suite.project_id not in allowed_projects:
                raise serializers.ValidationError(
                    {"source_suite": "来源套件必须属于当前项目或已关联的 API 项目"}
                )
        elif source_type == "api_case":
            if case is None:
                raise serializers.ValidationError(
                    {"source_case": "api_case 场景必须选择来源 API 用例"}
                )
            if case.project_id not in allowed_projects:
                raise serializers.ValidationError(
                    {"source_case": "来源用例必须属于当前项目或已关联的 API 项目"}
                )
        config = attrs.get("config", getattr(instance, "config", None))
        if config is not None and config.project_id != project.id:
            raise serializers.ValidationError({"config": "负载配置与场景项目不一致"})
        variables = attrs.get("variables")
        if variables is not None and not isinstance(variables, dict):
            raise serializers.ValidationError({"variables": "变量必须是 JSON 对象"})
        return attrs


class PerformanceExecutionSerializer(serializers.ModelSerializer):
    scenario_name = serializers.CharField(source="scenario.name", read_only=True)
    config_name = serializers.CharField(source="config.name", read_only=True, allow_null=True)
    project_name = serializers.CharField(source="project.name", read_only=True)
    status_label = serializers.SerializerMethodField()
    is_finished = serializers.BooleanField(read_only=True)

    class Meta:
        model = PerformanceExecution
        fields = (
            "id",
            "project",
            "project_name",
            "scenario",
            "scenario_name",
            "config",
            "config_name",
            "name",
            "status",
            "status_label",
            "trigger_type",
            "started_at",
            "finished_at",
            "duration_ms",
            "total_requests",
            "avg_tps",
            "p50_response_time",
            "p95_response_time",
            "p99_response_time",
            "error_rate",
            "status_code_dist",
            "csv_path",
            "report_path",
            "summary",
            "celery_task_id",
            "error_message",
            "is_finished",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_status_label(self, obj) -> str:
        return obj.get_status_display()


class AiDiagnosisRecordSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True, allow_null=True)
    execution_name = serializers.CharField(source="execution.name", read_only=True,
                                           allow_null=True)
    status_label = serializers.SerializerMethodField()

    class Meta:
        model = AiDiagnosisRecord
        fields = (
            "id",
            "project",
            "project_name",
            "execution",
            "execution_name",
            "source",
            "alert_name",
            "severity",
            "grafana_url",
            "diagnosis_content",
            "status",
            "status_label",
            "notified_at",
            "resolved_at",
            "raw_payload",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "project",
            "execution",
            "source",
            "alert_name",
            "grafana_url",
            "notified_at",
            "raw_payload",
            "created_at",
            "updated_at",
        )

    def get_status_label(self, obj) -> str:
        return obj.get_status_display()

    def validate_status(self, value):
        if value not in ("pending", "resolved", "ignored"):
            raise serializers.ValidationError("状态必须是 pending/resolved/ignored 之一")
        return value

    def update(self, instance, validated_data):
        from django.utils import timezone

        if "status" in validated_data:
            status = validated_data["status"]
            if status == "resolved" and validated_data.get("resolved_at") is None:
                instance.resolved_at = timezone.now()
            elif status == "pending":
                instance.resolved_at = None
        if "resolved_at" in validated_data:
            instance.resolved_at = validated_data["resolved_at"]
        for field in ("diagnosis_content", "severity", "status"):
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        instance.save()
        return instance


class ManualDiagnosisSerializer(serializers.Serializer):
    """Body for ``POST /api/performance/diagnoses/`` (manual diagnosis)."""

    execution = serializers.IntegerField(required=False, allow_null=True)
    project = serializers.IntegerField(required=False, allow_null=True)
    alert_name = serializers.CharField(required=False, allow_blank=True, default="")
    severity = serializers.CharField(required=False, allow_blank=True, default="")
    grafana_url = serializers.CharField(required=False, allow_blank=True, default="")
    raw_payload = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        execution_id = attrs.get("execution")
        if execution_id is not None:
            execution = PerformanceExecution.objects.filter(pk=execution_id).first()
            if execution is None:
                raise BusinessError(message="执行记录不存在", code="not_found", status_code=404)
            attrs["execution_obj"] = execution
        elif not attrs.get("project"):
            raise serializers.ValidationError(
                {"execution": "必须提供 execution 或 project 之一"}
            )
        return attrs
