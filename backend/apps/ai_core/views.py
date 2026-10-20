"""AI 核心模块 HTTP 接口（``/api/ai/``）。

权限约定（ARCHITECTURE §2.7 / §1.4）：
* 所有接口 ``IsAuthenticated``；
* 配置读：全局配置所有登录用户可读，项目配置需属主/成员；
* 配置写（含 set-default / refresh_tools）：全局需 ``is_staff``，
  项目需 ``admin`` 及以上；
* RAG 索引需要文档所属项目的 ``editor`` 及以上。
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_core.models import (
    LLMConfiguration,
    LLMUsageLog,
    MCPConfiguration,
    MCPTool,
    RAGConfiguration,
)
from apps.ai_core.serializers import (
    LLMConfigurationSerializer,
    LLMUsageLogSerializer,
    MCPConfigurationSerializer,
    MCPToolSerializer,
    RAGConfigurationSerializer,
)
from apps.ai_core.services.agents.registry import list_agents, run_agent
from apps.ai_core.services.llm_service import LLMService
from apps.ai_core.services.rag_service import RAGService
from apps.common.api.api_exception_handler import BusinessError
from apps.common.permissions import get_user_role, require_project_role
from apps.projects.models import KnowledgeDocument, Project
from apps.projects.views import projects_for


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def ensure_config_write(user, project) -> None:
    """Global configs need staff; project configs need admin/owner."""
    if project is None:
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return
        raise BusinessError(
            message="全局配置仅管理员（staff）可修改",
            code="permission_denied",
            status_code=403,
        )
    require_project_role(user, project, "admin")


def _parse_date_param(value: str, label: str):
    parsed = parse_date(value)
    if parsed is None:
        raise BusinessError(
            message=f"{label} 日期格式应为 YYYY-MM-DD",
            code="validation_error",
            status_code=400,
        )
    return parsed


def _as_bool(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class ProjectAwareConfigViewSet(viewsets.ModelViewSet):
    """Shared queryset scoping + write permissions for config resources."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return queryset
        return queryset.filter(
            Q(project__isnull=True) | Q(project__in=projects_for(user))
        ).distinct()

    def perform_create(self, serializer):
        ensure_config_write(self.request.user, serializer.validated_data.get("project"))
        serializer.save()

    def perform_update(self, serializer):
        project = serializer.validated_data.get(
            "project", getattr(serializer.instance, "project", None)
        )
        ensure_config_write(self.request.user, project)
        serializer.save()

    def perform_destroy(self, instance):
        ensure_config_write(self.request.user, instance.project)
        instance.delete()

    def assert_can_write(self, instance) -> None:
        ensure_config_write(self.request.user, instance.project)


# ---------------------------------------------------------------------------
# LLM configurations
# ---------------------------------------------------------------------------
class LLMConfigurationViewSet(ProjectAwareConfigViewSet):
    queryset = LLMConfiguration.objects.select_related("project")
    serializer_class = LLMConfigurationSerializer
    filterset_fields = ("project", "provider", "model_type", "is_active", "is_default")
    search_fields = ("name", "model_name")
    ordering_fields = ("created_at", "updated_at", "name")

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        config = self.get_object()
        # Connectivity probing spends real tokens -> same gate as writes.
        self.assert_can_write(config)
        service = LLMService(config=config, project=config.project)
        return Response(service.test_connection())

    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, pk=None):
        config = self.get_object()
        self.assert_can_write(config)
        # save() enforces one default per (project, model_type)
        config.is_default = True
        config.is_active = True
        config.save()
        config.refresh_from_db()
        return Response(self.get_serializer(config).data)


# ---------------------------------------------------------------------------
# RAG configurations
# ---------------------------------------------------------------------------
class RAGConfigurationViewSet(ProjectAwareConfigViewSet):
    queryset = RAGConfiguration.objects.select_related("project")
    serializer_class = RAGConfigurationSerializer
    filterset_fields = ("project", "vector_store", "embedding_mode", "is_default")
    search_fields = ("name", "collection_name")

    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, pk=None):
        config = self.get_object()
        self.assert_can_write(config)
        config.is_default = True
        config.save()
        config.refresh_from_db()
        return Response(self.get_serializer(config).data)


