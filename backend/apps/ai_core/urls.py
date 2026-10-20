"""URL routing for ``/api/ai/`` (mounted by the root URLConf)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.ai_core.views import (
    AgentViewSet,
    LLMConfigurationViewSet,
    LLMUsageLogViewSet,
    MCPConfigurationViewSet,
    MCPToolViewSet,
    RAGConfigurationViewSet,
    RagIndexView,
    RagSearchView,
    RagStatsView,
    UsageStatsView,
)

router = DefaultRouter()
router.register("llm-configs", LLMConfigurationViewSet, basename="llm-config")
router.register("rag-configs", RAGConfigurationViewSet, basename="rag-config")
router.register("mcp-configs", MCPConfigurationViewSet, basename="mcp-config")
router.register("mcp-tools", MCPToolViewSet, basename="mcp-tool")
router.register("usage-logs", LLMUsageLogViewSet, basename="llm-usage-log")
router.register("agents", AgentViewSet, basename="agent")

urlpatterns = [
    path("rag/index/", RagIndexView.as_view(), name="rag-index"),
    path("rag/search/", RagSearchView.as_view(), name="rag-search"),
    path("rag/stats/", RagStatsView.as_view(), name="rag-stats"),
    path("usage-stats/", UsageStatsView.as_view(), name="usage-stats"),
    path("", include(router.urls)),
]
