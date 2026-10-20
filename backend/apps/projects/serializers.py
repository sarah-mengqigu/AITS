from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.projects.models import (
    Environment,
    KnowledgeDocument,
    Project,
    ProjectMember,
    ProjectThirdPartyConfig,
    UploadedFile,
)

User = get_user_model()


class ProjectMemberSerializer(serializers.ModelSerializer):
    user_detail = serializers.SerializerMethodField()
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = ProjectMember
        fields = ("id", "project", "user", "username", "email", "user_detail", "role",
                  "created_at")
        read_only_fields = ("id", "created_at")

    def get_user_detail(self, obj):
        return {
            "id": obj.user_id,
            "username": obj.user.username,
            "nickname": obj.user.nickname,
            "email": obj.user.email,
            "avatar": obj.user.avatar,
        }

    def validate(self, attrs):
        project = attrs.get("project") or getattr(self.instance, "project", None)
        user = attrs.get("user") or getattr(self.instance, "user", None)
        if project and user and project.owner_id == user.id:
            raise serializers.ValidationError("拥有者角色不可重复添加")
        role = attrs.get("role")
        if role == "owner" and self.instance is None:
            raise serializers.ValidationError("不能在成员中额外授予 owner 角色")
        return attrs


class EnvironmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Environment
        fields = ("id", "project", "name", "env_type", "base_url", "variables", "headers",
                  "is_default", "description", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_variables(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("环境变量必须是对象")
        return value

    def validate_headers(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("请求头必须是对象")
        return value


class ProjectThirdPartyConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectThirdPartyConfig
        fields = ("id", "project", "dingtalk_webhook", "wecom_webhook", "feishu_webhook",
                  "gitlab_url", "gitlab_token", "extra", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class ProjectSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.username", read_only=True)
    member_count = serializers.IntegerField(read_only=True)
    role = serializers.SerializerMethodField()
    linked_api_projects = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Project.objects.all(), required=False
    )

    class Meta:
        model = Project
        fields = ("id", "name", "description", "project_type", "owner", "owner_name",
                  "is_active", "sonic_project_id", "linked_api_projects", "tags",
                  "settings", "member_count", "role", "created_at", "updated_at")
        read_only_fields = ("id", "owner", "created_at", "updated_at")

    def get_role(self, obj):
        request = self.context.get("request")
        if not request:
            return None
        from apps.common.permissions import get_user_role

        return get_user_role(request.user, obj)

    def validate_sonic_project_id(self, value):
        return (value or "").strip()

    def validate(self, attrs):
        project_type = attrs.get("project_type") or getattr(
            self.instance, "project_type", "api"
        )
        linked = attrs.get("linked_api_projects")
        if linked and project_type != "perf":
            raise serializers.ValidationError(
                {"linked_api_projects": "仅性能项目可关联 API 项目"}
            )
        if linked:
            for project in linked:
                if project.project_type != "api":
                    raise serializers.ValidationError(
                        {"linked_api_projects": f"{project.name} 不是 API 项目"}
                    )
        return attrs


class UploadedFileSerializer(serializers.ModelSerializer):
    url = serializers.CharField(read_only=True)
    uploaded_by_name = serializers.CharField(source="uploaded_by.username", read_only=True,
                                             default="")

    class Meta:
        model = UploadedFile
        fields = ("id", "project", "original_name", "stored_path", "sha256", "size",
                  "content_type", "purpose", "uploaded_by", "uploaded_by_name", "url",
                  "created_at")
        read_only_fields = ("id", "stored_path", "sha256", "size", "content_type",
                            "uploaded_by", "created_at")


class KnowledgeDocumentSerializer(serializers.ModelSerializer):
    source_file_name = serializers.CharField(source="source_file.original_name",
                                             read_only=True, default="")

    class Meta:
        model = KnowledgeDocument
        fields = ("id", "project", "title", "content", "source_file", "source_file_name",
                  "status", "chunk_count", "error_message", "indexed_at", "metadata",
                  "created_at", "updated_at")
        read_only_fields = ("id", "status", "chunk_count", "error_message", "indexed_at",
                            "created_at", "updated_at")