# ---------------------------------------------------------------------------
# MCP configurations + tools
# ---------------------------------------------------------------------------
class MCPConfigurationViewSet(ProjectAwareConfigViewSet):
    queryset = MCPConfiguration.objects.select_related("project").prefetch_related("tools")
    serializer_class = MCPConfigurationSerializer
    filterset_fields = ("project", "transport", "is_active", "last_status")
    search_fields = ("name",)

    @action(detail=True, methods=["post"], url_path="refresh_tools")
    def refresh_tools(self, request, pk=None):
        config = self.get_object()
        self.assert_can_write(config)
        result = config.refresh_tools()
        return Response({"config": config.id, **result})


class MCPToolViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MCPTool.objects.select_related("config", "config__project")
    serializer_class = MCPToolSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("config", "is_enabled")
    search_fields = ("name", "description")

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return queryset
        return queryset.filter(
            Q(config__project__isnull=True) | Q(config__project__in=projects_for(user))
        ).distinct()


# ---------------------------------------------------------------------------
# usage logs / stats
# ---------------------------------------------------------------------------
class LLMUsageLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LLMUsageLog.objects.select_related("project", "config")
    serializer_class = LLMUsageLogSerializer
    permission_classes = [IsAuthenticated]
    ordering_fields = ("created_at", "total_tokens", "response_time_ms")

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not getattr(user, "is_superuser", False):
            queryset = queryset.filter(
                Q(project__isnull=True) | Q(project__in=projects_for(user))
            )
        params = self.request.query_params
        agent = params.get("agent") or params.get("agent_name")
        if agent:
            queryset = queryset.filter(agent_name=agent)
        success = params.get("success")
        if success is not None and str(success) != "":
            queryset = queryset.filter(success=_as_bool(success))
        task_type = params.get("task_type")
        if task_type:
            queryset = queryset.filter(task_type=task_type)
        project = params.get("project")
        if project:
            queryset = queryset.filter(project_id=project)
        model = params.get("model")
        if model:
            queryset = queryset.filter(config__model_name__icontains=model)
        date_from = params.get("date_from")
        if date_from:
            queryset = queryset.filter(
                created_at__date__gte=_parse_date_param(date_from, "date_from")
            )
        date_to = params.get("date_to")
        if date_to:
            queryset = queryset.filter(
                created_at__date__lte=_parse_date_param(date_to, "date_to")
            )
        return queryset


