from django.apps import AppConfig


class AppTestingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.app_testing"
    label = "app_testing"
    verbose_name = "移动端 App 测试"
