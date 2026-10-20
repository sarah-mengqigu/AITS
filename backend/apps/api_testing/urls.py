"""URL configuration for the API 测试 module (``/api/api-testing/``)."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.api_testing.views import (
    AIScenarioGenerateView,
    APIEndpointViewSet,
    APIModuleViewSet,
    APISpecificationViewSet,
    APITestCaseViewSet,
    APITestExecutionViewSet,
    APITestSuiteViewSet,
    PostmanImportView,
)

router = DefaultRouter()
router.register("specs", APISpecificationViewSet, basename="api-spec")
router.register("modules", APIModuleViewSet, basename="api-module")
router.register("endpoints", APIEndpointViewSet, basename="api-endpoint")
router.register("cases", APITestCaseViewSet, basename="api-case")
router.register("suites", APITestSuiteViewSet, basename="api-suite")
router.register("executions", APITestExecutionViewSet, basename="api-execution")

urlpatterns = [
    path("postman/import/", PostmanImportView.as_view(), name="api-postman-import"),
    path(
        "ai/generate_scenario/",
        AIScenarioGenerateView.as_view(),
        name="api-ai-generate-scenario",
    ),
] + router.urls
