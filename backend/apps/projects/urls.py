from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.projects.views import (
    EnvironmentViewSet,
    KnowledgeDocumentViewSet,
    ProjectMemberViewSet,
    ProjectViewSet,
    UploadedFileViewSet,
)

router = DefaultRouter()
router.register("environments", EnvironmentViewSet, basename="environment")
router.register("members", ProjectMemberViewSet, basename="project-member")
router.register("files", UploadedFileViewSet, basename="uploaded-file")
router.register("knowledge", KnowledgeDocumentViewSet, basename="knowledge-document")
router.register("", ProjectViewSet, basename="project")

urlpatterns = [
    path("", include(router.urls)),
]
