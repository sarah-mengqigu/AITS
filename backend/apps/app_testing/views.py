"""API views for the 移动端 App 测试 module (ARCHITECTURE §2.5).

Routes are mounted by ``aits_backend.urls`` under ``/api/app-testing/``; this
module only registers relative router paths. Two kinds of endpoints live here:

* **业务 CRUD**（modules / applications / cases / suites / runs）— 全部按可访问
  项目过滤，权限：读 ``viewer``、写/执行 ``editor``、删除 ``admin``。
* **Sonic 代理**（devices / element-pages）— 透传 Sonic 的只读信息。未配置
  ``SONIC_BASE_URL`` 时：``GET devices/`` 与 ``GET element-pages/`` 返回**空数组
  ``[]``**（不报错），``GET devices/{udid}/`` 返回 ``{"detail":
  "sonic_not_configured"}``，``POST devices/{udid}/remote/`` 返回
  ``{"detail": "sonic_not_configured"}``（写入类动作由 ``SonicClient`` 抛
  ``BusinessError(code="sonic_not_configured")``，HTTP 400，前端可据此提示）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from django.db.models import Count
from django.http import FileResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.app_testing import serializers
from apps.app_testing.models import (
    TERMINAL_RUN_STATUSES,
    AppTestApplication,
    AppTestCase,
    AppTestModule,
    AppTestRun,
    AppTestSuite,
)
from apps.app_testing.services import execution as execution_service
from apps.app_testing.services import generator as step_generator
from apps.app_testing.services.sonic_client import SonicClient, get_sonic_client
from apps.app_testing.tasks import execute_suite_task
from apps.common.api.api_exception_handler import BusinessError
from apps.common.pagination import StandardResultsSetPagination
from apps.common.permissions import ProjectRolePermission, require_project_role
from apps.common.task.utils import submit
from apps.common.websocket.core import WebSocketMessageService
from apps.projects.models import Project
from apps.projects.views import ProjectScopedViewSet, projects_for

logger = logging.getLogger(__name__)

PROJECT_PARAM = "project"
SONIC_NOT_CONFIGURED = "sonic_not_configured"


# ---------------------------------------------------------------------------
# shared behaviour
# ---------------------------------------------------------------------------
class AppTestingRolePermission(ProjectRolePermission):
    """Read = viewer, write/execute = editor, delete = admin."""

    minimum_role_by_action = {"destroy": "admin"}


class AppTestingViewSet(ProjectScopedViewSet):
    """Shared behaviour for every project scoped app-testing viewset."""

    permission_classes = [IsAuthenticated, AppTestingRolePermission]
    pagination_class = StandardResultsSetPagination
    project_field = PROJECT_PARAM
    filterset_fields: tuple = ()

    def perform_create(self, serializer):
        project = self._resolve_project(serializer)
        if project is not None:
            require_project_role(self.request.user, project, "editor")
        serializer.save()

    def perform_update(self, serializer):
        project = self._resolve_project(serializer)
        if project is not None:
            require_project_role(self.request.user, project, "editor")
        serializer.save()

    def perform_destroy(self, instance):
        project = getattr(instance, "project", None)
        if project is not None:
            require_project_role(self.request.user, project, "admin")
        instance.delete()

    def _resolve_project(self, serializer):
        project = serializer.validated_data.get(self.project_field)
        if project is not None:
            return project
        instance = getattr(serializer, "instance", None)
        if instance is not None:
            return getattr(instance, "project", None)
        return None

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _accessible_project(request, project_id):
        """Resolve ``?project=`` to a project the caller may read."""
        project = Project.objects.filter(pk=project_id).first()
        if project is None:
            raise BusinessError(message="项目不存在", code="not_found", status_code=404)
        require_project_role(request.user, project, "viewer")
        return project

    def _sonic_project_id(self, request):
        project = self._optional_project(request)
        if project is not None:
            return project.sonic_project_id or str(project.id), project
        return "", None

    def _optional_project(self, request):
        project_id = (
            request.query_params.get(PROJECT_PARAM)
            or request.data.get(PROJECT_PARAM)
            or request.data.get("project_id")
        )
        if not project_id:
            return None
        return self._accessible_project(request, project_id)


# ---------------------------------------------------------------------------
# modules
# ---------------------------------------------------------------------------
def _tree_payload(modules) -> list[dict]:
    nodes: dict[int, dict] = {}
    for module in modules:
        case_count = getattr(module, "annotated_case_count", None)
        nodes[module.id] = {
            "id": module.id,
            "project": module.project_id,
            "parent": module.parent_id,
            "name": module.name,
            "description": module.description,
            "order": module.order,
            "case_count": case_count if case_count is not None else module.case_count,
            "children": [],
        }
    roots: list[dict] = []
    for module in modules:
        node = nodes[module.id]
        parent = nodes.get(module.parent_id)
        if parent is not None:
            parent["children"].append(node)
        else:
            roots.append(node)
    return roots


class AppTestModuleViewSet(AppTestingViewSet):
    queryset = AppTestModule.objects.select_related("project", "parent")
    serializer_class = serializers.AppTestModuleSerializer
    filterset_fields = ("project", "parent")
    search_fields = ("name", "description")
    ordering_fields = ("order", "created_at", "name")

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """``GET /api/app-testing/modules/tree/?project=<id>`` -> nested tree."""
        queryset = self.get_queryset().annotate(annotated_case_count=Count("cases"))
        project_id = request.query_params.get(PROJECT_PARAM)
        if project_id:
            project = self._accessible_project(request, project_id)
            queryset = queryset.filter(project=project)
        modules = list(queryset.order_by("order", "id"))
        return Response(_tree_payload(modules))


# ---------------------------------------------------------------------------
# applications
# ---------------------------------------------------------------------------
class AppTestApplicationViewSet(AppTestingViewSet):
    queryset = AppTestApplication.objects.select_related("project")
    serializer_class = serializers.AppTestApplicationSerializer
    filterset_fields = ("project", "platform")
    search_fields = ("name", "package_name", "bundle_id", "description")
    ordering_fields = ("created_at", "name")


# ---------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------
class AppTestCaseViewSet(AppTestingViewSet):
    queryset = AppTestCase.objects.select_related("project", "module", "application")
    serializer_class = serializers.AppTestCaseSerializer
    filterset_fields = ("project", "module", "application", "source", "priority",
                        "is_active")
    search_fields = ("name", "description")
    ordering_fields = ("created_at", "priority", "name")

    @action(detail=True, methods=["post"], url_path="generate_steps")
    def generate_steps(self, request, pk=None):
        """``requirement`` -> 结构化 steps + sonic_steps（AI 优先，规则降级）。"""
        test_case = self.get_object()
        require_project_role(request.user, test_case.project, "editor")
        requirement = (
            request.data.get("requirement")
            or request.data.get("natural_language")
            or request.data.get("prompt")
            or request.data.get("text")
            or ""
        )
        requirement = str(requirement).strip()
        if not requirement:
            raise BusinessError(message="缺少 requirement 参数", code="missing_requirement")
        platform = (
            request.data.get("platform")
            or getattr(test_case.application, "platform", "")
            or "android"
        )
        generated = step_generator.generate_steps(
            requirement, project=test_case.project, platform=platform
        )
        test_case.steps = generated["steps"]
        test_case.sonic_steps = generated["sonic_steps"]
        test_case.source = "ai"
        test_case.save(update_fields=["steps", "sonic_steps", "source", "updated_at"])
        return Response(
            {
                "case": test_case.id,
                "steps": test_case.steps,
                "sonic_steps": test_case.sonic_steps,
                "generated_by": generated["generated_by"],
                "requirement": requirement,
                "applied": True,
            }
        )


# ---------------------------------------------------------------------------
# suites
# ---------------------------------------------------------------------------
DEVICE_FIELDS = ("udid", "device_udid", "device_id", "deviceId", "device_name",
                 "deviceName", "platform", "sonic_suite_id", "suiteId")


def _merge_device_config(request) -> dict:
    """Collect device overrides from the run request body."""
    config = {}
    payload = request.data.get("device_config")
    if isinstance(payload, dict):
        config.update(payload)
    for key in DEVICE_FIELDS:
        value = request.data.get(key)
        if value not in (None, ""):
            config[key] = value
    return config


class AppTestSuiteViewSet(AppTestingViewSet):
    queryset = AppTestSuite.objects.select_related("project", "application")
    serializer_class = serializers.AppTestSuiteSerializer
    filterset_fields = ("project", "application", "is_active")
    search_fields = ("name", "description")
    ordering_fields = ("created_at", "name")

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        """Run a suite -> 202 ``{"task_id", "status", "run_id"}`` (progress via WS)."""
        suite = self.get_object()
        require_project_role(request.user, suite.project, "editor")
        if not suite.is_active:
            raise BusinessError(message="套件已禁用，无法执行", code="suite_inactive")
        run = execution_service.create_suite_run(
            suite,
            triggered_by=request.user,
            trigger_type="manual",
            environment_id=request.data.get("environment")
            or request.data.get("environment_id"),
            device_config=_merge_device_config(request),
        )
        task_result = submit(execute_suite_task, run.id)
        run.refresh_from_db()
        return Response(
            {
                "task_id": str(run.id),
                "status": "pending",
                "run_id": run.id,
                "run_status": run.status,
                "celery_task_id": str(getattr(task_result, "id", "") or ""),
            },
            status=status.HTTP_202_ACCEPTED,
        )


# ---------------------------------------------------------------------------
# runs
# ---------------------------------------------------------------------------
class AppTestRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AppTestRun.objects.select_related("project", "suite")
    serializer_class = serializers.AppTestRunSerializer
    permission_classes = [IsAuthenticated, AppTestingRolePermission]
    pagination_class = StandardResultsSetPagination
    filterset_fields = ("project", "status", "trigger_type", "suite")
    search_fields = ("name", "device_name", "device_udid")
    ordering_fields = ("created_at", "started_at", "duration_ms")

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return queryset
        return queryset.filter(project__in=projects_for(user))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        run = self.get_object()
        require_project_role(request.user, run.project, "editor")
        if run.status in TERMINAL_RUN_STATUSES:
            raise BusinessError(
                message=f"执行已结束（{run.status}），无法取消",
                code="invalid_status",
                status_code=status.HTTP_409_CONFLICT,
            )
        run.status = "cancelled"
        run.finished_at = timezone.now()
        if run.started_at:
            run.duration_ms = max(
                int((run.finished_at - run.started_at).total_seconds() * 1000), 1
            )
        run.summary = {
            **(run.summary or {}),
            "cancelled_by": request.user.id,
            "cancelled_at": run.finished_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        run.save()
        try:
            WebSocketMessageService.push_task_status(
                run.id, status="cancelled", progress=100, message="执行已取消"
            )
        except Exception:  # pragma: no cover - ws push is best effort
            logger.debug("ws push failed", exc_info=True)
        return Response(serializers.AppTestRunSerializer(run).data)

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        """Report metadata + parsed JSON payload; ``?download=1`` returns the file."""
        run = self.get_object()
        summary = run.summary or {}
        wants_download = str(request.query_params.get("download", "")).lower() in (
            "1", "true", "yes", "on",
        )
        if wants_download:
            if not run.report_path:
                raise BusinessError(message="报告文件不存在", code="not_found",
                                    status_code=404)
            path = Path(run.report_path)
            if path.is_file():
                return FileResponse(
                    open(path, "rb"), content_type="application/json",
                    as_attachment=True, filename=f"app-testing-report-{run.id}.json",
                )
            raise BusinessError(message="报告文件不存在", code="not_found", status_code=404)
        report_payload = None
        path = Path(run.report_path) if run.report_path else None
        if path is not None and path.is_file():
            try:
                report_payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                logger.warning("report json unreadable: %s", run.report_path)
        return Response(
            {
                "run_id": run.id,
                "name": run.name,
                "status": run.status,
                "suite": run.suite_id,
                "device": {
                    "udid": run.device_udid,
                    "device_id": run.device_id,
                    "device_name": run.device_name,
                    "platform": run.platform,
                },
                "total": run.total,
                "passed": run.passed,
                "failed": run.failed,
                "skipped": run.skipped,
                "pass_rate": run.pass_rate,
                "duration_ms": run.duration_ms,
                "summary": summary,
                "report_path": run.report_path,
                "report_url": summary.get("report_url", ""),
                "report_available": bool(report_payload),
                "report": report_payload,
            }
        )


# ---------------------------------------------------------------------------
# Sonic proxy: devices / element-pages
# ---------------------------------------------------------------------------
class SonicDeviceViewSet(viewsets.ViewSet):
    """Sonic 在线设备代理（未配置 Sonic → 空数组，见模块 docstring）。"""

    permission_classes = [IsAuthenticated]

    def _project_and_sonic_id(self, request):
        project_id = request.query_params.get(PROJECT_PARAM) or request.data.get(
            PROJECT_PARAM
        )
        if not project_id:
            return None, ""
        project = Project.objects.filter(pk=project_id).first()
        if project is None:
            raise BusinessError(message="项目不存在", code="not_found", status_code=404)
        require_project_role(request.user, project, "viewer")
        return project, project.sonic_project_id or str(project.id)

    def list(self, request):
        """``GET /api/app-testing/devices/`` -> ``[...]``（未配置 Sonic 返回 ``[]``）。"""
        project, sonic_project_id = self._project_and_sonic_id(request)
        client = get_sonic_client(project)
        if not client.configured:
            return Response([])
        return Response(client.list_devices(project_id=sonic_project_id or None))

    def retrieve(self, request, pk=None):
        """``GET /api/app-testing/devices/{udid}/``."""
        project, _ = self._project_and_sonic_id(request)
        client = get_sonic_client(project)
        if not client.configured:
            return Response(
                {
                    "udid": pk,
                    "configured": False,
                    "detail": SONIC_NOT_CONFIGURED,
                    "device": {},
                }
            )
        device = client.get_device(pk)
        if not device:
            raise BusinessError(
                message="设备不存在或已离线", code="not_found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return Response({"udid": pk, "configured": True, "device": device})

    @action(detail=True, methods=["post"])
    def remote(self, request, pk=None):
        """``POST /api/app-testing/devices/{udid}/remote/`` -> 远控 ws 信息。"""
        project, _ = self._project_and_sonic_id(request)
        if project is not None:
            require_project_role(request.user, project, "editor")
        client = get_sonic_client(project)
        if not client.configured:
            return Response(
                {
                    "udid": pk,
                    "configured": False,
                    "detail": SONIC_NOT_CONFIGURED,
                    "ws_url": "",
                    "jmuxer": {},
                }
            )
        info = client.device_remote_info(pk)
        if not info or not info.get("ws_url"):
            raise BusinessError(
                message="获取远控信息失败，请确认设备在线",
                code="sonic_remote_unavailable",
                status_code=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"configured": True, **info})


class SonicElementPageViewSet(viewsets.ViewSet):
    """Sonic ElementPages 代理（未配置 Sonic → 空数组）。"""

    permission_classes = [IsAuthenticated]

    def list(self, request):
        """``GET /api/app-testing/element-pages/?project=<id>``."""
        project_id = request.query_params.get(PROJECT_PARAM)
        project = None
        sonic_project_id = ""
        if project_id:
            project = Project.objects.filter(pk=project_id).first()
            if project is None:
                raise BusinessError(message="项目不存在", code="not_found", status_code=404)
            require_project_role(request.user, project, "viewer")
            sonic_project_id = project.sonic_project_id or str(project.id)
        client = get_sonic_client(project)
        if not client.configured:
            return Response([])
        return Response(client.list_element_pages(project_id=sonic_project_id or None))


#: re-exported for convenience in tests / other modules
__all__ = [
    "AppTestApplicationViewSet",
    "AppTestCaseViewSet",
    "AppTestModuleViewSet",
    "AppTestRunViewSet",
    "AppTestSuiteViewSet",
    "SonicClient",
    "SonicDeviceViewSet",
    "SonicElementPageViewSet",
]
