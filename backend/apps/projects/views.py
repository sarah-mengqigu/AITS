from django.db import transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.api.api_exception_handler import BusinessError
from apps.common.permissions import (
    ProjectRolePermission,
    get_user_role,
    require_project_role,
)
from apps.projects.models import (
    Environment,
    KnowledgeDocument,
    Project,
    ProjectMember,
    ProjectThirdPartyConfig,
    UploadedFile,
)
from apps.projects.serializers import (
    EnvironmentSerializer,
    KnowledgeDocumentSerializer,
    ProjectMemberSerializer,
    ProjectSerializer,
    ProjectThirdPartyConfigSerializer,
    UploadedFileSerializer,
)


def projects_for(user):
    """Projects a user can access (owned, member of, or all for superuser)."""
    if getattr(user, "is_superuser", False):
        return Project.objects.all()
    return Project.objects.filter(Q(owner=user) | Q(members__user=user)).distinct()


class ProjectScopedViewSet(viewsets.ModelViewSet):
    """Base viewset that scopes querysets to the caller's projects."""

    permission_classes = [IsAuthenticated, ProjectRolePermission]
    project_field = "project"

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        return qs.filter(**{f"{self.project_field}__in": projects_for(user)})

    def perform_create(self, serializer):
        project = serializer.validated_data.get(self.project_field)
        if project is not None:
            require_project_role(self.request.user, project, "editor")
        serializer.save()

    def perform_update(self, serializer):
        project = serializer.validated_data.get(
            self.project_field, getattr(serializer.instance, self.project_field, None)
        )
        if project is not None:
            require_project_role(self.request.user, project, "editor")
        serializer.save()


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project_type", "is_active")
    search_fields = ("name", "description")
    ordering_fields = ("created_at", "updated_at", "name")

    def get_queryset(self):
        return projects_for(self.request.user).select_related("owner").prefetch_related(
            "linked_api_projects"
        )

    def get_permissions(self):
        if self.action in ("retrieve", "list", "stats", "members"):
            return [IsAuthenticated()]
        if self.action == "create":
            return [IsAuthenticated()]
        return [IsAuthenticated(), ProjectRolePermission()]

    def perform_create(self, serializer):
        project = serializer.save(owner=self.request.user)
        ProjectMember.objects.get_or_create(
            project=project, user=self.request.user, defaults={"role": "owner"}
        )
        ProjectThirdPartyConfig.objects.get_or_create(project=project)

    def perform_destroy(self, instance):
        require_project_role(self.request.user, instance, "owner")
        instance.delete()

    @action(detail=True, methods=["get"])
    def members(self, request, pk=None):
        project = self.get_object()
        role = get_user_role(request.user, project)
        if role is None:
            raise BusinessError(message="无权访问该项目", code="permission_denied",
                                status_code=403)
        members = project.members.select_related("user").all()
        return Response(ProjectMemberSerializer(members, many=True).data)

    @action(detail=True, methods=["post"], url_path="members/add")
    def add_member(self, request, pk=None):
        project = self.get_object()
        require_project_role(request.user, project, "admin")
        payload = dict(request.data)
        payload["project"] = project.id
        serializer = ProjectMemberSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        member, created = ProjectMember.objects.update_or_create(
            project=project,
            user=serializer.validated_data["user"],
            defaults={
                "role": serializer.validated_data.get("role", "editor"),
                "invited_by": request.user,
            },
        )
        return Response(
            ProjectMemberSerializer(member).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["delete"], url_path=r"members/(?P<member_id>[^/.]+)")
    def remove_member(self, request, pk=None, member_id=None):
        project = self.get_object()
        require_project_role(request.user, project, "admin")
        member = project.members.filter(pk=member_id).select_related("user").first()
        if not member:
            raise BusinessError(message="成员不存在", code="not_found", status_code=404)
        if member.user_id == project.owner_id:
            raise BusinessError(message="不能移除项目拥有者", code="invalid_operation")
        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "put", "patch"], url_path="third-party-config")
    def third_party_config(self, request, pk=None):
        project = self.get_object()
        if get_user_role(request.user, project) is None:
            raise BusinessError(message="无权访问该项目", code="permission_denied",
                                status_code=403)
        config, _ = ProjectThirdPartyConfig.objects.get_or_create(project=project)
        if request.method == "GET":
            return Response(ProjectThirdPartyConfigSerializer(config).data)

        require_project_role(request.user, project, "admin")
        serializer = ProjectThirdPartyConfigSerializer(
            config, data=request.data, partial=request.method == "PATCH"
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        project = self.get_object()
        if get_user_role(request.user, project) is None:
            raise BusinessError(message="无权访问该项目", code="permission_denied",
                                status_code=403)
        return Response(
            {
                "project_id": project.id,
                "member_count": project.members.count(),
                "environment_count": project.environments.count(),
                "file_count": project.files.count(),
                "knowledge_count": project.knowledge_documents.count(),
                "modules": {
                    "api": project.api_specifications.count() if hasattr(project, "api_specifications") else 0,
                    "web": project.web_modules.count() if hasattr(project, "web_modules") else 0,
                    "app": project.app_modules.count() if hasattr(project, "app_modules") else 0,
                    "perf": project.performance_scenarios.count() if hasattr(project, "performance_scenarios") else 0,
                },
            }
        )


class EnvironmentViewSet(ProjectScopedViewSet):
    queryset = Environment.objects.select_related("project")
    serializer_class = EnvironmentSerializer
    filterset_fields = ("project", "env_type", "is_default")
    search_fields = ("name", "base_url")

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        require_project_role(self.request.user, project, "editor")
        if not Environment.objects.filter(project=project).exists():
            serializer.save(is_default=True)
        else:
            serializer.save()

    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, pk=None):
        env = self.get_object()
        require_project_role(request.user, env.project, "editor")
        env.is_default = True
        env.save(update_fields=["is_default"])
        return Response(EnvironmentSerializer(env).data)


