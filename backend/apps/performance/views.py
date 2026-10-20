"""REST API for the 性能测试 module (mounted at ``/api/performance/``).

Endpoints (``docs/ARCHITECTURE.md`` §2.6):

* ``/configs/``            - load configuration CRUD
* ``/scenarios/``          - scenario CRUD, ``/{id}/generate_script/``, ``/{id}/run/``
* ``/executions/``         - list/retrieve, ``/{id}/cancel/``, ``/{id}/report/``
* ``/diagnoses/``          - list/retrieve, PATCH status handling
* ``/dashboard/``          - aggregated metrics for the front-end dashboard
* ``/grafana/webhook/``    - public Grafana alerting receiver
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.api.api_exception_handler import BusinessError
from apps.common.pagination import StandardResultsSetPagination
from apps.common.permissions import ProjectRolePermission, require_project_role
from apps.common.task.utils import submit
from apps.performance.constants import (
    DEFAULT_DASHBOARD_DAYS,
    MAX_DASHBOARD_DAYS,
)
from apps.performance.models import (
    AiDiagnosisRecord,
    LoadConfiguration,
    PerformanceExecution,
    PerformanceScenario,
)
from apps.performance.serializers import (
    AiDiagnosisRecordSerializer,
    LoadConfigurationSerializer,
    ManualDiagnosisSerializer,
    PerformanceExecutionSerializer,
    PerformanceScenarioSerializer,
)
from apps.performance.services import execution as execution_service
from apps.performance.services import diagnosis as diagnosis_service
from apps.performance.services.script_generator import (
    estimate_endpoint_count,
    generate_locust_script,
)
from apps.performance.tasks import execute_scenario_task
from apps.projects.models import Project
from apps.projects.views import ProjectScopedViewSet, projects_for

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _as_int(value, default=0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _round(value, digits=2, default=0.0) -> float:
    if value is None:
        return default
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return default


class BasePerformanceViewSet(ProjectScopedViewSet):
    """Project scoped viewset with the性能测试 role mapping."""

    permission_classes = [IsAuthenticated, ProjectRolePermission]
    pagination_class = StandardResultsSetPagination
    minimum_role_by_action = {"destroy": "admin"}

    def get_permissions(self):
        permission = ProjectRolePermission()
        permission.minimum_role_by_action = self.minimum_role_by_action
        return [IsAuthenticated(), permission]

    def perform_destroy(self, instance):
        project = getattr(instance, "project", None)
        if project is not None:
            require_project_role(self.request.user, project, "admin")
        instance.delete()


class BaseReadOnlyPerformanceViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, ProjectRolePermission]
    pagination_class = StandardResultsSetPagination
    project_field = "project"

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return queryset
        return queryset.filter(**{f"{self.project_field}__in": projects_for(user)})


# ---------------------------------------------------------------------------
# load configurations
# ---------------------------------------------------------------------------
class LoadConfigurationViewSet(BasePerformanceViewSet):
    queryset = LoadConfiguration.objects.select_related("project")
    serializer_class = LoadConfigurationSerializer
    filterset_fields = ("project", "name")
    search_fields = ("name", "description", "host")
    ordering_fields = ("created_at", "updated_at", "users", "duration_seconds")


# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------
class PerformanceScenarioViewSet(BasePerformanceViewSet):
    queryset = PerformanceScenario.objects.select_related(
        "project", "source_suite", "source_case", "config"
    )
    serializer_class = PerformanceScenarioSerializer
    filterset_fields = ("project", "source_type", "is_active", "config")
    search_fields = ("name", "description")
    ordering_fields = ("created_at", "updated_at", "name", "endpoint_count")

    def _refresh_endpoint_count(self, scenario: PerformanceScenario) -> PerformanceScenario:
        if not scenario.endpoint_count:
            count = estimate_endpoint_count(scenario)
            if count:
                scenario.endpoint_count = count
                scenario.save(update_fields=["endpoint_count", "updated_at"])
        return scenario

    def perform_create(self, serializer):
        require_project_role(self.request.user, serializer.validated_data.get("project"), "editor")
        instance = serializer.save()
        self._refresh_endpoint_count(instance)

    def perform_update(self, serializer):
        project = serializer.validated_data.get(
            "project", getattr(serializer.instance, "project", None)
        )
        require_project_role(self.request.user, project, "editor")
        instance = serializer.save()
        self._refresh_endpoint_count(instance)

    @action(detail=True, methods=["post"], url_path="generate_script")
    def generate_script(self, request, pk=None):
        scenario = self.get_object()
        require_project_role(request.user, scenario.project, "editor")
        script = generate_locust_script(scenario)
        count = estimate_endpoint_count(scenario)
        if count and count != scenario.endpoint_count:
            scenario.endpoint_count = count
            scenario.save(update_fields=["endpoint_count", "updated_at"])
        return Response(
            {
                "scenario_id": scenario.id,
                "script": script,
                "endpoint_count": scenario.endpoint_count or count,
            }
        )

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        scenario = self.get_object()
        require_project_role(request.user, scenario.project, "editor")
        config_id = request.data.get("config_id") or request.data.get("config")
        config = None
        if config_id not in (None, ""):
            config = LoadConfiguration.objects.filter(pk=_as_int(config_id)).first()
            if config is None:
                raise BusinessError(
                    message="负载配置不存在", code="config_not_found", status_code=404
                )
            if config.project_id != scenario.project_id:
                raise BusinessError(
                    message="负载配置与场景不属于同一项目", code="project_mismatch", status_code=400
                )
        execution = execution_service.create_execution(
            scenario,
            config=config,
            triggered_by=request.user,
            trigger_type="manual",
        )
        submit(execute_scenario_task, execution.id)
        execution.refresh_from_db()
        return Response(
            {
                "task_id": str(execution.id),
                "status": "pending",
                "execution_id": execution.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


# ---------------------------------------------------------------------------
# executions
# ---------------------------------------------------------------------------
class PerformanceExecutionViewSet(BaseReadOnlyPerformanceViewSet):
    queryset = PerformanceExecution.objects.select_related(
        "project", "scenario", "config"
    )
    serializer_class = PerformanceExecutionSerializer
    filterset_fields = ("project", "scenario", "status", "trigger_type")
    search_fields = ("name", "error_message")
    ordering_fields = ("created_at", "started_at", "duration_ms", "avg_tps", "error_rate")

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        execution = self.get_object()
        require_project_role(request.user, execution.project, "editor")
        if execution.status == "cancelled":
            # Idempotent: cancelling twice is not an error.
            return Response(PerformanceExecutionSerializer(execution).data)
        if execution.status not in ("pending", "running"):
            raise BusinessError(
                message="执行已结束，无法取消", code="execution_finished", status_code=400
            )
        reason = str(request.data.get("reason") or "用户取消执行")[:2000]
        execution.status = "cancelled"
        execution.finished_at = timezone.now()
        execution.error_message = reason
        execution.save(
            update_fields=["status", "finished_at", "error_message", "updated_at"]
        )
        return Response(PerformanceExecutionSerializer(execution).data)

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        execution = self.get_object()
        return Response(execution_service.load_report(execution))


# ---------------------------------------------------------------------------
# AI diagnosis records
# ---------------------------------------------------------------------------
class AiDiagnosisRecordViewSet(BasePerformanceViewSet):
    queryset = AiDiagnosisRecord.objects.select_related("project", "execution")
    serializer_class = AiDiagnosisRecordSerializer
    filterset_fields = ("project", "execution", "source", "status", "severity")
    search_fields = ("alert_name", "diagnosis_content")
    ordering_fields = ("created_at", "updated_at")

    def create(self, request, *args, **kwargs):
        serializer = ManualDiagnosisSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        execution = data.get("execution_obj")
        project = getattr(execution, "project", None)
        if project is None:
            project = Project.objects.filter(pk=_as_int(data.get("project"))).first()
            if project is None:
                raise BusinessError(message="项目不存在", code="not_found", status_code=404)
        require_project_role(request.user, project, "editor")
        alert = {
            "source": "manual",
            "alert_name": data.get("alert_name") or "",
            "severity": data.get("severity") or "",
            "grafana_url": data.get("grafana_url") or "",
            "raw_payload": data.get("raw_payload") or {},
        }
        record = diagnosis_service.diagnose_execution(execution, alert=alert, project=project)
        return Response(
            AiDiagnosisRecordSerializer(record).data, status=status.HTTP_201_CREATED
        )

    def perform_destroy(self, instance):
        project = getattr(instance, "project", None)
        if project is not None:
            require_project_role(self.request.user, project, "admin")
        instance.delete()


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------
class PerformanceDashboardView(APIView):
    """Aggregated metrics for the performance monitoring dashboard."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        days = _as_int(request.query_params.get("days"), DEFAULT_DASHBOARD_DAYS)
        days = max(1, min(days, MAX_DASHBOARD_DAYS))
        now = timezone.now()
        start = now - timedelta(days=days)
        accessible = projects_for(request.user)
        project_id = _as_int(request.query_params.get("project"), 0)
        if project_id:
            accessible = accessible.filter(pk=project_id)

        executions = PerformanceExecution.objects.filter(
            project__in=accessible, created_at__gte=start
        )
        diagnoses = AiDiagnosisRecord.objects.filter(
            project__in=accessible, created_at__gte=start
        )

        summary = {
            "executions": 0,
            "passed": 0,
            "failed": 0,
            "error": 0,
            "cancelled": 0,
            "running": 0,
            "pending": 0,
            "avg_tps": 0.0,
            "avg_p95": 0.0,
            "avg_p99": 0.0,
            "avg_error_rate": 0.0,
            "total_requests": 0,
        }
        status_rows = executions.values("status").annotate(count=Count("id"))
        for row in status_rows:
            summary["executions"] += row["count"]
            if row["status"] in summary:
                summary[row["status"]] = row["count"]
        aggregated = executions.aggregate(
            avg_tps=Avg("avg_tps"),
            avg_p95=Avg("p95_response_time"),
            avg_p99=Avg("p99_response_time"),
            avg_error_rate=Avg("error_rate"),
        )
        summary["avg_tps"] = _round(aggregated.get("avg_tps"))
        summary["avg_p95"] = _round(aggregated.get("avg_p95"))
        summary["avg_p99"] = _round(aggregated.get("avg_p99"))
        summary["avg_error_rate"] = _round(aggregated.get("avg_error_rate"), 4)

        trend_map: dict = {}
        for row in executions.annotate(day=TruncDate("created_at")).values("day").annotate(
            executions=Count("id"),
            avg_tps=Avg("avg_tps"),
            avg_p95=Avg("p95_response_time"),
            avg_error_rate=Avg("error_rate"),
            failed=Count("id", filter=Q(status__in=("failed", "error"))),
        ).order_by("day"):
            day = row["day"]
            if day is None:
                continue
            trend_map[day.isoformat() if hasattr(day, "isoformat") else str(day)] = {
                "executions": row["executions"],
                "passed": 0,
                "failed": row["failed"],
                "avg_tps": _round(row["avg_tps"]),
                "avg_p95": _round(row["avg_p95"]),
                "avg_error_rate": _round(row["avg_error_rate"], 4),
            }
        trend = []
        today = timezone.localdate()
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            key = day.isoformat()
            bucket = trend_map.get(key) or {
                "executions": 0,
                "passed": 0,
                "failed": 0,
                "avg_tps": 0.0,
                "avg_p95": 0.0,
                "avg_error_rate": 0.0,
            }
            bucket["date"] = key
            trend.append(bucket)

        recent = []
        for execution in executions.select_related("scenario").order_by("-created_at")[:5]:
            recent.append(
                {
                    "id": execution.id,
                    "name": execution.name,
                    "status": execution.status,
                    "status_label": execution.get_status_display(),
                    "scenario_id": execution.scenario_id,
                    "scenario_name": getattr(execution.scenario, "name", ""),
                    "trigger_type": execution.trigger_type,
                    "avg_tps": _round(execution.avg_tps),
                    "p95_response_time": execution.p95_response_time,
                    "error_rate": _round(execution.error_rate, 4),
                    "total_requests": execution.total_requests,
                    "created_at": execution.created_at.isoformat()
                    if execution.created_at
                    else None,
                }
            )

        diagnosis_stats = {
            "total": 0,
            "pending": 0,
            "resolved": 0,
            "ignored": 0,
            "by_severity": {},
        }
        for row in diagnoses.values("status").annotate(count=Count("id")):
            diagnosis_stats["total"] += row["count"]
            if row["status"] in diagnosis_stats:
                diagnosis_stats[row["status"]] = row["count"]
        for row in diagnoses.exclude(severity="").values("severity").annotate(
            count=Count("id")
        ):
            diagnosis_stats["by_severity"][row["severity"]] = row["count"]

        return Response(
            {
                "days": days,
                "range": {"start": start.isoformat(), "end": now.isoformat()},
                "summary": summary,
                "trend": trend,
                "recent_executions": recent,
                "diagnosis": diagnosis_stats,
            }
        )


# ---------------------------------------------------------------------------
# Grafana webhook
# ---------------------------------------------------------------------------
class GrafanaWebhookView(APIView):
    """Public Grafana alerting receiver (no JWT - Grafana cannot carry one)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def _check_token(self, request) -> None:
        from django.conf import settings

        configured = str(
            getattr(settings, "GRAFANA_WEBHOOK_TOKEN", "")
            or getattr(settings, "GRAFANA_WEBHOOK_SECRET", "")
            or ""
        ).strip()
        if not configured:
            return
        supplied = (
            request.headers.get("X-Grafana-Token")
            or request.query_params.get("token")
            or (request.data.get("token") if isinstance(request.data, dict) else "")
        )
        if str(supplied or "").strip() != configured:
            raise BusinessError(
                message="Grafana Webhook token 校验失败", code="invalid_token", status_code=403
            )

    def post(self, request):
        self._check_token(request)
        result = diagnosis_service.handle_grafana_webhook(request.data)
        return Response(result, status=status.HTTP_200_OK)

    def get(self, request):
        # Convenience probe for Grafana configuration pages / smoke scripts.
        return Response({"status": "ok", "endpoint": "grafana-webhook"})