class UsageStatsView(APIView):
    """Aggregate usage by day / model / agent."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = LLMUsageLog.objects.all()
        user = request.user
        if not getattr(user, "is_superuser", False):
            queryset = queryset.filter(
                Q(project__isnull=True) | Q(project__in=projects_for(user))
            )
        params = request.query_params
        project = params.get("project")
        if project:
            queryset = queryset.filter(project_id=project)
        agent = params.get("agent") or params.get("agent_name")
        if agent:
            queryset = queryset.filter(agent_name=agent)
        date_from = params.get("date_from")
        if date_from:
            queryset = queryset.filter(
                created_at__date__gte=_parse_date_param(date_from, "date_from")
            )
        days = params.get("days")
        if days:
            try:
                days_value = int(days)
            except (TypeError, ValueError):
                raise BusinessError(message="days 必须为整数", code="validation_error")
            if days_value > 0:
                since = timezone.now() - timedelta(days=days_value)
                queryset = queryset.filter(created_at__gte=since)

        rows = list(
            queryset.values(
                "agent_name",
                "task_type",
                "success",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "response_time_ms",
                "created_at",
                "config__model_name",
                "config__provider",
            )
        )
        total = {
            "requests": len(rows),
            "success": sum(1 for row in rows if row["success"]),
            "failed": sum(1 for row in rows if not row["success"]),
            "prompt_tokens": sum(int(row["prompt_tokens"] or 0) for row in rows),
            "completion_tokens": sum(int(row["completion_tokens"] or 0) for row in rows),
            "total_tokens": sum(int(row["total_tokens"] or 0) for row in rows),
            "avg_response_time_ms": round(
                sum(int(row["response_time_ms"] or 0) for row in rows) / len(rows), 2
            )
            if rows
            else 0,
        }

        by_day: dict[str, dict] = {}
        by_model: dict[str, dict] = {}
        by_agent: dict[str, dict] = {}
        for row in rows:
            created_at = row["created_at"]
            day = (
                timezone.localtime(created_at).strftime("%Y-%m-%d")
                if created_at
                else ""
            )
            bucket = by_day.setdefault(
                day, {"date": day, "requests": 0, "success": 0, "failed": 0, "total_tokens": 0}
            )
            bucket["requests"] += 1
            bucket["success" if row["success"] else "failed"] += 1
            bucket["total_tokens"] += int(row["total_tokens"] or 0)

            model = row["config__model_name"] or "mock"
            model_bucket = by_model.setdefault(
                model,
                {
                    "model": model,
                    "provider": row["config__provider"] or "mock",
                    "requests": 0,
                    "total_tokens": 0,
                },
            )
            model_bucket["requests"] += 1
            model_bucket["total_tokens"] += int(row["total_tokens"] or 0)

            agent_name = row["agent_name"] or "unknown"
            agent_bucket = by_agent.setdefault(
                agent_name,
                {"agent": agent_name, "requests": 0, "total_tokens": 0},
            )
            agent_bucket["requests"] += 1
            agent_bucket["total_tokens"] += int(row["total_tokens"] or 0)

        return Response(
            {
                "total": total,
                "by_day": sorted(by_day.values(), key=lambda item: item["date"]),
                "by_model": sorted(
                    by_model.values(), key=lambda item: (-item["requests"], item["model"])
                ),
                "by_agent": sorted(
                    by_agent.values(), key=lambda item: (-item["requests"], item["agent"])
                ),
            }
        )


# ---------------------------------------------------------------------------
# RAG actions
# ---------------------------------------------------------------------------
class RagIndexView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        document_id = request.data.get("document_id")
        if document_id in (None, "", []):
            raise BusinessError(message="document_id 不能为空", code="validation_error")
        document = (
            KnowledgeDocument.objects.select_related("project")
            .filter(pk=document_id)
            .first()
        )
        if document is None:
            raise Http404("document not found")
        require_project_role(request.user, document.project, "editor")
        chunk_count = RAGService().index_document(document)
        document.refresh_from_db()
        return Response(
            {
                "document_id": document.id,
                "chunk_count": chunk_count,
                "status": document.status,
                "indexed_at": document.indexed_at,
            }
        )


class RagSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        query = request.data.get("query") or request.query_params.get("query")
        if not query or not str(query).strip():
            raise BusinessError(message="query 不能为空", code="validation_error")
        project = None
        project_id = request.data.get("project") or request.query_params.get("project")
        if project_id not in (None, ""):
            project = Project.objects.filter(pk=project_id).first()
            if project is None:
                raise Http404("project not found")
            if not getattr(request.user, "is_superuser", False) and get_user_role(
                request.user, project
            ) is None:
                raise BusinessError(
                    message="无权访问该项目", code="permission_denied", status_code=403
                )
        try:
            top_k = int(request.data.get("top_k") or request.query_params.get("top_k") or 5)
        except (TypeError, ValueError):
            raise BusinessError(message="top_k 必须为整数", code="validation_error")
        results = RAGService().search(str(query), project=project, top_k=top_k)
        return Response(
            {"query": str(query), "top_k": top_k, "count": len(results), "results": results}
        )


class RagStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(RAGService().stats())


# ---------------------------------------------------------------------------
# agents
# ---------------------------------------------------------------------------
class AgentViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        agents = list_agents()
        return Response({"count": len(agents), "results": agents})

    @action(detail=True, methods=["post"], url_path="run")
    def run(self, request, pk=None):
        data = request.data if isinstance(request.data, dict) else {}
        raw_payload = data.get("payload")
        if isinstance(raw_payload, dict):
            payload = raw_payload
        else:
            payload = {
                key: value
                for key, value in data.items()
                if key not in {"payload", "stream_task_id"}
            }
        result = run_agent(pk, payload, stream_task_id=data.get("stream_task_id"))
        return Response(result)
