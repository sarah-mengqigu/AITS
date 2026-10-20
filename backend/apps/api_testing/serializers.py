"""Serializers for the API 测试 module."""

from rest_framework import serializers

from apps.api_testing.models import (
    APIEndpoint,
    APIModule,
    APISpecification,
    APITestCase,
    APITestCaseExecutionDetail,
    APITestExecution,
    APITestSuite,
    APITestSuiteExecutionDetail,
)


# ---------------------------------------------------------------------------
# specification / module / endpoint
# ---------------------------------------------------------------------------
class APISpecificationSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True)
    file_name = serializers.CharField(source="file.original_name", read_only=True, default="")
    module_count = serializers.SerializerMethodField()

    class Meta:
        model = APISpecification
        fields = (
            "id", "project", "project_name", "name", "source_type", "version", "base_url",
            "status", "endpoint_count", "module_count", "file", "file_name",
            "error_message", "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "status", "endpoint_count", "error_message", "created_at", "updated_at",
        )

    def get_module_count(self, obj) -> int:
        return obj.modules.count()


class APISpecificationDetailSerializer(APISpecificationSerializer):
    class Meta(APISpecificationSerializer.Meta):
        fields = APISpecificationSerializer.Meta.fields + ("spec_data",)
        read_only_fields = APISpecificationSerializer.Meta.read_only_fields + ("spec_data",)


class APIModuleSerializer(serializers.ModelSerializer):
    children_count = serializers.SerializerMethodField()
    full_path = serializers.CharField(read_only=True)
    spec_name = serializers.CharField(source="spec.name", read_only=True, default="")

    class Meta:
        model = APIModule
        fields = (
            "id", "project", "spec", "spec_name", "parent", "name", "description", "order",
            "full_path", "children_count", "created_at", "updated_at",
        )
        read_only_fields = ("id", "full_path", "created_at", "updated_at")

    def get_children_count(self, obj) -> int:
        return obj.children.count()

    def validate_parent(self, value):
        instance = self.instance
        project = self.initial_data.get("project") or getattr(instance, "project_id", None)
        if value is not None:
            if project is not None and str(value.project_id) != str(project):
                raise serializers.ValidationError("父模块必须属于同一项目")
            if instance is not None and value.pk == instance.pk:
                raise serializers.ValidationError("模块不能以自身作为父模块")
        return value

    def validate(self, attrs):
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        depth = 0
        node = parent
        while node is not None and depth < 50:
            node = node.parent
            depth += 1
        if depth >= 50:
            raise serializers.ValidationError({"parent": "模块层级过深"})
        return attrs


class APIEndpointSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    spec_name = serializers.CharField(source="spec.name", read_only=True, default="")
    module_name = serializers.CharField(source="module.name", read_only=True, default="")
    case_count = serializers.SerializerMethodField()

    class Meta:
        model = APIEndpoint
        fields = (
            "id", "project", "spec", "spec_name", "module", "module_name", "path", "method",
            "operation_id", "summary", "description", "display_name", "parameters",
            "request_body", "responses", "headers", "is_active", "case_count",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "display_name", "created_at", "updated_at")

    def get_case_count(self, obj) -> int:
        return obj.test_cases.count()

    def validate_method(self, value):
        return str(value or "").lower()

    def validate_parameters(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("parameters 必须是数组")
        return value

    def validate_request_body(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("request_body 必须是对象")
        return value

    def validate_responses(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("responses 必须是对象")
        return value

    def validate_headers(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("headers 必须是对象")
        return value


# ---------------------------------------------------------------------------
# test cases / suites
# ---------------------------------------------------------------------------
class APITestCaseSerializer(serializers.ModelSerializer):
    endpoint_name = serializers.CharField(source="endpoint.display_name", read_only=True,
                                          default="")
    module_name = serializers.CharField(source="module.name", read_only=True, default="")

    class Meta:
        model = APITestCase
        fields = (
            "id", "project", "endpoint", "endpoint_name", "module", "module_name", "name",
            "case_type", "test_type", "description", "request_config", "assertions",
            "extract", "hooks", "script_yaml", "source", "priority", "is_active",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "script_yaml", "created_at", "updated_at")

    def validate_request_config(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("request_config 必须是对象")
        return value

    def validate_assertions(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("assertions 必须是数组")
        for item in value:
            if not isinstance(item, dict) or not item.get("type"):
                raise serializers.ValidationError("每条断言必须包含 type")
        return value

    def validate_extract(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("extract 必须是对象")
        return value

    def validate_hooks(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("hooks 必须是对象")
        return value

    def validate(self, attrs):
        instance = self.instance
        project = attrs.get("project") or getattr(instance, "project", None)
        endpoint = attrs.get("endpoint", getattr(instance, "endpoint", None))
        module = attrs.get("module", getattr(instance, "module", None))
        if endpoint is not None and project is not None and endpoint.project_id != project.id:
            raise serializers.ValidationError({"endpoint": "端点不属于该项目"})
        if module is not None and project is not None and module.project_id != project.id:
            raise serializers.ValidationError({"module": "模块不属于该项目"})
        case_type = attrs.get("case_type") or getattr(instance, "case_type", "endpoint")
        if case_type == "scenario":
            config = attrs.get("request_config", getattr(instance, "request_config", {})) or {}
            steps = config.get("steps") if isinstance(config, dict) else None
            if not isinstance(steps, list) or not steps:
                raise serializers.ValidationError(
                    {"request_config": "场景用例需要 request_config.steps 列表"}
                )
        return attrs


class APITestSuiteSerializer(serializers.ModelSerializer):
    environment_name = serializers.CharField(source="environment.name", read_only=True,
                                             default="")
    case_count = serializers.SerializerMethodField()

    class Meta:
        model = APITestSuite
        fields = (
            "id", "project", "name", "description", "environment", "environment_name",
            "case_ids", "config", "source", "is_active", "case_count", "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "case_count", "created_at", "updated_at")

    def get_case_count(self, obj) -> int:
        return len(obj.ordered_case_ids()) if hasattr(obj, "ordered_case_ids") else len(
            obj.case_ids or []
        )

    def validate_case_ids(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("case_ids 必须是数组")
        cleaned = []
        for item in value:
            try:
                cleaned.append(int(item))
            except (TypeError, ValueError):
                raise serializers.ValidationError("case_ids 只能包含用例 ID")
        return cleaned

    def validate_config(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("config 必须是对象")
        return value

    def validate(self, attrs):
        instance = self.instance
        project = attrs.get("project") or getattr(instance, "project", None)
        case_ids = attrs.get("case_ids", getattr(instance, "case_ids", []))
        if case_ids and project is not None:
            existing = set(
                APITestCase.objects.filter(project=project, pk__in=case_ids)
                .values_list("pk", flat=True)
            )
            missing = [case_id for case_id in case_ids if case_id not in existing]
            if missing:
                raise serializers.ValidationError(
                    {"case_ids": f"以下用例不存在或不属于该项目: {missing}"}
                )
        environment = attrs.get("environment", getattr(instance, "environment", None))
        if environment is not None and project is not None and environment.project_id != project.id:
            raise serializers.ValidationError({"environment": "环境不属于该项目"})
        return attrs


# ---------------------------------------------------------------------------
# executions
# ---------------------------------------------------------------------------
class APITestCaseExecutionDetailSerializer(serializers.ModelSerializer):
    test_case_name = serializers.CharField(source="test_case.name", read_only=True,
                                           default="")

    class Meta:
        model = APITestCaseExecutionDetail
        fields = (
            "id", "execution", "test_case", "test_case_name", "case_name", "status",
            "duration_ms", "request", "response", "assertions", "error_message",
            "step_log", "order", "created_at",
        )
        read_only_fields = fields


class APITestCaseExecutionDetailNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = APITestCaseExecutionDetail
        fields = (
            "id", "test_case", "case_name", "status", "duration_ms", "request", "response",
            "assertions", "error_message", "step_log", "order", "created_at",
        )
        read_only_fields = fields


class APITestSuiteExecutionDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = APITestSuiteExecutionDetail
        fields = (
            "id", "execution", "suite", "suite_name", "status", "total", "passed", "failed",
            "duration_ms", "detail", "created_at",
        )
        read_only_fields = fields


class APITestExecutionSerializer(serializers.ModelSerializer):
    suite_name = serializers.CharField(source="suite.name", read_only=True, default="")
    environment_name = serializers.CharField(source="environment.name", read_only=True,
                                             default="")
    triggered_by_name = serializers.CharField(source="triggered_by.username", read_only=True,
                                              default="")

    class Meta:
        model = APITestExecution
        fields = (
            "id", "project", "suite", "suite_name", "name", "environment", "environment_name",
            "status", "trigger_type", "triggered_by", "triggered_by_name", "started_at",
            "finished_at", "duration_ms", "total", "passed", "failed", "skipped", "pass_rate",
            "report_path", "summary", "error_message", "created_at", "updated_at",
        )
        read_only_fields = fields


class APITestExecutionDetailSerializer(APITestExecutionSerializer):
    case_details = APITestCaseExecutionDetailNestedSerializer(many=True, read_only=True)
    suite_details = APITestSuiteExecutionDetailSerializer(many=True, read_only=True)

    class Meta(APITestExecutionSerializer.Meta):
        fields = APITestExecutionSerializer.Meta.fields + ("case_details", "suite_details")
        read_only_fields = fields
