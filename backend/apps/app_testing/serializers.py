"""DRF serializers for the 移动端 App 测试 module."""

from django.conf import settings
from rest_framework import serializers

from apps.app_testing.models import (
    APP_STEP_ACTIONS,
    AppTestApplication,
    AppTestCase,
    AppTestModule,
    AppTestRun,
    AppTestSuite,
)

STEP_ACTIONS = set(APP_STEP_ACTIONS)


def _media_relpath(path) -> str:
    raw = str(path or "")
    media_root = str(getattr(settings, "MEDIA_ROOT", "") or "")
    if media_root and raw.startswith(media_root):
        return raw[len(media_root):].lstrip("/")
    return raw


def _normalize_id_list(value, field_name):
    """Accept ``[1, 2]``, ``["1", "2"]`` or ``[{"id": 1}]`` for id list fields."""
    if value in (None, ""):
        return []
    if not isinstance(value, (list, tuple)):
        raise serializers.ValidationError(f"{field_name} 必须是数组")
    cleaned = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("id") or item.get("case_id")
        try:
            cleaned.append(int(item))
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError(f"{field_name} 含非法 ID: {item}") from exc
    return cleaned


class AppTestModuleSerializer(serializers.ModelSerializer):
    children_count = serializers.SerializerMethodField()
    case_count = serializers.IntegerField(read_only=True)
    parent_name = serializers.SerializerMethodField()
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = AppTestModule
        fields = (
            "id", "project", "project_name", "parent", "parent_name", "name",
            "description", "order", "case_count", "children_count", "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "project_name",
                            "parent_name")

    def get_children_count(self, obj):
        return getattr(obj, "children_count", None) or obj.children.count()

    def get_parent_name(self, obj):
        return obj.parent.name if obj.parent_id else ""

    def validate(self, attrs):
        project = attrs.get("project") or getattr(self.instance, "project", None)
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        if parent is not None and project is not None and parent.project_id != project.id:
            raise serializers.ValidationError({"parent": "上级模块必须属于同一项目"})
        if self.instance is not None and parent is not None:
            node = parent
            seen = set()
            while node is not None and node.id not in seen:
                if node.id == self.instance.id:
                    raise serializers.ValidationError({"parent": "不能将模块挂到自身或子模块下"})
                seen.add(node.id)
                node = node.parent
        return attrs


class AppTestApplicationSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True)
    app_identifier = serializers.CharField(read_only=True)
    case_count = serializers.SerializerMethodField()

    class Meta:
        model = AppTestApplication
        fields = (
            "id", "project", "project_name", "name", "platform", "package_name",
            "bundle_id", "app_version", "description", "app_identifier", "case_count",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "project_name",
                            "app_identifier")

    def get_case_count(self, obj):
        return getattr(obj, "annotated_case_count", None) or obj.cases.count()

    def validate(self, attrs):
        platform = attrs.get("platform") or getattr(self.instance, "platform", "android")
        package_name = attrs.get("package_name", getattr(self.instance, "package_name", ""))
        bundle_id = attrs.get("bundle_id", getattr(self.instance, "bundle_id", ""))
        if platform == "android" and not package_name and not bundle_id:
            raise serializers.ValidationError({"package_name": "Android 应用必须提供包名"})
        if platform == "ios" and not bundle_id and not package_name:
            raise serializers.ValidationError({"bundle_id": "iOS 应用必须提供 Bundle ID"})
        return attrs


