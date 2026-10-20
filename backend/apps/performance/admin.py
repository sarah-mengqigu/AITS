"""Django admin registrations for the performance module."""

from django.contrib import admin

from apps.performance.models import (
    AiDiagnosisRecord,
    LoadConfiguration,
    PerformanceExecution,
    PerformanceScenario,
)


@admin.register(LoadConfiguration)
class LoadConfigurationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "users", "spawn_rate",
                    "duration_seconds", "host", "created_at")
    list_filter = ("project",)
    search_fields = ("name", "host")


@admin.register(PerformanceScenario)
class PerformanceScenarioAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "source_type", "endpoint_count",
                    "config", "is_active", "created_at")
    list_filter = ("project", "source_type", "is_active")
    search_fields = ("name", "description")


@admin.register(PerformanceExecution)
class PerformanceExecutionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "scenario", "status", "trigger_type",
                    "avg_tps", "p95_response_time", "error_rate", "created_at")
    list_filter = ("project", "status", "trigger_type")
    search_fields = ("name", "error_message")


@admin.register(AiDiagnosisRecord)
class AiDiagnosisRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "alert_name", "project", "source", "severity", "status",
                    "created_at")
    list_filter = ("project", "source", "status", "severity")
    search_fields = ("alert_name", "diagnosis_content")
