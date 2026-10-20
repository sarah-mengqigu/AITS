"""Django admin registrations for the 定时任务 module."""

from django.contrib import admin

from apps.scheduled_tasks.models import ScheduledTask, TaskExecutionLog


@admin.register(ScheduledTask)
class ScheduledTaskAdmin(admin.ModelAdmin):
    list_display = (
        "id", "name", "project", "suite_type", "cron_expression", "timezone",
        "is_enabled", "last_run_at", "next_run_at",
    )
    list_filter = ("suite_type", "is_enabled", "trigger_condition", "timezone")
    search_fields = ("name", "description", "cron_expression")
    filter_horizontal = ("notice_targets",)
    readonly_fields = ("last_run_at", "next_run_at", "created_at", "updated_at")


@admin.register(TaskExecutionLog)
class TaskExecutionLogAdmin(admin.ModelAdmin):
    list_display = (
        "id", "scheduled_task_name", "task", "suite_type", "status", "total",
        "passed", "failed", "pass_rate", "duration_ms", "created_at",
    )
    list_filter = ("status", "suite_type")
    search_fields = ("scheduled_task_name", "error_message")
    readonly_fields = ("created_at", "updated_at")