class ProjectMemberViewSet(ProjectScopedViewSet):
    queryset = ProjectMember.objects.select_related("user", "project")
    serializer_class = ProjectMemberSerializer
    filterset_fields = ("project", "role")
    search_fields = ("user__username", "user__email")

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        require_project_role(self.request.user, project, "admin")
        serializer.save(invited_by=self.request.user)


class UploadedFileViewSet(ProjectScopedViewSet):
    queryset = UploadedFile.objects.select_related("project", "uploaded_by")
    serializer_class = UploadedFileSerializer
    filterset_fields = ("project", "purpose")
    parser_classes = [MultiPartParser, FormParser]

    def create(self, request, *args, **kwargs):
        from apps.common.storage.file_storage import save_uploaded_file

        project_id = request.data.get("project")
        if not project_id:
            raise BusinessError(message="缺少 project 参数", code="missing_project")
        project = Project.objects.filter(pk=project_id).first()
        if project is None:
            raise BusinessError(message="项目不存在", code="not_found", status_code=404)
        require_project_role(request.user, project, "editor")
        upload = request.FILES.get("file")
        stored_path, sha, size = save_uploaded_file(
            upload, subdir=f"projects/{project.id}"
        )
        instance, created = UploadedFile.objects.get_or_create(
            sha256=sha,
            project=project,
            defaults={
                "original_name": upload.name,
                "stored_path": stored_path,
                "size": size,
                "content_type": getattr(upload, "content_type", "") or "",
                "purpose": request.data.get("purpose", "generic"),
                "uploaded_by": request.user,
            },
        )
        return Response(
            UploadedFileSerializer(instance).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        from django.http import FileResponse

        instance = self.get_object()
        from django.conf import settings
        from pathlib import Path

        path = Path(settings.MEDIA_ROOT) / instance.stored_path
        if not path.exists():
            raise BusinessError(message="文件不存在", code="not_found", status_code=404)
        return FileResponse(open(path, "rb"), as_attachment=True,
                            filename=instance.original_name)


class KnowledgeDocumentViewSet(ProjectScopedViewSet):
    queryset = KnowledgeDocument.objects.select_related("project", "source_file")
    serializer_class = KnowledgeDocumentSerializer
    filterset_fields = ("project", "status")
    search_fields = ("title", "content")

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        require_project_role(self.request.user, project, "editor")
        document = serializer.save()
        self._maybe_index(document)

    def perform_update(self, serializer):
        document = serializer.instance
        require_project_role(self.request.user, document.project, "editor")
        document = serializer.save(status="pending")
        self._maybe_index(document)

    def _maybe_index(self, document):
        """Kick off RAG indexing when available (ai_core may be absent)."""
        try:
            from apps.ai_core.services.rag_service import RAGService

            RAGService().index_document(document)
        except Exception:
            pass

    @action(detail=True, methods=["post"])
    def reindex(self, request, pk=None):
        document = self.get_object()
        require_project_role(request.user, document.project, "editor")
        try:
            from apps.ai_core.services.rag_service import RAGService

            chunks = RAGService().index_document(document)
            return Response({"detail": "索引完成", "chunk_count": chunks})
        except Exception as exc:
            document.status = "failed"
            document.error_message = str(exc)
            document.save(update_fields=["status", "error_message"])
            raise BusinessError(message=f"索引失败: {exc}", code="index_failed")
