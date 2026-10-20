"""Django admin registrations for the 移动端 App 测试 module."""

from django.contrib import admin

from apps.app_testing.models import (
    AppTestApplication,
    AppTestCase,
    AppTestModule,
    AppTestRun,
    AppTestSuite,
)


@admin.register(AppTestModule)
class AppTestModuleAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "parent", "order", "created_at")
    list_filter = ("project",)
    search_fields = ("name", "description")


@admin.register(AppTestApplication)
class AppTestApplicationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "platform", "package_name", "bundle_id",
                    "app_version")
    list_filter = ("project", "platform")
    search_fields = ("name", "package_name", "bundle_id")


@admin.register(AppTestCase)
class AppTestCaseAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "module", "application", "source",
                    "priority", "is_active")
    list_filter = ("project", "source", "priority", "is_active")
    search_fields = ("name", "description")


@admin.register(AppTestSuite)
class AppTestSuiteAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "application", "is_active", "created_at")
    list_filter = ("project", "is_active")
    search_fields = ("name", "description")


@admin.register(AppTestRun)
class AppTestRunAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "suite", "status", "trigger_type",
                    "total", "passed", "failed", "pass_rate", "created_at")
    list_filter = ("project", "status", "trigger_type")
    search_fields = ("name", "device_udid", "device_name")
    readonly_fields = ("created_at", "updated_at")
