from django.apps import AppConfig


class ScheduledTasksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.scheduled_tasks"
    label = "scheduled_tasks"
    verbose_name = "定时任务"

    def ready(self):
        # Importing the module connects the post_save / post_delete receivers
        # that keep django_celery_beat in sync with ScheduledTask rows.
        from apps.scheduled_tasks import signals  # noqa: F401
