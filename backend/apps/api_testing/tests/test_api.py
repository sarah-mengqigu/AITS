"""API level tests for ``/api/api-testing/`` routes."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from django.core.files.uploadedfile import SimpleUploadedFile

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
from apps.api_testing.tests.base import APITestFixture
from apps.api_testing.tests.samples import OPENAPI3_SPEC, POSTMAN_COLLECTION
from apps.projects.models import UploadedFile

SPECS_URL = "/api/api-testing/specs/"


class SpecImportTests(APITestFixture):
    def test_import_openapi_spec_json(self):
        resp = self.client.post(
            f"{SPECS_URL}import/",
            {
                "project": self.project.id,
                "content": json.dumps(OPENAPI3_SPEC, ensure_ascii=False),
                "name": "Pet API",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["endpoint_count"], 3)
        self.assertEqual(resp.data["spec"]["name"], "Pet API")
        self.assertEqual(resp.data["spec"]["source_type"], "openapi")
        self.assertEqual(resp.data["spec"]["base_url"], "https://api.example.com/v1")

        spec = APISpecification.objects.get(pk=resp.data["spec"]["id"])
        self.assertEqual(spec.endpoint_count, 3)
        self.assertEqual(APIEndpoint.objects.filter(spec=spec).count(), 3)
        self.assertTrue(APIModule.objects.filter(project=self.project, name="pets").exists())
        self.assertEqual(
            APIEndpoint.objects.get(spec=spec, method="get", path="/pets").module.name,
            "pets",
        )

    def test_import_spec_multipart_file(self):
        upload = SimpleUploadedFile(
            "openapi.json",
            json.dumps(OPENAPI3_SPEC).encode("utf-8"),
            content_type="application/json",
        )
        resp = self.client.post(
            f"{SPECS_URL}import/",
            {"project": self.project.id, "file": upload},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["endpoint_count"], 3)
        spec = APISpecification.objects.get(pk=resp.data["spec"]["id"])
        self.assertIsNotNone(spec.file_id)
        self.assertEqual(UploadedFile.objects.filter(project=self.project).count(), 1)

    def test_reparse_spec_rebuilds_endpoints(self):
        spec = self.create_spec(
            name="Reparse Spec",
            spec_data={"format": "openapi3", "raw": OPENAPI3_SPEC},
        )
        resp = self.client.post(f"{SPECS_URL}{spec.id}/reparse/")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["endpoint_count"], 3)
        spec.refresh_from_db()
        self.assertEqual(spec.endpoint_count, 3)
        self.assertEqual(spec.status, "parsed")
        self.assertEqual(APIEndpoint.objects.filter(spec=spec).count(), 3)

    def test_invalid_spec_returns_business_error_envelope(self):
        resp = self.client.post(
            f"{SPECS_URL}import/",
            {"project": self.project.id, "content": "not: [a: valid: spec"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.data)
        for key in ("code", "message", "errors", "status_code"):
            self.assertIn(key, resp.data)
        self.assertIn(resp.data["code"], {"invalid_spec", "unknown_spec"})
        self.assertEqual(APISpecification.objects.count(), 0)

    def test_spec_permissions(self):
        spec = self.create_spec()
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(SPECS_URL).status_code, 200)
        self.assertEqual(self.client.delete(f"{SPECS_URL}{spec.id}/").status_code, 403)

        self.client.force_authenticate(self.editor)
        self.assertEqual(self.client.delete(f"{SPECS_URL}{spec.id}/").status_code, 403)

        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.delete(f"{SPECS_URL}{spec.id}/").status_code, 204)


class ModuleAndEndpointTests(APITestFixture):
    def test_module_tree_nested(self):
        root = self.create_module("根模块", order=0)
        child = self.create_module("子模块", parent=root, order=1)
        sibling = self.create_module("另一个根", order=2)

        resp = self.client.get(
            "/api/api-testing/modules/tree/", {"project": self.project.id}
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["count"], 3)
        self.assertEqual(len(resp.data["tree"]), 2)
        root_node = next(node for node in resp.data["tree"] if node["id"] == root.id)
        self.assertEqual(len(root_node["children"]), 1)
        self.assertEqual(root_node["children"][0]["id"], child.id)
        self.assertEqual(root_node["children"][0]["full_path"], "根模块/子模块")
        self.assertIn(sibling.id, [node["id"] for node in resp.data["tree"]])

        # Other projects' modules are not leaked.
        other_project = self.project.__class__.objects.create(
            name="Other", project_type="api", owner=self.outsider
        )
        resp = self.client.get(
            "/api/api-testing/modules/tree/", {"project": other_project.id}
        )
        self.assertEqual(resp.status_code, 403)

        self.client.force_authenticate(self.viewer)
        resp = self.client.post(
            "/api/api-testing/modules/",
            {"project": self.project.id, "name": "viewer 模块"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.data)

    def test_endpoint_generate_cases(self):
        endpoint = self.create_endpoint(
            path="/pets",
            method="post",
            summary="创建宠物",
            parameters=[
                {"name": "traceId", "in": "query", "required": True, "example": "t-1"}
            ],
            request_body={
                "content_type": "application/json",
                "example": {"id": 1, "name": "tom"},
            },
            responses={"200": {}, "400": {}},
        )
        url = f"/api/api-testing/endpoints/{endpoint.id}/generate_cases/"
        resp = self.client.post(url, {}, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["created"], 4)
        self.assertEqual(len(resp.data["cases"]), 4)
        self.assertEqual(APITestCase.objects.filter(endpoint=endpoint).count(), 4)
        test_types = set(
            APITestCase.objects.filter(endpoint=endpoint).values_list(
                "test_type", flat=True
            )
        )
        self.assertEqual(test_types, {"positive", "negative", "boundary", "security"})
        self.assertTrue(
            all(case.endpoint_id == endpoint.id
                for case in APITestCase.objects.filter(endpoint=endpoint))
        )

        preview = self.client.get(url)
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data["count"], 4)
        self.assertTrue(preview.data["preview"])
        self.assertEqual(APITestCase.objects.filter(endpoint=endpoint).count(), 4)

    def test_endpoint_list_filters(self):
        get_endpoint = self.create_endpoint(path="/pets", method="get")
        post_endpoint = self.create_endpoint(path="/orders", method="post",
                                             summary="下单")
        resp = self.client.get(
            "/api/api-testing/endpoints/",
            {"project": self.project.id, "method": "GET"},
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], get_endpoint.id)

        resp = self.client.get(
            "/api/api-testing/endpoints/", {"search": "下单"}
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], post_endpoint.id)


class CaseTests(APITestFixture):
    def test_case_crud_and_generate_script(self):
        payload = {
            "project": self.project.id,
            "name": "新建用例",
            "case_type": "endpoint",
            "test_type": "positive",
            "request_config": {
                "method": "GET",
                "url": "/pets",
                "params": {"limit": 10},
                "headers": {"Accept": "application/json"},
            },
            "assertions": [
                {"type": "status_code", "expected": 200},
                {"type": "json_path", "path": "data.id", "expected": 1},
            ],
            "extract": {"token": "data.token"},
        }
        resp = self.client.post("/api/api-testing/cases/", payload, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        case_id = resp.data["id"]

        resp = self.client.get("/api/api-testing/cases/", {"project": self.project.id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)

        resp = self.client.patch(
            f"/api/api-testing/cases/{case_id}/", {"name": "重命名用例"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["name"], "重命名用例")

        resp = self.client.post(
            f"/api/api-testing/cases/{case_id}/generate_script/", {}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        document = yaml.safe_load(resp.data["script_yaml"])
        self.assertIn("config", document)
        self.assertIn("teststeps", document)
        self.assertEqual(document["teststeps"][0]["request"]["url"], "/pets")
        case = APITestCase.objects.get(pk=case_id)
        self.assertTrue(case.script_yaml.strip())

        self.client.force_authenticate(self.editor)
        self.assertEqual(
            self.client.delete(f"/api/api-testing/cases/{case_id}/").status_code, 403
        )
        self.client.force_authenticate(self.owner)
        self.assertEqual(
            self.client.delete(f"/api/api-testing/cases/{case_id}/").status_code, 204
        )
        self.assertEqual(APITestCase.objects.count(), 0)

    def test_viewer_can_read_but_not_write(self):
        case = self.create_case(name="只读用例")
        self.client.force_authenticate(self.viewer)
        resp = self.client.get("/api/api-testing/cases/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], case.id)

        resp = self.client.post(
            "/api/api-testing/cases/",
            {"project": self.project.id, "name": "viewer 用例"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.data)
        self.assertEqual(resp.data["code"], "permission_denied")

        resp = self.client.patch(
            f"/api/api-testing/cases/{case.id}/", {"name": "x"}, format="json"
        )
        self.assertEqual(resp.status_code, 403)

    def test_outsider_cannot_list_or_retrieve_cases(self):
        case = self.create_case(name="私有用例")
        self.client.force_authenticate(self.outsider)
        resp = self.client.get("/api/api-testing/cases/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 0)

        resp = self.client.get(f"/api/api-testing/cases/{case.id}/")
        self.assertEqual(resp.status_code, 404, resp.data)
        self.assertEqual(resp.data["code"], "not_found")

        resp = self.client.post(
            "/api/api-testing/cases/",
            {"project": self.project.id, "name": "越权用例"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


class ExecutionAPITests(APITestFixture):
    def _case(self, name):
        return self.create_case(
            name=name,
            assertions=[{"type": "status_code", "expected": 200}],
            request_config={
                "method": "GET",
                "url": "/pets",
                "mock_response": {"status_code": 200, "json": {"data": {"id": 1}}},
            },
        )

    def test_suite_run_and_execution_details(self):
        first = self._case("套件用例一")
        second = self._case("套件用例二")
        suite = self.create_suite([first, second])

        resp = self.client.post(f"/api/api-testing/suites/{suite.id}/run/", {}, format="json")
        self.assertEqual(resp.status_code, 202, resp.data)
        self.assertEqual(resp.data["status"], "pending")
        execution_id = int(resp.data["task_id"])
        self.assertEqual(resp.data["execution_id"], execution_id)

        execution = APITestExecution.objects.get(pk=execution_id)
        self.assertEqual(execution.status, "passed")
        self.assertEqual(execution.total, 2)
        self.assertEqual(execution.passed, 2)
        self.assertEqual(execution.failed, 0)
        self.assertEqual(execution.pass_rate, 100.0)
        self.assertEqual(execution.triggered_by_id, self.owner.id)
        self.assertEqual(APITestCaseExecutionDetail.objects.filter(
            execution=execution).count(), 2)
        self.assertEqual(APITestSuiteExecutionDetail.objects.filter(
            execution=execution).count(), 1)
        self.assertTrue(Path(execution.report_path).is_file())

        detail_resp = self.client.get(f"/api/api-testing/executions/{execution_id}/")
        self.assertEqual(detail_resp.status_code, 200, detail_resp.data)
        self.assertEqual(len(detail_resp.data["case_details"]), 2)
        self.assertEqual(len(detail_resp.data["suite_details"]), 1)
        self.assertEqual(detail_resp.data["status"], "passed")

        list_resp = self.client.get(
            "/api/api-testing/executions/", {"project": self.project.id}
        )
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(list_resp.data["count"], 1)

        report_resp = self.client.get(
            f"/api/api-testing/executions/{execution_id}/report/"
        )
        self.assertEqual(report_resp.status_code, 200, report_resp.data)
        self.assertEqual(report_resp.data["summary"]["total"], 2)
        self.assertEqual(len(report_resp.data["cases"]), 2)
        self.assertIn("execution", report_resp.data)

    def test_case_run_endpoint(self):
        case = self._case("单用例执行")
        resp = self.client.post(f"/api/api-testing/cases/{case.id}/run/", {}, format="json")
        self.assertEqual(resp.status_code, 202, resp.data)
        execution_id = int(resp.data["task_id"])
        execution = APITestExecution.objects.get(pk=execution_id)
        self.assertEqual(execution.status, "passed")
        self.assertEqual(execution.suite_id, None)
        self.assertEqual(execution.case_details.count(), 1)
        self.assertEqual(execution.case_details.first().test_case_id, case.id)

    def test_suite_run_permissions_and_empty_suite(self):
        suite = self.create_suite([self._case("权限用例")])
        self.client.force_authenticate(self.viewer)
        resp = self.client.post(f"/api/api-testing/suites/{suite.id}/run/", {}, format="json")
        self.assertEqual(resp.status_code, 403, resp.data)

        empty_suite = self.create_suite([], name="空套件")
        self.client.force_authenticate(self.owner)
        resp = self.client.post(
            f"/api/api-testing/suites/{empty_suite.id}/run/", {}, format="json"
        )
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(resp.data["code"], "empty_suite")
        for key in ("code", "message", "errors", "status_code"):
            self.assertIn(key, resp.data)

    def test_execution_cancel_and_inline_report(self):
        execution = APITestExecution.objects.create(
            project=self.project,
            name="待执行记录",
            status="pending",
            trigger_type="manual",
            triggered_by=self.owner,
        )
        resp = self.client.post(
            f"/api/api-testing/executions/{execution.id}/cancel/", {}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["status"], "cancelled")
        execution.refresh_from_db()
        self.assertEqual(execution.status, "cancelled")
        self.assertIsNotNone(execution.finished_at)

        resp = self.client.post(
            f"/api/api-testing/executions/{execution.id}/cancel/", {}, format="json"
        )
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(resp.data["code"], "execution_finished")

        report = self.client.get(f"/api/api-testing/executions/{execution.id}/report/")
        self.assertEqual(report.status_code, 200, report.data)
        self.assertTrue(report.data["artifacts"]["inline"])
        self.assertEqual(report.data["execution"]["id"], execution.id)


class IntegrationRoutesTests(APITestFixture):
    def test_error_envelope_for_missing_or_invalid_input(self):
        resp = self.client.post(f"{SPECS_URL}import/", {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "missing_project")
        self.assertIn("message", resp.data)
        self.assertEqual(resp.data["status_code"], 400)

        resp = self.client.post(
            f"{SPECS_URL}import/", {"project": self.project.id}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "missing_content")

        resp = self.client.post(
            "/api/api-testing/cases/",
            {
                "project": self.project.id,
                "name": "非法断言用例",
                "assertions": [{"expected": 1}],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "validation_error")
        self.assertIn("assertions", resp.data["errors"])

        resp = self.client.get("/api/api-testing/executions/999999/")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.data["code"], "not_found")

    def test_postman_import_api(self):
        resp = self.client.post(
            "/api/api-testing/postman/import/",
            {"project": self.project.id, "collection": POSTMAN_COLLECTION},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["endpoint_count"], 2)
        self.assertEqual(resp.data["case_count"], 2)
        spec = APISpecification.objects.get(pk=resp.data["spec"]["id"])
        self.assertEqual(spec.source_type, "postman")
        self.assertEqual(spec.base_url, "https://postman.example.com")
        self.assertEqual(APIEndpoint.objects.filter(spec=spec).count(), 2)

        cases = APITestCase.objects.filter(project=self.project, source="postman")
        self.assertEqual(cases.count(), 2)
        login_case = cases.get(name="Login")
        assertion_types = {item["type"] for item in login_case.assertions}
        self.assertIn("status_code", assertion_types)
        self.assertIn("json_path", assertion_types)
        self.assertEqual(login_case.request_config["method"], "POST")
        self.assertEqual(login_case.request_config["url"], "/api/login")

        module = APIModule.objects.get(project=self.project, name="Auth")
        self.assertEqual(APIEndpoint.objects.get(spec=spec, path="/api/login").module_id,
                         module.id)

    def test_ai_generate_scenario_endpoint(self):
        self.create_endpoint(path="/pets", method="get", summary="宠物列表")
        resp = self.client.post(
            "/api/api-testing/ai/generate_scenario/",
            {
                "project": self.project.id,
                "requirement": "请测试 /pets 接口的返回结果并校验状态码",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertGreaterEqual(resp.data["count"], 1)
        self.assertTrue(resp.data["saved"])
        self.assertTrue(resp.data["scenario"])

        case = APITestCase.objects.filter(
            project=self.project, case_type="scenario"
        ).first()
        self.assertIsNotNone(case)
        self.assertEqual(case.source, "ai")
        self.assertTrue(case.request_config["steps"])
        self.assertTrue(case.request_config["steps"][0]["request_config"]["url"])

        resp = self.client.post(
            "/api/api-testing/ai/generate_scenario/",
            {"project": self.project.id, "requirement": "   "},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "missing_requirement")
