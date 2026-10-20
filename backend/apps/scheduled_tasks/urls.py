"""Router registration for ``/api/scheduled-tasks/`` (mounted by the root urls)."""

from rest_framework.routers import DefaultRouter

from apps.scheduled_tasks.views import (
    CronViewSet,
    ScheduledTaskViewSet,
    TaskExecutionLogViewSet,
)

router = DefaultRouter()
router.register("tasks", ScheduledTaskViewSet, basename="scheduled-task")
router.register("logs", TaskExecutionLogViewSet, basename="scheduled-task-log")
router.register("cron", CronViewSet, basename="scheduled-task-cron")

urlpatterns = router.urls
