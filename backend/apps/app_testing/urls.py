"""Router registration for ``/api/app-testing/`` (mounted by the root urls)."""

from rest_framework.routers import DefaultRouter

from apps.app_testing.views import (
    AppTestApplicationViewSet,
    AppTestCaseViewSet,
    AppTestModuleViewSet,
    AppTestRunViewSet,
    AppTestSuiteViewSet,
    SonicDeviceViewSet,
    SonicElementPageViewSet,
)

router = DefaultRouter()
router.register("modules", AppTestModuleViewSet, basename="app-module")
router.register("applications", AppTestApplicationViewSet, basename="app-application")
router.register("cases", AppTestCaseViewSet, basename="app-case")
router.register("suites", AppTestSuiteViewSet, basename="app-suite")
router.register("runs", AppTestRunViewSet, basename="app-run")
router.register("devices", SonicDeviceViewSet, basename="app-device")
router.register("element-pages", SonicElementPageViewSet, basename="app-element-page")

urlpatterns = router.urls
