"""Django admin registrations for the API 测试 module."""

from django.contrib import admin

from apps.api_testing.models import (
    APIEndpoint,
    APIModule,
    APISpecification,
    APITestCase,
    APITestCaseExecutionDetail,
    APITestExecution,
    APITestSuite,
    APITestSuiteExecutionDetail,
)


@admin.register(APISpecification)
class APISpecificationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "source_type", "version", "status",
                    "endpoint_count", "created_at")
    list_filter = ("source_type", "status", "project")
    search_fields = ("name", "base_url")
    readonly_fields = ("created_at", "updated_at", "endpoint_count")


@admin.register(APIModule)
class APIModuleAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "spec", "parent", "order", "created_at")
    list_filter = ("project",)
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(APIEndpoint)
class APIEndpointAdmin(admin.ModelAdmin):
    list_display = ("id", "method", "path", "project", "spec", "module", "is_active")
    list_filter = ("method", "is_active", "project")
    search_fields = ("path", "summary", "operation_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(APITestCase)
class APITestCaseAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "case_type", "test_type", "source",
                    "priority", "is_active")
    list_filter = ("case_type", "test_type", "source", "is_active", "project")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(APITestSuite)
class APITestSuiteAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "environment", "source", "is_active",
                    "created_at")
    list_filter = ("source", "is_active", "project")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(APITestExecution)
class APITestExecutionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "suite", "status", "trigger_type",
                    "total", "passed", "failed", "pass_rate", "duration_ms", "created_at")
    list_filter = ("status", "trigger_type", "project")
    search_fields = ("name", "error_message")
    readonly_fields = ("created_at", "updated_at", "started_at", "finished_at",
                       "report_path")


@admin.register(APITestCaseExecutionDetail)
class APITestCaseExecutionDetailAdmin(admin.ModelAdmin):
    list_display = ("id", "execution", "case_name", "status", "duration_ms", "order")
    list_filter = ("status",)
    search_fields = ("case_name", "error_message")
    readonly_fields = ("created_at", "updated_at")


@admin.register(APITestSuiteExecutionDetail)
class APITestSuiteExecutionDetailAdmin(admin.ModelAdmin):
    list_display = ("id", "execution", "suite_name", "status", "total", "passed",
                    "failed", "duration_ms")
    list_filter = ("status",)
    search_fields = ("suite_name",)
    readonly_fields = ("created_at", "updated_at")
