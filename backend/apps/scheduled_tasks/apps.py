from django.apps import AppConfig


class ScheduledTasksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.scheduled_tasks"
    label = "scheduled_tasks"
    verbose_name = "定时任务"
