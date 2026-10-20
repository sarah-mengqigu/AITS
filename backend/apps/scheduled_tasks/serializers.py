"""DRF serializers for the 定时任务 module (ARCHITECTURE §2.8)."""

from __future__ import annotations

from rest_framework import serializers

from apps.scheduled_tasks.models import (
    DEFAULT_TASK_TIMEZONE,
    ScheduledTask,
    TaskExecutionLog,
    normalize_suite_ids,
)
from apps.scheduled_tasks.services import cron as cron_utils


class ScheduledTaskSerializer(serializers.ModelSerializer):
    """CRUD serializer — validates the cron / suite ids / environment ownership."""

    project_name = serializers.CharField(source="project.name", read_only=True)
    environment_name = serializers.CharField(
        source="environment.name", read_only=True, default=""
    )
    created_by_name = serializers.SerializerMethodField()
    notice_target_names = serializers.SerializerMethodField()
    suite_count = serializers.SerializerMethodField()
    periodic_task_name = serializers.CharField(read_only=True)

    class Meta:
        model = ScheduledTask
        fields = (
            "id", "project", "project_name", "name", "suite_type", "suite_ids",
            "suite_count", "cron_expression", "timezone", "trigger_condition",
            "environment", "environment_name", "app_run_config", "notice_targets",
            "notice_target_names", "is_enabled", "last_run_at", "next_run_at",
            "created_by", "created_by_name", "description", "periodic_task_name",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "created_by", "last_run_at", "next_run_at", "periodic_task_name",
            "created_at", "updated_at",
        )

    # -- read only helpers -------------------------------------------------
    def get_created_by_name(self, obj) -> str:
        user = obj.created_by
        if user is None:
            return ""
        return getattr(user, "display_name", "") or user.get_username()

    def get_notice_target_names(self, obj) -> list[str]:
        return [receiver.name for receiver in obj.notice_targets.all()]

    def get_suite_count(self, obj) -> int:
        return len(obj.suite_id_list)

    # -- validation --------------------------------------------------------
    def validate_suite_ids(self, value):
        try:
            return normalize_suite_ids(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_cron_expression(self, value):
        try:
            return cron_utils.validate_cron(value)
        except cron_utils.CronError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_timezone(self, value):
        if not value:
            return DEFAULT_TASK_TIMEZONE
        try:
            cron_utils.resolve_timezone(value)
        except cron_utils.CronError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value

    def validate(self, attrs):
        project = attrs.get("project") or getattr(self.instance, "project", None)
        environment = attrs.get("environment", getattr(self.instance, "environment", None))
        if (
            environment is not None
            and project is not None
            and environment.project_id != project.id
        ):
            raise serializers.ValidationError({"environment": "执行环境必须属于同一个项目"})

        targets = attrs.get("notice_targets")
        if targets and project is not None:
            foreign = [
                receiver.name
                for receiver in targets
                if receiver.project_id and receiver.project_id != project.id
            ]
            if foreign:
                raise serializers.ValidationError(
                    {"notice_targets": f"通知接收对象不属于该项目: {', '.join(foreign)}"}
                )
        return attrs

    # -- writes ------------------------------------------------------------
    def update(self, instance, validated_data):
        cron_changed = "cron_expression" in validated_data
        timezone_changed = "timezone" in validated_data
        task = super().update(instance, validated_data)
        if cron_changed or timezone_changed:
            next_run = task.compute_next_run_at()
            if next_run is not None and next_run != task.next_run_at:
                task.next_run_at = next_run
                task.save(update_fields=["next_run_at", "updated_at"])
        return task


class TaskExecutionLogSerializer(serializers.ModelSerializer):
    """Execution log (list view — ``step_log`` omitted to keep payloads small)."""

    triggered_by_name = serializers.SerializerMethodField()
    project_id = serializers.SerializerMethodField()
    task_name = serializers.CharField(source="scheduled_task_name", read_only=True)

    class Meta:
        model = TaskExecutionLog
        fields = (
            "id", "task", "task_name", "scheduled_task_name", "project_id", "suite_type",
            "status", "triggered_by", "triggered_by_name", "started_at", "finished_at",
            "duration_ms", "total", "passed", "failed", "skipped", "pass_rate",
            "report_urls", "error_message", "celery_task_id", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_triggered_by_name(self, obj) -> str:
        user = obj.triggered_by
        if user is None:
            return ""
        return getattr(user, "display_name", "") or user.get_username()

    def get_project_id(self, obj):
        return obj.task.project_id if obj.task_id else None


class TaskExecutionLogDetailSerializer(TaskExecutionLogSerializer):
    """Execution log detail — adds the raw ``step_log``."""

    class Meta(TaskExecutionLogSerializer.Meta):
        fields = TaskExecutionLogSerializer.Meta.fields + ("step_log",)
        read_only_fields = fields


class CronPreviewSerializer(serializers.Serializer):
    """Response shape of ``GET /api/scheduled-tasks/cron/preview/``."""

    valid = serializers.BooleanField()
    expression = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    next_runs = serializers.ListField(child=serializers.CharField(), required=False)
    timezone = serializers.CharField(required=False, allow_blank=True)
    message = serializers.CharField(required=False, allow_blank=True)
