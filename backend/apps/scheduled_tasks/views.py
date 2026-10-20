"""API views for the 定时任务 module (ARCHITECTURE §2.8).

Routes are mounted by ``aits_backend.urls`` under ``/api/scheduled-tasks/``;
this module only registers relative router paths.

Permission policy (§1.4): read = ``viewer``, write / run = ``editor``,
delete = ``admin``.  Every queryset is scoped to the projects the caller can
access.
"""

from __future__ import annotations

import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.api.api_exception_handler import BusinessError
from apps.common.pagination import StandardResultsSetPagination
from apps.common.permissions import ProjectRolePermission, require_project_role
from apps.common.task.utils import submit
from apps.projects.views import ProjectScopedViewSet, projects_for
from apps.scheduled_tasks import serializers
from apps.scheduled_tasks.models import (
    STATUS_PENDING,
    ScheduledTask,
    TaskExecutionLog,
)
from apps.scheduled_tasks.services import cron as cron_service
from apps.scheduled_tasks.tasks import run_task_now

logger = logging.getLogger(__name__)


class ScheduledTaskRolePermission(ProjectRolePermission):
    """Read = viewer, write / run / toggle = editor, delete = admin."""

    minimum_role_by_action = {"destroy": "admin", "run": "editor", "toggle": "editor"}


class ScheduledTaskViewSet(ProjectScopedViewSet):
    """``/api/scheduled-tasks/tasks/`` — CRUD + run / toggle / logs."""

    queryset = ScheduledTask.objects.select_related(
        "project", "environment", "created_by"
    ).prefetch_related("notice_targets")
    serializer_class = serializers.ScheduledTaskSerializer
    permission_classes = [IsAuthenticated, ScheduledTaskRolePermission]
    pagination_class = StandardResultsSetPagination
    filterset_fields = ("project", "suite_type", "is_enabled", "environment",
                        "trigger_condition")
    search_fields = ("name", "description", "cron_expression")
    ordering_fields = ("created_at", "updated_at", "name", "next_run_at", "last_run_at")
    project_field = "project"

    # -- writes ------------------------------------------------------------
    def perform_create(self, serializer):
        project = serializer.validated_data.get("project")
        if project is not None:
            require_project_role(self.request.user, project, "editor")
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        require_project_role(self.request.user, instance.project, "admin")
        instance.delete()

    # -- actions -----------------------------------------------------------
    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        """Run the task right now -> ``202 {task_id, log_id, status}``."""
        task = self.get_object()
        require_project_role(request.user, task.project, "editor")

        log = TaskExecutionLog.objects.create(
            task=task,
            scheduled_task_name=task.name,
            suite_type=task.suite_type,
            status=STATUS_PENDING,
            triggered_by=request.user,
        )
        # Eager in tests / offline mode: the log is already terminal afterwards,
        # so we always report the real status (still 202 + log id).
        task_result = submit(run_task_now, task.id, request.user.id, log.id)
        log.refresh_from_db()

        return Response(
            {
                "task_id": log.id,
                "log_id": log.id,
                "status": log.status,
                "scheduled_task_id": task.id,
                "celery_task_id": str(getattr(task_result, "id", "") or ""),
                "execution_log": serializers.TaskExecutionLogSerializer(log).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def toggle(self, request, pk=None):
        """Flip ``is_enabled`` (the beat ``PeriodicTask`` follows via signals)."""
        task = self.get_object()
        require_project_role(request.user, task.project, "editor")
        task.is_enabled = not task.is_enabled
        task.save(update_fields=["is_enabled", "updated_at"])
        return Response(serializers.ScheduledTaskSerializer(task).data)

    @action(detail=True, methods=["get"])
    def logs(self, request, pk=None):
        """``GET tasks/{id}/logs/`` — paginated execution history of one task."""
        task = self.get_object()
        queryset = (
            TaskExecutionLog.objects.filter(task=task)
            .select_related("task", "triggered_by")
            .order_by("-created_at")
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = serializers.TaskExecutionLogSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        return Response(serializers.TaskExecutionLogSerializer(queryset, many=True).data)


class TaskExecutionLogViewSet(viewsets.ReadOnlyModelViewSet):
    """``/api/scheduled-tasks/logs/`` — read only execution history."""

    queryset = TaskExecutionLog.objects.select_related("task", "triggered_by")
    permission_classes = [IsAuthenticated, ProjectRolePermission]
    pagination_class = StandardResultsSetPagination
    filterset_fields = ("task", "status", "suite_type")
    search_fields = ("scheduled_task_name", "error_message")
    ordering_fields = ("created_at", "started_at", "finished_at", "duration_ms")

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not getattr(user, "is_superuser", False):
            queryset = queryset.filter(task__project__in=projects_for(user))
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(task__project_id=project_id)
        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return serializers.TaskExecutionLogDetailSerializer
        return serializers.TaskExecutionLogSerializer


class CronViewSet(viewsets.ViewSet):
    """``/api/scheduled-tasks/cron/preview/`` — cron helper for the UI."""

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"])
    def preview(self, request):
        """Return ``{valid, description, next_runs}`` for ``?expr=``.

        Invalid expressions are a *normal* preview result (``valid: false`` +
        ``message``) so the form can validate while the user types; the create
        endpoint still rejects them with a ``validation_error`` envelope.
        """
        expression = (
            request.query_params.get("expr")
            or request.query_params.get("expression")
            or ""
        )
        count = request.query_params.get("count") or 5
        timezone_name = request.query_params.get("timezone") or None
        try:
            count_value = int(count)
        except (TypeError, ValueError) as exc:
            raise BusinessError(
                message="count 必须是整数", code="validation_error"
            ) from exc
        payload = cron_service.preview(
            expression, count=count_value, timezone_name=timezone_name
        )
        return Response(serializers.CronPreviewSerializer(payload).data)
