from django.apps import AppConfig


class WebTestingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.web_testing"
    label = "web_testing"
    verbose_name = "Web UI 测试"
