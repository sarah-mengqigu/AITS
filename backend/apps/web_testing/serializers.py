"""DRF serializers for the Web UI 测试 module."""

from rest_framework import serializers

from apps.web_testing.models import (
    LOCATOR_TYPE_CHOICES,
    MidSceneScript,
    WebElement,
    WebPage,
    WebUITestCase,
    WebUITestCaseExecutionDetail,
    WebUITestExecution,
    WebUITestModule,
    WebUITestSuite,
)

LOCATOR_TYPE_VALUES = {choice[0] for choice in LOCATOR_TYPE_CHOICES}

STEP_ACTIONS = {
    "goto", "click", "fill", "assert_text", "wait", "press", "hover", "select",
    "check", "uncheck", "scroll", "screenshot", "keyboard", "upload", "assert_visible",
}


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


class WebUITestModuleSerializer(serializers.ModelSerializer):
    children_count = serializers.SerializerMethodField()
    case_count = serializers.IntegerField(read_only=True)
    parent_name = serializers.SerializerMethodField()

    class Meta:
        model = WebUITestModule
        fields = (
            "id", "project", "parent", "parent_name", "name", "description", "order",
            "case_count", "children_count", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "parent_name")

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


class WebUITestCaseSerializer(serializers.ModelSerializer):
    module_name = serializers.SerializerMethodField()
    step_count = serializers.IntegerField(read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = WebUITestCase
        fields = (
            "id", "project", "project_name", "module", "module_name", "name",
            "description", "case_type", "steps", "script", "script_type", "pom_refs",
            "assertions", "source", "priority", "is_active", "step_count",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "project_name",
                            "module_name", "step_count")

    def get_module_name(self, obj):
        return obj.module.name if obj.module_id else ""

    def validate_steps(self, value):
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("steps 必须是数组")
        for index, step in enumerate(value):
            if not isinstance(step, dict):
                raise serializers.ValidationError(f"第 {index + 1} 个步骤必须是对象")
            action = step.get("action")
            if not action:
                raise serializers.ValidationError(f"第 {index + 1} 个步骤缺少 action")
            if str(action) not in STEP_ACTIONS:
                raise serializers.ValidationError(
                    f"第 {index + 1} 个步骤 action 不支持: {action}"
                )
        return value

    def validate_pom_refs(self, value):
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("pom_refs 必须是数组")
        return value

    def validate_assertions(self, value):
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("assertions 必须是数组")
        return value

    def validate(self, attrs):
        project = attrs.get("project") or getattr(self.instance, "project", None)
        module = attrs.get("module", getattr(self.instance, "module", None))
        if module is not None and project is not None and module.project_id != project.id:
            raise serializers.ValidationError({"module": "模块必须属于同一项目"})
        return attrs


class WebUITestSuiteSerializer(serializers.ModelSerializer):
    case_count = serializers.IntegerField(read_only=True)
    environment_name = serializers.SerializerMethodField()
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = WebUITestSuite
        fields = (
            "id", "project", "project_name", "name", "description", "case_ids",
            "environment", "environment_name", "browser", "headless", "config",
            "is_active", "case_count", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "project_name",
                            "environment_name", "case_count")

    def get_environment_name(self, obj):
        return obj.environment.name if obj.environment_id else ""

    def validate_case_ids(self, value):
        ids = _normalize_id_list(value, "case_ids")
        project = self.initial_data.get("project") or getattr(
            self.instance, "project_id", None
        )
        if project and ids:
            valid = set(
                WebUITestCase.objects.filter(project_id=project, id__in=ids)
                .values_list("id", flat=True)
            )
            missing = [cid for cid in ids if cid not in valid]
            if missing:
                raise serializers.ValidationError(
                    f"以下用例不属于该项目: {missing}"
                )
        return ids

    def validate_config(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("config 必须是对象")
        return value


class WebUITestCaseExecutionDetailSerializer(serializers.ModelSerializer):
    test_case_name = serializers.CharField(source="test_case.name", read_only=True)

    class Meta:
        model = WebUITestCaseExecutionDetail
        fields = (
            "id", "execution", "test_case", "test_case_name", "case_name", "status",
            "duration_ms", "steps", "screenshots", "error_message", "step_log",
            "created_at",
        )
        read_only_fields = fields


class WebUITestExecutionSerializer(serializers.ModelSerializer):
    suite_name = serializers.SerializerMethodField()
    triggered_by_name = serializers.SerializerMethodField()
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = WebUITestExecution
        fields = (
            "id", "project", "project_name", "suite", "suite_name", "name", "status",
            "trigger_type", "triggered_by", "triggered_by_name", "browser",
            "started_at", "finished_at", "duration_ms", "total", "passed", "failed",
            "skipped", "pass_rate", "report_path", "allure_results_path", "summary",
            "error_message", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_suite_name(self, obj):
        return obj.suite.name if obj.suite_id else ""

    def get_triggered_by_name(self, obj):
        return obj.triggered_by.username if obj.triggered_by_id else ""


class WebUITestExecutionDetailSerializer(WebUITestExecutionSerializer):
    details = serializers.SerializerMethodField()

    class Meta(WebUITestExecutionSerializer.Meta):
        fields = WebUITestExecutionSerializer.Meta.fields + ("details",)
        read_only_fields = fields

    def get_details(self, obj):
        details = getattr(obj, "prefetched_details", None)
        if details is None:
            details = obj.details.all()
        return WebUITestCaseExecutionDetailSerializer(details, many=True).data


class WebPageSerializer(serializers.ModelSerializer):
    element_count = serializers.IntegerField(read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = WebPage
        fields = (
            "id", "project", "project_name", "name", "url", "description",
            "element_count", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "project_name",
                            "element_count")


class WebElementSerializer(serializers.ModelSerializer):
    page_name = serializers.CharField(source="page.name", read_only=True)
    project = serializers.IntegerField(source="page.project_id", read_only=True)
    locators = serializers.SerializerMethodField()

    class Meta:
        model = WebElement
        fields = (
            "id", "page", "page_name", "project", "name", "locator_type",
            "locator_value", "description", "alternatives", "locators",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "page_name", "project",
                            "locators")

    def get_locators(self, obj):
        return [{"locator_type": kind, "locator_value": value}
                for kind, value in obj.locators()]

    def validate_locator_type(self, value):
        if value not in LOCATOR_TYPE_VALUES:
            raise serializers.ValidationError(
                f"locator_type 仅支持 {sorted(LOCATOR_TYPE_VALUES)}"
            )
        return value

    def validate_locator_value(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("locator_value 不能为空")
        return value

    def validate_alternatives(self, value):
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("alternatives 必须是数组")
        cleaned = []
        for item in value:
            if isinstance(item, dict):
                kind = item.get("locator_type") or item.get("type")
                raw = item.get("locator_value") or item.get("value")
                if not kind or kind not in LOCATOR_TYPE_VALUES:
                    raise serializers.ValidationError(
                        f"备选定位的 locator_type 非法: {kind}"
                    )
                if not raw:
                    raise serializers.ValidationError("备选定位的 locator_value 不能为空")
                cleaned.append({"locator_type": kind, "locator_value": str(raw)})
            elif isinstance(item, str):
                cleaned.append({"locator_type": "css", "locator_value": item})
            else:
                raise serializers.ValidationError("备选定位必须是对象或字符串")
        return cleaned


class WebElementBulkItemSerializer(WebElementSerializer):
    """Bulk upsert item; ``page`` comes from the envelope, so it is optional.

    The model ``unique_together`` validator is disabled here - bulk upsert uses
    ``update_or_create`` and must accept items without an explicit ``page``.
    """

    page = serializers.IntegerField(required=False, allow_null=True)

    class Meta(WebElementSerializer.Meta):
        read_only_fields = WebElementSerializer.Meta.read_only_fields
        validators = []


class WebElementBulkSerializer(serializers.Serializer):
    """``POST /api/web-testing/elements/bulk/`` payload."""

    page = serializers.IntegerField()
    elements = WebElementBulkItemSerializer(many=True)

    def validate_page(self, value):
        page = WebPage.objects.filter(pk=value).first()
        if page is None:
            raise serializers.ValidationError("页面不存在")
        request = self.context.get("request")
        if request is not None:
            from apps.common.permissions import require_project_role

            require_project_role(request.user, page.project, "editor")
        self._page = page
        return value

    def validate(self, attrs):
        seen = set()
        for item in attrs.get("elements", []):
            name = item.get("name")
            if name in seen:
                raise serializers.ValidationError(f"数组内元素名称重复: {name}")
            seen.add(name)
        return attrs

    @property
    def page_instance(self):
        return getattr(self, "_page", None)


class MidSceneScriptSerializer(serializers.ModelSerializer):
    case_name = serializers.SerializerMethodField()
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = MidSceneScript
        fields = (
            "id", "project", "project_name", "name", "description", "script_type",
            "content", "case", "case_name", "status", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "project_name",
                            "case_name")

    def get_case_name(self, obj):
        return obj.case.name if obj.case_id else ""

    def validate(self, attrs):
        project = attrs.get("project") or getattr(self.instance, "project", None)
        case = attrs.get("case", getattr(self.instance, "case", None))
        if case is not None and project is not None and case.project_id != project.id:
            raise serializers.ValidationError({"case": "关联用例必须属于同一项目"})
        return attrs


class ScriptGenerationResultSerializer(serializers.Serializer):
    """Response shape for ``cases/{id}/generate_script/``."""

    case = serializers.IntegerField(read_only=True)
    script_type = serializers.CharField(read_only=True)
    generated_by = serializers.CharField(read_only=True)
    script = serializers.CharField(read_only=True)
