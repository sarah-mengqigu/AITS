"""Router registration for ``/api/web-testing/`` (mounted by the root urls)."""

from rest_framework.routers import DefaultRouter

from apps.web_testing.views import (
    MidSceneScriptViewSet,
    WebElementViewSet,
    WebPageViewSet,
    WebUITestCaseViewSet,
    WebUITestExecutionViewSet,
    WebUITestModuleViewSet,
    WebUITestSuiteViewSet,
)

router = DefaultRouter()
router.register("modules", WebUITestModuleViewSet, basename="web-module")
router.register("cases", WebUITestCaseViewSet, basename="web-case")
router.register("suites", WebUITestSuiteViewSet, basename="web-suite")
router.register("executions", WebUITestExecutionViewSet, basename="web-execution")
router.register("pages", WebPageViewSet, basename="web-page")
router.register("elements", WebElementViewSet, basename="web-element")
router.register("midscene-scripts", MidSceneScriptViewSet, basename="midscene-script")

urlpatterns = router.urls
