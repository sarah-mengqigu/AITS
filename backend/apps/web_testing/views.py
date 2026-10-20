"""API views for the Web UI 测试 module (ARCHITECTURE §2.4).

Routes are mounted by ``aits_backend.urls`` under ``/api/web-testing/``; this
module only registers relative router paths.

Permission policy (§1.4): read = viewer, write/execute = editor, delete = admin.
Every queryset is scoped to the projects the caller can access.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from django.db.models import Count
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.api.api_exception_handler import BusinessError
from apps.common.pagination import StandardResultsSetPagination
from apps.common.permissions import ProjectRolePermission, require_project_role
from apps.common.task.utils import submit
from apps.common.websocket.core import WebSocketMessageService
from apps.projects.models import Project
from apps.projects.views import ProjectScopedViewSet, projects_for
from apps.web_testing import serializers
from apps.web_testing.models import (
    TERMINAL_EXECUTION_STATUSES,
    MidSceneScript,
    WebElement,
    WebPage,
    WebUITestCase,
    WebUITestExecution,
    WebUITestModule,
    WebUITestSuite,
)
from apps.web_testing.services import execution as execution_service
from apps.web_testing.services import generator as case_generator
from apps.web_testing.services import script_builder
from apps.web_testing.tasks import execute_case_task, execute_suite_task

logger = logging.getLogger(__name__)

PAGE_PARAM = "project"


class WebTestingRolePermission(ProjectRolePermission):
    """Write needs editor, delete needs admin, read needs viewer."""

    minimum_role_by_action = {"destroy": "admin"}


class WebTestingViewSet(ProjectScopedViewSet):
    """Shared behaviour for all web-testing viewsets."""

    permission_classes = [IsAuthenticated, WebTestingRolePermission]
    pagination_class = StandardResultsSetPagination
    project_field = PAGE_PARAM
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
        if project is None and hasattr(instance, "page"):
            project = instance.page.project
        if project is not None:
            require_project_role(self.request.user, project, "admin")
        instance.delete()

    def _resolve_project(self, serializer):
        project = serializer.validated_data.get(self.project_field)
        if project is not None:
            return project
        instance = getattr(serializer, "instance", None)
        if instance is not None:
            project = getattr(instance, "project", None)
            if project is None and hasattr(instance, "page"):
                project = instance.page.project
            return project
        # Element creation passes ``page`` instead of ``project``.
        page = serializer.validated_data.get("page")
        if page is not None:
            return page.project
        return None


# ---------------------------------------------------------------------------
# modules
# ---------------------------------------------------------------------------
def _tree_payload(modules) -> list[dict]:
    nodes: dict[int, dict] = {}
    for module in modules:
        nodes[module.id] = {
            "id": module.id,
            "project": module.project_id,
            "parent": module.parent_id,
            "name": module.name,
            "description": module.description,
            "order": module.order,
            "case_count": (
                getattr(module, "annotated_case_count", None)
                if getattr(module, "annotated_case_count", None) is not None
                else module.case_count
            ),
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


class WebUITestModuleViewSet(WebTestingViewSet):
    queryset = WebUITestModule.objects.select_related("project", "parent")
    serializer_class = serializers.WebUITestModuleSerializer
    filterset_fields = ("project", "parent")
    search_fields = ("name", "description")
    ordering_fields = ("order", "created_at", "name")

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """``GET /api/web-testing/modules/tree/?project=<id>`` -> nested tree."""
        queryset = self.get_queryset().annotate(annotated_case_count=Count("cases"))
        project_id = request.query_params.get(PAGE_PARAM)
        if project_id:
            project = Project.objects.filter(pk=project_id).first()
            if project is None:
                raise BusinessError(message="项目不存在", code="not_found", status_code=404)
            require_project_role(request.user, project, "viewer")
            queryset = queryset.filter(project=project)
        modules = list(queryset.order_by("order", "id"))
        return Response(_tree_payload(modules))


# ---------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------
class WebUITestCaseViewSet(WebTestingViewSet):
    queryset = WebUITestCase.objects.select_related("project", "module")
    serializer_class = serializers.WebUITestCaseSerializer
    filterset_fields = ("project", "module", "case_type", "script_type", "priority",
                        "source", "is_active")
    search_fields = ("name", "description")
    ordering_fields = ("created_at", "priority", "name")

    @action(detail=True, methods=["post"], url_path="generate_script")
    def generate_script(self, request, pk=None):
        """Generate a Playwright / MidScene script (AI first, template fallback)."""
        test_case = self.get_object()
        require_project_role(request.user, test_case.project, "editor")
        script_type = str(
            request.data.get("script_type") or test_case.script_type or "playwright"
        ).lower()
        if script_type not in script_builder.SUPPORTED_SCRIPT_TYPES:
            raise BusinessError(
                message=f"script_type 仅支持 {list(script_builder.SUPPORTED_SCRIPT_TYPES)}",
                code="invalid_script_type",
            )
        script_text, source = script_builder.build_script(test_case, script_type=script_type)
        test_case.script = script_text
        test_case.script_type = script_type
        test_case.save(update_fields=["script", "script_type", "updated_at"])
        return Response(
            {
                "case": test_case.id,
                "script_type": script_type,
                "generated_by": source,
                "script": script_text,
                "length": len(script_text),
            }
        )

    @action(detail=True, methods=["post"], url_path="generate_from_nl")
    def generate_from_nl(self, request, pk=None):
        """Natural language -> structured steps (rule fallback when no ai_core)."""
        test_case = self.get_object()
        require_project_role(request.user, test_case.project, "editor")
        natural_language = (
            request.data.get("natural_language")
            or request.data.get("prompt")
            or request.data.get("text")
            or ""
        )
        generated = case_generator.generate_case_from_nl(
            natural_language,
            test_case.project,
            name=request.data.get("name") or "",
            module=test_case.module,
            script_type=test_case.script_type,
            save=False,
        )
        apply_steps = request.data.get("apply", True)
        if apply_steps and generated["steps"]:
            test_case.steps = generated["steps"]
            test_case.save(update_fields=["steps", "updated_at"])
        return Response(
            {
                "case": test_case.id,
                "name": generated["name"],
                "steps": generated["steps"],
                "generated_by": generated["generated_by"],
                "applied": bool(apply_steps and generated["steps"]),
            }
        )

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        """Run a single case -> 202 ``{task_id, status, execution_id}``."""
        test_case = self.get_object()
        require_project_role(request.user, test_case.project, "editor")
        execution = execution_service.create_case_execution(
            test_case, triggered_by=request.user, trigger_type="manual"
        )
        task_result = submit(execute_case_task, execution.id, test_case.id)
        execution.refresh_from_db()
        return Response(
            {
                "task_id": str(execution.id),
                "status": "pending",
                "execution_id": execution.id,
                "execution_status": execution.status,
                "celery_task_id": str(getattr(task_result, "id", "") or ""),
            },
            status=status.HTTP_202_ACCEPTED,
        )


# ---------------------------------------------------------------------------
# suites
# ---------------------------------------------------------------------------
class WebUITestSuiteViewSet(WebTestingViewSet):
    queryset = WebUITestSuite.objects.select_related("project", "environment")
    serializer_class = serializers.WebUITestSuiteSerializer
    filterset_fields = ("project", "browser", "is_active", "environment")
    search_fields = ("name", "description")
    ordering_fields = ("created_at", "name")

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        """Run a suite -> 202 ``{task_id, status}``; progress flows over WS."""
        suite = self.get_object()
        require_project_role(request.user, suite.project, "editor")
        environment_id = request.data.get("environment") or request.data.get(
            "environment_id"
        )
        execution = execution_service.create_suite_execution(
            suite, triggered_by=request.user, trigger_type="manual",
            environment_id=environment_id,
        )
        task_result = submit(execute_suite_task, execution.id)
        execution.refresh_from_db()
        return Response(
            {
                "task_id": str(execution.id),
                "status": "pending",
                "execution_id": execution.id,
                "execution_status": execution.status,
                "celery_task_id": str(getattr(task_result, "id", "") or ""),
            },
            status=status.HTTP_202_ACCEPTED,
        )


# ---------------------------------------------------------------------------
# executions
# ---------------------------------------------------------------------------
class WebUITestExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WebUITestExecution.objects.select_related(
        "project", "suite", "triggered_by"
    )
    permission_classes = [IsAuthenticated, WebTestingRolePermission]
    pagination_class = StandardResultsSetPagination
    filterset_fields = ("project", "status", "trigger_type", "suite")
    ordering_fields = ("created_at", "started_at", "duration_ms")

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return queryset
        return queryset.filter(project__in=projects_for(user))

    def get_serializer_class(self):
        if self.action == "retrieve":
            return serializers.WebUITestExecutionDetailSerializer
        return serializers.WebUITestExecutionSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.prefetched_details = list(
            instance.details.select_related("test_case").all()
        )
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        execution = self.get_object()
        require_project_role(request.user, execution.project, "editor")
        if execution.status in TERMINAL_EXECUTION_STATUSES:
            raise BusinessError(
                message=f"执行已结束（{execution.status}），无法取消",
                code="invalid_status",
                status_code=status.HTTP_409_CONFLICT,
            )
        execution.status = "cancelled"
        execution.finished_at = timezone.now()
        if execution.started_at:
            execution.duration_ms = max(
                int((execution.finished_at - execution.started_at).total_seconds() * 1000), 1
            )
        execution.summary = {
            **(execution.summary or {}),
            "cancelled_by": request.user.id,
            "cancelled_at": execution.finished_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        execution.save()
        try:
            WebSocketMessageService.push_task_status(
                execution.id, status="cancelled", progress=100, message="执行已取消"
            )
        except Exception:  # pragma: no cover - ws is best effort
            logger.debug("ws push failed", exc_info=True)
        return Response(serializers.WebUITestExecutionSerializer(execution).data)

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        """Return report metadata + parsed JSON payload; ``?download=1`` = HTML."""
        execution = self.get_object()
        summary = execution.summary or {}
        wants_download = str(request.query_params.get("download", "")).lower() in (
            "1", "true", "yes", "on",
        )
        if wants_download and execution.report_path:
            path = Path(execution.report_path)
            if path.exists():
                from django.http import FileResponse

                return FileResponse(
                    open(path, "rb"), content_type="text/html",
                    as_attachment=True, filename=f"web-testing-report-{execution.id}.html",
                )
            raise BusinessError(message="报告文件不存在", code="not_found", status_code=404)
        report_payload = None
        json_path = summary.get("report_json") or ""
        if json_path:
            path = Path(json_path)
            if path.exists():
                try:
                    report_payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    logger.warning("report json unreadable: %s", json_path)
        html_path = execution.report_path or ""
        return Response(
            {
                "execution_id": execution.id,
                "name": execution.name,
                "status": execution.status,
                "summary": summary,
                "report_path": html_path,
                "report_url": summary.get("report_url", ""),
                "report_available": bool(html_path and Path(html_path).exists()),
                "allure_results_path": execution.allure_results_path,
                "report": report_payload,
                "details": serializers.WebUITestCaseExecutionDetailSerializer(
                    execution.details.all(), many=True
                ).data,
            }
        )


# ---------------------------------------------------------------------------
# POM: pages / elements
# ---------------------------------------------------------------------------
class WebPageViewSet(WebTestingViewSet):
    queryset = WebPage.objects.select_related("project")
    serializer_class = serializers.WebPageSerializer
    filterset_fields = ("project",)
    search_fields = ("name", "url", "description")
    ordering_fields = ("created_at", "name")

    @action(detail=True, methods=["get"])
    def elements(self, request, pk=None):
        """``GET /api/web-testing/pages/{id}/elements/``."""
        page = self.get_object()
        elements = page.elements.all()
        return Response(serializers.WebElementSerializer(elements, many=True).data)


class WebElementViewSet(WebTestingViewSet):
    queryset = WebElement.objects.select_related("page", "page__project")
    serializer_class = serializers.WebElementSerializer
    project_field = "page__project"
    # NOTE: ``page`` is reserved by DRF pagination, so the POM page filter is
    # exposed as ``?page_id=<WebPage id>`` (``?page=`` still paginates).
    filterset_fields = ("locator_type",)
    search_fields = ("name", "locator_value", "description")
    ordering_fields = ("created_at", "name")

    def get_queryset(self):
        queryset = super().get_queryset()
        page_id = self.request.query_params.get("page_id")
        if page_id not in (None, ""):
            queryset = queryset.filter(page_id=page_id)
        return queryset

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        """Upsert many POM elements of one page.

        Body: ``{"page": 1, "elements": [{name, locator_type, locator_value,
        alternatives, description}, ...]}``
        """
        payload = request.data
        if isinstance(payload, list):
            page_id = None
            for item in payload:
                if isinstance(item, dict) and item.get("page"):
                    page_id = item["page"]
                    break
            payload = {"page": page_id, "elements": payload}
        serializer = serializers.WebElementBulkSerializer(
            data=payload, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        page = serializer.page_instance
        if page is None:
            raise BusinessError(message="缺少 page 参数", code="missing_page")
        require_project_role(request.user, page.project, "editor")

        created = updated = 0
        elements = []
        for item in serializer.validated_data["elements"]:
            data = {key: value for key, value in item.items() if key != "page"}
            name = data.pop("name")
            element, is_created = WebElement.objects.update_or_create(
                page=page, name=name, defaults=data
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
            elements.append(element)
        return Response(
            {
                "page": page.id,
                "created": created,
                "updated": updated,
                "total": len(elements),
                "elements": serializers.WebElementSerializer(elements, many=True).data,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# MidScene scripts
# ---------------------------------------------------------------------------
class MidSceneScriptViewSet(WebTestingViewSet):
    queryset = MidSceneScript.objects.select_related("project", "case")
    serializer_class = serializers.MidSceneScriptSerializer
    filterset_fields = ("project", "script_type", "status", "case")
    search_fields = ("name", "description", "content")
    ordering_fields = ("created_at", "name")

    @action(detail=True, methods=["post"])
    def generate(self, request, pk=None):
        """Generate the MidScene content from the linked case (or raw steps)."""
        script = self.get_object()
        require_project_role(request.user, script.project, "editor")
        test_case = script.case
        case_id = request.data.get("case") or request.data.get("case_id")
        if test_case is None and case_id:
            test_case = WebUITestCase.objects.filter(
                pk=case_id, project_id=script.project_id
            ).first()
        if test_case is None:
            raise BusinessError(
                message="MidScene 脚本未关联用例，无法生成",
                code="missing_case",
            )
        script_type = str(
            request.data.get("script_type") or script.script_type or "yaml"
        ).lower()
        if script_type == "python":
            content = script_builder.generate_midscene_python_script(test_case)
        else:
            content = script_builder.generate_midscene_script(test_case)
            script_type = "yaml"
        script.content = content
        script.script_type = script_type
        script.case = test_case
        script.status = "generated"
        script.save(update_fields=["content", "script_type", "case", "status", "updated_at"])
        return Response(serializers.MidSceneScriptSerializer(script).data)
