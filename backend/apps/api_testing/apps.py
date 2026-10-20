from django.apps import AppConfig


class ApiTestingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.api_testing"
    label = "api_testing"
    verbose_name = "API 测试"
