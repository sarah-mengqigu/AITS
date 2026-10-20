"""REST API for the API 测试 module (mounted at ``/api/api-testing/``)."""

from __future__ import annotations

import json
import logging

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api_testing.models import (
    APIEndpoint,
    APIModule,
    APISpecification,
    APITestCase,
    APITestExecution,
    APITestSuite,
)
from apps.api_testing.serializers import (
    APIEndpointSerializer,
    APIModuleSerializer,
    APISpecificationDetailSerializer,
    APISpecificationSerializer,
    APITestCaseSerializer,
    APITestExecutionDetailSerializer,
    APITestExecutionSerializer,
    APITestSuiteSerializer,
)
from apps.api_testing.services import execution as execution_service
from apps.api_testing.services.generator import generate_endpoint_cases, generate_scenario
from apps.api_testing.services.importer import (
    import_openapi,
    import_postman_collection,
    reparse_spec,
)
from apps.api_testing.services.script_builder import build_httprunner_yaml
from apps.api_testing.tasks import execute_case_task, execute_suite_task
from apps.common.api.api_exception_handler import BusinessError
from apps.common.pagination import StandardResultsSetPagination
from apps.common.permissions import (
    ProjectRolePermission,
    get_user_role,
    require_project_role,
)
from apps.common.storage.file_storage import save_uploaded_file
from apps.common.task.utils import submit
from apps.projects.models import Project, UploadedFile
from apps.projects.views import ProjectScopedViewSet, projects_for

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _project_from_request(request, key: str = "project") -> Project:
    raw = request.data.get(key) if hasattr(request, "data") else None
    if raw in (None, ""):
        raw = request.query_params.get(key)
    if raw in (None, ""):
        raise BusinessError(message="缺少 project 参数", code="missing_project")
    project = Project.objects.filter(pk=raw).first()
    if project is None:
        raise BusinessError(message="项目不存在", code="not_found", status_code=404)
    return project


def _read_upload(upload) -> str:
    try:
        upload.seek(0)
        raw = upload.read()
    except (OSError, AttributeError) as exc:  # pragma: no cover - defensive
        raise BusinessError(message=f"读取上传文件失败: {exc}", code="invalid_file") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BusinessError(message="文件编码必须是 UTF-8", code="invalid_file") from exc
    if not text.strip():
        raise BusinessError(message="文件内容为空", code="empty_file")
    return text


def _store_upload(project, upload, purpose: str, user):
    """Persist an uploaded file and create the projects.UploadedFile row."""
    if upload is None:
        return None
    try:
        stored_path, sha, size = save_uploaded_file(
            upload, subdir=f"api_testing/{project.id}"
        )
        uploaded, _ = UploadedFile.objects.get_or_create(
            sha256=sha,
            project=project,
            defaults={
                "original_name": upload.name,
                "stored_path": stored_path,
                "size": size,
                "content_type": getattr(upload, "content_type", "") or "",
                "purpose": purpose,
                "uploaded_by": user if getattr(user, "pk", None) else None,
            },
        )
        return uploaded
    except BusinessError:
        raise
    except Exception as exc:  # storage is auxiliary - never block the import
        logger.warning("failed to store uploaded spec file: %s", exc)
        return None


