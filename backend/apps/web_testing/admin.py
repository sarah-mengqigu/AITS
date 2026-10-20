from django.contrib import admin

from apps.web_testing.models import (
    MidSceneScript,
    WebElement,
    WebPage,
    WebUITestCase,
    WebUITestCaseExecutionDetail,
    WebUITestExecution,
    WebUITestModule,
    WebUITestSuite,
)


class WebUITestModuleInline(admin.TabularInline):
    model = WebUITestModule
    fk_name = "parent"
    extra = 0
    fields = ("name", "order", "description")


@admin.register(WebUITestModule)
class WebUITestModuleAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "parent", "order", "created_at")
    list_filter = ("project",)
    search_fields = ("name", "description")
    ordering = ("project", "order", "id")
    inlines = [WebUITestModuleInline]


@admin.register(WebUITestCase)
class WebUITestCaseAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "module", "case_type", "script_type",
                    "priority", "is_active", "created_at")
    list_filter = ("project", "case_type", "script_type", "priority", "source",
                   "is_active")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(WebUITestSuite)
class WebUITestSuiteAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "browser", "headless", "case_count",
                    "is_active", "created_at")
    list_filter = ("project", "browser", "is_active")
    search_fields = ("name", "description")


@admin.register(WebUITestExecution)
class WebUITestExecutionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "suite", "status", "trigger_type",
                    "browser", "total", "passed", "failed", "pass_rate", "duration_ms",
                    "created_at")
    list_filter = ("project", "status", "trigger_type", "browser")
    search_fields = ("name", "error_message")
    readonly_fields = ("created_at", "updated_at")


@admin.register(WebUITestCaseExecutionDetail)
class WebUITestCaseExecutionDetailAdmin(admin.ModelAdmin):
    list_display = ("id", "execution", "case_name", "status", "duration_ms")
    list_filter = ("status",)
    search_fields = ("case_name", "error_message")


class WebElementInline(admin.TabularInline):
    model = WebElement
    extra = 0
    fields = ("name", "locator_type", "locator_value", "alternatives")


@admin.register(WebPage)
class WebPageAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "url", "created_at")
    list_filter = ("project",)
    search_fields = ("name", "url", "description")
    inlines = [WebElementInline]


@admin.register(WebElement)
class WebElementAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "page", "locator_type", "locator_value")
    list_filter = ("locator_type",)
    search_fields = ("name", "locator_value", "description")


@admin.register(MidSceneScript)
class MidSceneScriptAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "script_type", "case", "status",
                    "created_at")
    list_filter = ("project", "script_type", "status")
    search_fields = ("name", "description", "content")