class AppTestCaseSerializer(serializers.ModelSerializer):
    module_name = serializers.SerializerMethodField()
    application_name = serializers.SerializerMethodField()
    project_name = serializers.CharField(source="project.name", read_only=True)
    step_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = AppTestCase
        fields = (
            "id", "project", "project_name", "module", "module_name", "application",
            "application_name", "name", "description", "steps", "sonic_steps",
            "source", "priority", "is_active", "step_count", "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "project_name",
                            "module_name", "application_name", "step_count")

    def get_module_name(self, obj):
        return obj.module.name if obj.module_id else ""

    def get_application_name(self, obj):
        return obj.application.name if obj.application_id else ""

    def validate_steps(self, value):
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("steps 必须是数组")
        for index, step in enumerate(value):
            if not isinstance(step, dict):
                raise serializers.ValidationError(f"第 {index + 1} 个步骤必须是对象")
            action = str(step.get("action") or "").lower()
            if not action:
                raise serializers.ValidationError(f"第 {index + 1} 个步骤缺少 action")
            if action not in STEP_ACTIONS:
                raise serializers.ValidationError(
                    f"第 {index + 1} 个步骤 action 不支持: {action}"
                )
        return value

    def validate_sonic_steps(self, value):
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("sonic_steps 必须是数组")
        return value

    def validate(self, attrs):
        project = attrs.get("project") or getattr(self.instance, "project", None)
        if project is None:
            return attrs
        module = attrs.get("module", getattr(self.instance, "module", None))
        if module is not None and module.project_id != project.id:
            raise serializers.ValidationError({"module": "模块必须属于同一项目"})
        application = attrs.get("application", getattr(self.instance, "application", None))
        if application is not None and application.project_id != project.id:
            raise serializers.ValidationError({"application": "应用必须属于同一项目"})
        return attrs

    def create(self, validated_data):
        sync = "steps" in validated_data and "sonic_steps" not in validated_data
        instance = super().create(validated_data)
        if sync:
            self._sync_sonic_steps(instance)
        return instance

    def update(self, instance, validated_data):
        sync = "steps" in validated_data and "sonic_steps" not in validated_data
        instance = super().update(instance, validated_data)
        if sync:
            self._sync_sonic_steps(instance)
        return instance

    @staticmethod
    def _sync_sonic_steps(instance):
        """Keep ``sonic_steps`` in sync whenever only AITS steps were supplied."""
        from apps.app_testing.services.case_converter import aits_steps_to_sonic

        sonic_steps = aits_steps_to_sonic(instance.steps or [])
        if instance.sonic_steps != sonic_steps:
            instance.sonic_steps = sonic_steps
            instance.save(update_fields=["sonic_steps", "updated_at"])


class AppTestSuiteSerializer(serializers.ModelSerializer):
    case_count = serializers.IntegerField(read_only=True)
    application_name = serializers.SerializerMethodField()
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = AppTestSuite
        fields = (
            "id", "project", "project_name", "name", "description", "case_ids",
            "application", "application_name", "device_config", "is_active",
            "case_count", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "project_name",
                            "application_name", "case_count")

    def get_application_name(self, obj):
        return obj.application.name if obj.application_id else ""

    def validate_case_ids(self, value):
        ids = _normalize_id_list(value, "case_ids")
        project_id = self.initial_data.get("project") or getattr(
            self.instance, "project_id", None
        )
        if project_id and ids:
            valid = set(
                AppTestCase.objects.filter(project_id=project_id, id__in=ids)
                .values_list("id", flat=True)
            )
            missing = [cid for cid in ids if cid not in valid]
            if missing:
                raise serializers.ValidationError(f"以下用例不属于该项目: {missing}")
        return ids

    def validate_device_config(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("device_config 必须是对象")
        return value

    def validate(self, attrs):
        project = attrs.get("project") or getattr(self.instance, "project", None)
        application = attrs.get("application", getattr(self.instance, "application", None))
        if (application is not None and project is not None
                and application.project_id != project.id):
            raise serializers.ValidationError({"application": "应用必须属于同一项目"})
        return attrs


class AppTestRunSerializer(serializers.ModelSerializer):
    suite_name = serializers.SerializerMethodField()
    project_name = serializers.CharField(source="project.name", read_only=True)
    report_url = serializers.SerializerMethodField()

    class Meta:
        model = AppTestRun
        fields = (
            "id", "project", "project_name", "suite", "suite_name", "name", "status",
            "trigger_type", "device_udid", "device_id", "device_name", "platform",
            "started_at", "finished_at", "duration_ms", "total", "passed", "failed",
            "skipped", "pass_rate", "sonic_suite_id", "report_path", "report_url",
            "summary", "error_message", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_suite_name(self, obj):
        return obj.suite.name if obj.suite_id else ""

    def get_report_url(self, obj):
        return (obj.summary or {}).get("report_url", "") or _media_relpath(obj.report_path)
