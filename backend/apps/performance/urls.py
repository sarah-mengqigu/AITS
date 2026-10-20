"""URL configuration for the 性能测试 module (``/api/performance/``)."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.performance.views import (
    AiDiagnosisRecordViewSet,
    GrafanaWebhookView,
    LoadConfigurationViewSet,
    PerformanceDashboardView,
    PerformanceExecutionViewSet,
    PerformanceScenarioViewSet,
)

router = DefaultRouter()
router.register("configs", LoadConfigurationViewSet, basename="performance-config")
router.register("scenarios", PerformanceScenarioViewSet, basename="performance-scenario")
router.register("executions", PerformanceExecutionViewSet, basename="performance-execution")
router.register("diagnoses", AiDiagnosisRecordViewSet, basename="performance-diagnosis")

urlpatterns = [
    path("dashboard/", PerformanceDashboardView.as_view(), name="performance-dashboard"),
    path("grafana/webhook/", GrafanaWebhookView.as_view(), name="performance-grafana-webhook"),
] + router.urls