def _as_bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_or_none(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise BusinessError(message="environment 参数必须是整数", code="invalid_environment")


def _load_collection(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise BusinessError(message="Collection 内容为空", code="empty_collection")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            try:
                import yaml

                parsed = yaml.safe_load(text)
            except Exception as exc:  # noqa: BLE001
                raise BusinessError(
                    message=f"Collection 解析失败: {exc}", code="invalid_collection"
                ) from exc
        if not isinstance(parsed, dict):
            raise BusinessError(message="Collection 必须是 JSON 对象", code="invalid_collection")
        return parsed
    raise BusinessError(message="请提供 Postman Collection 文件或内容", code="missing_file")


# ---------------------------------------------------------------------------
# base viewset
# ---------------------------------------------------------------------------
class BaseProjectViewSet(ProjectScopedViewSet):
    """Project scoped viewset with the API 测试 role mapping."""

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


class BaseReadOnlyProjectViewSet(viewsets.ReadOnlyModelViewSet):
    """Read only project scoped viewset for execution history."""

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
# specifications
# ---------------------------------------------------------------------------
class APISpecificationViewSet(BaseProjectViewSet):
    queryset = APISpecification.objects.select_related("project", "file")
    serializer_class = APISpecificationSerializer
    filterset_fields = ("project", "source_type", "status")
    search_fields = ("name", "base_url")

    def get_serializer_class(self):
        if self.action in ("retrieve", "import_spec", "reparse"):
            return APISpecificationDetailSerializer
        return APISpecificationSerializer

    @action(
        detail=False,
        methods=["post"],
        url_path="import",
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def import_spec(self, request):
        project = _project_from_request(request)
        require_project_role(request.user, project, "editor")

        upload = request.FILES.get("file")
        content = request.data.get("content")
        fmt = str(request.data.get("format") or "").lower()
        base_url = str(request.data.get("base_url") or "")
        name = request.data.get("name") or None

        uploaded_file = _store_upload(project, upload, "api_spec", request.user)
        if upload is not None:
            content = _read_upload(upload)
        if content in (None, ""):
            raise BusinessError(
                message="请提供 file 文件或 content 规范内容", code="missing_content"
            )
        if not isinstance(content, (str, bytes, dict)):
            raise BusinessError(message="content 必须是文本", code="invalid_spec")

        try:
            if fmt == "postman":
                if isinstance(content, str):
                    content = _load_collection(content)
                result = import_postman_collection(
                    project, content, name=name, base_url=base_url,
                    uploaded_file=uploaded_file, created_by=request.user,
                )
                payload = {
                    "spec": APISpecificationDetailSerializer(result["spec"]).data,
                    "endpoint_count": result["endpoint_count"],
                    "created": result["created"],
                    "updated": result["updated"],
                    "case_count": result["case_count"],
                    "cases": APITestCaseSerializer(result["cases"], many=True).data,
                }
                return Response(payload, status=status.HTTP_201_CREATED)
            result = import_openapi(
                project, content, name=name, base_url=base_url,
                uploaded_file=uploaded_file, created_by=request.user,
            )
        except BusinessError:
            raise
        except Exception as exc:  # noqa: BLE001 - parse errors must be 4xx, not 500
            logger.exception("spec import failed")
            raise BusinessError(
                message=f"规范导入失败: {exc}", code="invalid_spec"
            ) from exc

        return Response(
            {
                "spec": APISpecificationDetailSerializer(result["spec"]).data,
                "endpoint_count": result["endpoint_count"],
                "created": result["created"],
                "updated": result["updated"],
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def reparse(self, request, pk=None):
        spec = self.get_object()
        require_project_role(request.user, spec.project, "editor")
        try:
            result = reparse_spec(spec)
        except BusinessError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("spec reparse failed")
            raise BusinessError(message=f"重新解析失败: {exc}", code="invalid_spec") from exc
        return Response(
            {
                "spec": APISpecificationDetailSerializer(result["spec"]).data,
                "endpoint_count": result["endpoint_count"],
                "created": result["created"],
                "updated": result["updated"],
            }
        )


# ---------------------------------------------------------------------------
# modules
# ---------------------------------------------------------------------------
class APIModuleViewSet(BaseProjectViewSet):
    queryset = APIModule.objects.select_related("project", "spec", "parent")
    serializer_class = APIModuleSerializer
    filterset_fields = ("project", "spec", "parent")
    search_fields = ("name", "description")

    @action(detail=False, methods=["get"])
    def tree(self, request):
        queryset = self.get_queryset()
        project_id = request.query_params.get("project")
        if project_id:
            project = Project.objects.filter(pk=project_id).first()
            if project is None:
                raise BusinessError(message="项目不存在", code="not_found", status_code=404)
            if get_user_role(request.user, project) is None:
                raise BusinessError(
                    message="无权访问该项目", code="permission_denied", status_code=403
                )
            queryset = queryset.filter(project=project)
        spec_id = request.query_params.get("spec")
        if spec_id:
            queryset = queryset.filter(spec_id=spec_id)

        modules = list(queryset.order_by("order", "id"))
        nodes: dict[int, dict] = {}
        for module in modules:
            data = APIModuleSerializer(module).data
            data["children"] = []
            nodes[module.id] = data
        roots: list[dict] = []
        for module in modules:
            node = nodes[module.id]
            parent_id = module.parent_id
            if parent_id and parent_id in nodes:
                nodes[parent_id]["children"].append(node)
            else:
                roots.append(node)
        return Response({"count": len(modules), "tree": roots, "results": roots})


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------
class APIEndpointViewSet(BaseProjectViewSet):
    queryset = APIEndpoint.objects.select_related("project", "spec", "module")
    serializer_class = APIEndpointSerializer
    filterset_fields = ("project", "spec", "module", "is_active")
    search_fields = ("path", "summary", "operation_id", "description")
    ordering_fields = ("path", "method", "created_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        method = self.request.query_params.get("method")
        if method:
            # Accept both ``?method=GET`` and ``?method=get``.
            queryset = queryset.filter(method=str(method).lower())
        return queryset

    @action(detail=True, methods=["get", "post"], url_path="generate_cases")
    def generate_cases(self, request, pk=None):
        endpoint = self.get_object()
        use_ai = _as_bool(
            request.data.get("use_ai")
            if hasattr(request, "data")
            else None,
            default=False,
        ) or _as_bool(request.query_params.get("use_ai"), default=False)
        if request.method == "POST":
            require_project_role(request.user, endpoint.project, "editor")
            generated = generate_endpoint_cases(endpoint, use_ai=use_ai)
            created = [
                APITestCase.objects.create(
                    project=endpoint.project,
                    endpoint=endpoint,
                    module=endpoint.module,
                    name=payload.get("name") or f"{endpoint.display_name} - 用例",
                    case_type=payload.get("case_type") or "endpoint",
                    test_type=payload.get("test_type") or "positive",
                    description=payload.get("description") or "",
                    request_config=payload.get("request_config") or {},
                    assertions=payload.get("assertions") or [],
                    extract=payload.get("extract") or {},
                    source=payload.get("source") or "ai",
                    priority=payload.get("priority", 2),
                )
                for payload in generated
            ]
            return Response(
                {
                    "created": len(created),
                    "count": len(created),
                    "cases": APITestCaseSerializer(created, many=True).data,
                },
                status=status.HTTP_201_CREATED,
            )
        generated = generate_endpoint_cases(endpoint, use_ai=use_ai)
        return Response({"count": len(generated), "cases": generated, "preview": True})


# ---------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------
class APITestCaseViewSet(BaseProjectViewSet):
    queryset = APITestCase.objects.select_related("project", "endpoint", "module")
    serializer_class = APITestCaseSerializer
    filterset_fields = (
        "project", "endpoint", "module", "case_type", "test_type", "source", "is_active",
    )
    search_fields = ("name", "description")
    ordering_fields = ("priority", "created_at", "name")

    @action(detail=True, methods=["get", "post"], url_path="generate_script")
    def generate_script(self, request, pk=None):
        case = self.get_object()
        if request.method == "POST":
            require_project_role(request.user, case.project, "editor")
        try:
            script = build_httprunner_yaml(case)
        except BusinessError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("script generation failed")
            raise BusinessError(message=f"脚本生成失败: {exc}", code="script_error") from exc
        if request.method == "POST":
            case.script_yaml = script
            case.save(update_fields=["script_yaml", "updated_at"])
        return Response({"id": case.id, "script_yaml": script})

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        case = self.get_object()
        require_project_role(request.user, case.project, "editor")
        environment_id = _int_or_none(
            request.data.get("environment") or request.query_params.get("environment")
        )
        execution = execution_service.create_case_execution(
            case,
            environment_id=environment_id,
            triggered_by=request.user,
            trigger_type="manual",
        )
        submit(execute_case_task, execution.id)
        return Response(
            {
                "task_id": str(execution.id),
                "execution_id": execution.id,
                "status": "pending",
            },
            status=status.HTTP_202_ACCEPTED,
        )


# ---------------------------------------------------------------------------
# suites
# ---------------------------------------------------------------------------
class APITestSuiteViewSet(BaseProjectViewSet):
    queryset = APITestSuite.objects.select_related("project", "environment")
    serializer_class = APITestSuiteSerializer
    filterset_fields = ("project", "environment", "source", "is_active")
    search_fields = ("name", "description")

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        suite = self.get_object()
        require_project_role(request.user, suite.project, "editor")
        environment_id = _int_or_none(
            request.data.get("environment")
            or request.query_params.get("environment")
            or (suite.environment_id if suite.environment_id else None)
        )
        execution = execution_service.create_suite_execution(
            suite,
            environment_id=environment_id,
            triggered_by=request.user,
            trigger_type="manual",
        )
        submit(execute_suite_task, execution.id)
        return Response(
            {
                "task_id": str(execution.id),
                "execution_id": execution.id,
                "status": "pending",
            },
            status=status.HTTP_202_ACCEPTED,
        )


# ---------------------------------------------------------------------------
# executions
# ---------------------------------------------------------------------------
class APITestExecutionViewSet(BaseReadOnlyProjectViewSet):
    queryset = APITestExecution.objects.select_related(
        "project", "suite", "environment", "triggered_by"
    )
    serializer_class = APITestExecutionSerializer
    filterset_fields = ("project", "suite", "status", "trigger_type")
    search_fields = ("name", "error_message")
    ordering_fields = ("created_at", "duration_ms", "pass_rate")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return APITestExecutionDetailSerializer
        return APITestExecutionSerializer

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        execution = self.get_object()
        require_project_role(request.user, execution.project, "editor")
        if execution.status not in ("pending", "running"):
            raise BusinessError(
                message="执行已结束，无法取消", code="execution_finished", status_code=400
            )
        execution.status = "cancelled"
        execution.finished_at = timezone.now()
        execution.error_message = request.data.get("reason") or "用户取消执行"
        execution.save(
            update_fields=["status", "finished_at", "error_message", "updated_at"]
        )
        return Response(APITestExecutionSerializer(execution).data)

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        execution = self.get_object()
        return Response(execution_service.load_report(execution))


# ---------------------------------------------------------------------------
# Postman import
# ---------------------------------------------------------------------------
class PostmanImportView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        project = _project_from_request(request)
        require_project_role(request.user, project, "editor")

        upload = request.FILES.get("file")
        raw_collection = request.data.get("collection")
        content = request.data.get("content")
        uploaded_file = _store_upload(project, upload, "postman_collection", request.user)

        if upload is not None:
            collection = _load_collection(_read_upload(upload))
        elif raw_collection not in (None, ""):
            collection = _load_collection(raw_collection)
        elif content not in (None, ""):
            collection = _load_collection(content)
        else:
            raise BusinessError(
                message="请提供 Postman Collection 文件或内容", code="missing_file"
            )

        name = request.data.get("name") or None
        base_url = str(request.data.get("base_url") or "")
        try:
            result = import_postman_collection(
                project, collection, name=name, base_url=base_url,
                uploaded_file=uploaded_file, created_by=request.user,
            )
        except BusinessError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("postman import failed")
            raise BusinessError(
                message=f"Postman 导入失败: {exc}", code="invalid_collection"
            ) from exc

        return Response(
            {
                "spec": APISpecificationDetailSerializer(result["spec"]).data,
                "endpoint_count": result["endpoint_count"],
                "case_count": result["case_count"],
                "created": result["created"],
                "updated": result["updated"],
                "cases": APITestCaseSerializer(result["cases"], many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# AI scenario generation
# ---------------------------------------------------------------------------
class AIScenarioGenerateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def post(self, request):
        project = _project_from_request(request)
        require_project_role(request.user, project, "editor")
        requirement = (
            request.data.get("requirement")
            or request.data.get("natural_language")
            or request.data.get("description")
            or ""
        )
        if not str(requirement).strip():
            raise BusinessError(message="缺少 requirement 需求描述", code="missing_requirement")

        result = generate_scenario(requirement, project)
        saved = _as_bool(request.data.get("save"), default=True)
        created_cases = []
        if saved:
            for payload in result.get("cases") or []:
                created_cases.append(
                    APITestCase.objects.create(
                        project=project,
                        name=payload.get("name") or "AI 场景用例",
                        case_type=payload.get("case_type") or "scenario",
                        test_type=payload.get("test_type") or "positive",
                        description=payload.get("description") or "",
                        request_config=payload.get("request_config") or {},
                        assertions=payload.get("assertions") or [],
                        extract=payload.get("extract") or {},
                        source=payload.get("source") or "ai",
                        priority=payload.get("priority", 2),
                    )
                )
        return Response(
            {
                "source": result.get("source", "rule"),
                "scenario": result.get("scenario") or {},
                "count": len(result.get("cases") or []),
                "cases": APITestCaseSerializer(
                    created_cases, many=True
                ).data if created_cases else result.get("cases") or [],
                "saved": saved,
            }
        )
