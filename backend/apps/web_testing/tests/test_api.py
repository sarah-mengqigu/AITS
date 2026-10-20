"""API tests for /api/web-testing/ (permissions, CRUD, execution, reports)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import yaml
from django.conf import settings

from apps.projects.models import Project
from apps.web_testing.models import (
    MidSceneScript,
    WebElement,
    WebPage,
    WebUITestCase,
    WebUITestExecution,
    WebUITestSuite,
)
from apps.web_testing.tests.base import API, WebTestingBaseTestCase, step


class ModuleAPITests(WebTestingBaseTestCase):
    def test_module_crud_and_tree(self):
        parent = self.create_module("登录模块", order=1)
        child = self.create_module("登录子模块", parent=parent, order=1)
        self.create_module("支付模块", order=2)

        resp = self.editor_client.get(f"{API}/modules/", {"project": self.project.id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 3)

        tree = self.editor_client.get(
            f"{API}/modules/tree/", {"project": self.project.id}
        )
        self.assertEqual(tree.status_code, 200)
        self.assertEqual(len(tree.data), 2)
        names = [node["name"] for node in tree.data]
        self.assertEqual(names, ["登录模块", "支付模块"])
        self.assertEqual(len(tree.data[0]["children"]), 1)
        self.assertEqual(tree.data[0]["children"][0]["name"], child.name)

        # forest (no ?project=) still yields the same nested structure
        forest = self.editor_client.get(f"{API}/modules/tree/")
        self.assertEqual(forest.status_code, 200)
        self.assertEqual(len(forest.data), 2)

    def test_module_create_requires_editor_and_delete_requires_admin(self):
        payload = {"project": self.project.id, "name": "只读不能建"}
        resp = self.viewer_client.post(f"{API}/modules/", payload, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "permission_denied")

        module = self.create_module("可删除模块")
        resp = self.editor_client.delete(f"{API}/modules/{module.id}/")
        self.assertEqual(resp.status_code, 403)

        resp = self.owner_client.delete(f"{API}/modules/{module.id}/")
        self.assertEqual(resp.status_code, 204)

    def test_module_read_permission_for_viewer_and_outsider(self):
        self.create_module("模块 A")
        resp = self.viewer_client.get(f"{API}/modules/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)

        resp = self.outsider_client.get(f"{API}/modules/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 0)


class CaseAPITests(WebTestingBaseTestCase):
    def test_case_crud(self):
        module = self.create_module("模块")
        payload = {
            "project": self.project.id,
            "module": module.id,
            "name": "登录成功",
            "description": "使用正确账号登录",
            "case_type": "ui",
            "steps": [
                step("goto", target="https://example.com/login"),
                step("fill", target="用户名", value="admin"),
                step("click", target="登录按钮"),
                step("assert_text", target="body", value="欢迎"),
            ],
            "assertions": [{"type": "url", "value": "https://example.com/home"}],
            "priority": "high",
        }
        resp = self.editor_client.post(f"{API}/cases/", payload, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        case_id = resp.data["id"]
        self.assertEqual(resp.data["step_count"], 4)
        self.assertEqual(resp.data["module_name"], "模块")

        resp = self.editor_client.patch(
            f"{API}/cases/{case_id}/", {"name": "登录成功-改"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["name"], "登录成功-改")

        resp = self.editor_client.get(f"{API}/cases/{case_id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["steps"]), 4)

        resp = self.owner_client.delete(f"{API}/cases/{case_id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(WebUITestCase.objects.filter(pk=case_id).exists())

    def test_case_create_validation_error_envelope(self):
        resp = self.editor_client.post(
            f"{API}/cases/",
            {"project": self.project.id, "name": "坏用例",
             "steps": [{"action": "teleport", "target": "x"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "validation_error")
        self.assertIn("message", resp.data)
        self.assertIn("errors", resp.data)

    def test_unauthorized_request_uses_error_envelope(self):
        resp = self.anonymous_client.get(f"{API}/cases/")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data["code"], "unauthorized")
        self.assertIn("message", resp.data)

    def test_generate_playwright_script_uses_pom(self):
        page = self.create_page("登录页", "https://example.com/login")
        self.create_element(page, name="登录按钮", locator_type="testid",
                            locator_value="login-btn")
        case = self.create_case(
            "POM 用例",
            steps=[
                step("goto", target="https://example.com/login"),
                step("click", target="登录按钮"),
            ],
            pom_refs=[page.id],
        )
        resp = self.editor_client.post(f"{API}/cases/{case.id}/generate_script/",
                                       {"script_type": "playwright"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        script = resp.data["script"]
        self.assertEqual(resp.data["generated_by"], "template")
        self.assertIn("sync_playwright", script)
        self.assertIn("POM_ELEMENTS", script)
        self.assertIn("get_by_test_id", script)
        self.assertIn("page.goto(", script)
        self.assertIn("locate(page", script)
        compile(script, "<generated-playwright>", "exec")  # must be valid python

        case.refresh_from_db()
        self.assertEqual(case.script, script)
        self.assertEqual(case.script_type, "playwright")

    def test_generate_midscene_script_yaml_structure(self):
        case = self.create_case(
            "MidScene 用例",
            steps=[
                step("goto", target="https://example.com/login"),
                step("fill", target="用户名", value="admin"),
                step("assert_text", target="body", value="欢迎"),
            ],
            assertions=["页面标题包含 首页"],
        )
        resp = self.editor_client.post(f"{API}/cases/{case.id}/generate_script/",
                                       {"script_type": "midscene"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        document = yaml.safe_load(resp.data["script"])
        self.assertIsInstance(document, dict)
        self.assertIn("target", document)
        self.assertEqual(document["target"]["url"], "https://example.com/login")
        tasks = document["tasks"]
        self.assertIsInstance(tasks, list)
        self.assertIn("flow", tasks[0])
        flow = tasks[0]["flow"]
        self.assertTrue(any("ai" in item for item in flow))
        self.assertTrue(any("aiAssert" in item for item in flow))
        case.refresh_from_db()
        self.assertEqual(case.script_type, "midscene")
        self.assertTrue(case.script.strip())

    def test_generate_from_nl_rule_fallback(self):
        case = self.create_case("待生成用例", steps=[])
        natural_language = (
            "打开 https://example.com/login\n"
            "在用户名输入 admin\n"
            "点击登录按钮\n"
            "验证页面包含 欢迎"
        )
        resp = self.editor_client.post(
            f"{API}/cases/{case.id}/generate_from_nl/",
            {"natural_language": natural_language},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["generated_by"], "rule")
        actions = [item["action"] for item in resp.data["steps"]]
        self.assertIn("goto", actions)
        self.assertIn("click", actions)
        self.assertIn("assert_text", actions)
        self.assertTrue(resp.data["applied"])
        case.refresh_from_db()
        self.assertEqual(case.steps, resp.data["steps"])

    def test_case_run_creates_execution_and_report(self):
        case = self.create_case("单用例执行")
        resp = self.editor_client.post(f"{API}/cases/{case.id}/run/")
        self.assertEqual(resp.status_code, 202, resp.data)
        self.assertIn("task_id", resp.data)
        self.assertEqual(resp.data["status"], "pending")

        execution = WebUITestExecution.objects.get(pk=resp.data["execution_id"])
        self.assertEqual(execution.status, "passed")
        self.assertEqual(execution.total, 1)
        self.assertEqual(execution.passed, 1)
        self.assertEqual(execution.details.count(), 1)
        self.assertGreaterEqual(execution.duration_ms, 1)
        self.assertTrue(execution.report_path)
        self.assertTrue(Path(execution.report_path).exists())
        self.assertIn("<html", Path(execution.report_path).read_text(encoding="utf-8"))


class SuiteExecutionAPITests(WebTestingBaseTestCase):
    def _make_suite(self):
        ok_case = self.create_case(
            "通过用例",
            steps=[step("goto", target="https://example.com"),
                   step("click", target="登录按钮")],
        )
        failed_case = self.create_case(
            "失败用例",
            steps=[step("assert_text", target="body", value="Welcome", expect="Bye")],
        )
        suite = self.create_suite("冒烟套件", case_ids=[ok_case.id, failed_case.id])
        return suite, ok_case, failed_case

    def test_suite_run_returns_202_and_statistics(self):
        suite, ok_case, failed_case = self._make_suite()
        resp = self.editor_client.post(f"{API}/suites/{suite.id}/run/")
        self.assertEqual(resp.status_code, 202, resp.data)
        self.assertIn("task_id", resp.data)
        self.assertEqual(resp.data["status"], "pending")

        execution = WebUITestExecution.objects.get(pk=resp.data["execution_id"])
        self.assertEqual(execution.suite_id, suite.id)
        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.total, 2)
        self.assertEqual(execution.passed, 1)
        self.assertEqual(execution.failed, 1)
        self.assertEqual(execution.pass_rate, 50.0)
        self.assertIsNotNone(execution.started_at)
        self.assertIsNotNone(execution.finished_at)
        self.assertEqual(execution.details.count(), 2)
        by_name = {detail.case_name: detail.status for detail in execution.details.all()}
        self.assertEqual(by_name["通过用例"], "passed")
        self.assertEqual(by_name["失败用例"], "failed")
        self.assertTrue(execution.allure_results_path)

    def test_allure_results_are_json_parseable(self):
        suite, _, _ = self._make_suite()
        resp = self.editor_client.post(f"{API}/suites/{suite.id}/run/")
        execution = WebUITestExecution.objects.get(pk=resp.data["execution_id"])
        results_dir = Path(settings.ALLURE_RESULTS_ROOT) / str(execution.id)
        self.assertTrue(results_dir.is_dir())
        files = sorted(results_dir.glob("*-result.json"))
        self.assertEqual(len(files), 2)
        statuses = set()
        for path in files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for field in ("name", "status", "stage", "start", "stop", "labels", "steps"):
                self.assertIn(field, payload)
            self.assertEqual(payload["stage"], "finished")
            self.assertIsInstance(payload["labels"], list)
            self.assertIsInstance(payload["steps"], list)
            statuses.add(payload["status"])
        self.assertEqual(statuses, {"passed", "failed"})

    def test_execution_list_and_detail_endpoints(self):
        suite, _, _ = self._make_suite()
        resp = self.editor_client.post(f"{API}/suites/{suite.id}/run/")
        execution_id = resp.data["execution_id"]

        listing = self.viewer_client.get(f"{API}/executions/",
                                         {"project": self.project.id})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(listing.data["results"][0]["id"], execution_id)

        detail = self.viewer_client.get(f"{API}/executions/{execution_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.data["details"]), 2)
        self.assertEqual(detail.data["suite_name"], suite.name)

    def test_report_endpoint_returns_artifacts(self):
        suite, _, _ = self._make_suite()
        resp = self.editor_client.post(f"{API}/suites/{suite.id}/run/")
        execution_id = resp.data["execution_id"]
        resp = self.viewer_client.get(f"{API}/executions/{execution_id}/report/")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["execution_id"], execution_id)
        self.assertTrue(resp.data["report_available"])
        self.assertIn("summary", resp.data)
        self.assertIsNotNone(resp.data["report"])
        self.assertEqual(resp.data["report"]["summary"]["total"], 2)
        self.assertEqual(len(resp.data["details"]), 2)

    def test_execution_failure_is_persisted_as_error(self):
        suite, _, _ = self._make_suite()
        with mock.patch(
            "apps.web_testing.services.runner.RealPlaywrightRunner.is_available",
            return_value=(False, "未安装 playwright 依赖"),
        ):
            with self.settings(AITS_EXECUTION_MODE="real"):
                resp = self.editor_client.post(f"{API}/suites/{suite.id}/run/")
        self.assertEqual(resp.status_code, 202, resp.data)
        execution = WebUITestExecution.objects.get(pk=resp.data["execution_id"])
        self.assertEqual(execution.status, "error")
        self.assertIn("Playwright", execution.error_message)
        self.assertIsNotNone(execution.finished_at)
        self.assertFalse(
            WebUITestExecution.objects.filter(status="running").exists()
        )

    def test_runner_exception_is_persisted_as_error(self):
        suite, _, _ = self._make_suite()
        with mock.patch(
            "apps.web_testing.services.runner.SimulatedRunner.run",
            side_effect=RuntimeError("模拟执行崩溃"),
        ):
            resp = self.editor_client.post(f"{API}/suites/{suite.id}/run/")
        self.assertEqual(resp.status_code, 202, resp.data)
        execution = WebUITestExecution.objects.get(pk=resp.data["execution_id"])
        self.assertEqual(execution.status, "error")
        self.assertIn("模拟执行崩溃", execution.error_message)
        self.assertFalse(
            WebUITestExecution.objects.filter(status="running").exists()
        )

    def test_cancel_execution(self):
        execution = WebUITestExecution.objects.create(
            project=self.project, name="待取消执行", status="pending",
            summary={"case_ids": []},
        )
        resp = self.viewer_client.post(f"{API}/executions/{execution.id}/cancel/")
        self.assertEqual(resp.status_code, 403)

        resp = self.editor_client.post(f"{API}/executions/{execution.id}/cancel/")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["status"], "cancelled")

        resp = self.editor_client.post(f"{API}/executions/{execution.id}/cancel/")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "invalid_status")

        report = self.viewer_client.get(f"{API}/executions/{execution.id}/report/")
        self.assertEqual(report.status_code, 200)
        self.assertFalse(report.data["report_available"])

    def test_suite_validates_case_ids_belong_to_project(self):
        other_project = Project.objects.create(
            name="另一个项目", project_type="web", owner=self.owner
        )
        foreign_case = WebUITestCase.objects.create(
            project=other_project, name="外部用例", steps=[]
        )
        resp = self.editor_client.post(
            f"{API}/suites/",
            {"project": self.project.id, "name": "非法套件",
             "case_ids": [foreign_case.id]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "validation_error")


class PomAPITests(WebTestingBaseTestCase):
    def test_page_and_element_crud_with_alternatives(self):
        resp = self.editor_client.post(
            f"{API}/pages/",
            {"project": self.project.id, "name": "登录页",
             "url": "https://example.com/login", "description": "登录页"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        page_id = resp.data["id"]

        resp = self.editor_client.post(
            f"{API}/elements/",
            {
                "page": page_id,
                "name": "用户名输入框",
                "locator_type": "css",
                "locator_value": "#username",
                "alternatives": [
                    {"locator_type": "xpath", "locator_value": "//input[@id='username']"},
                    {"locator_type": "text", "locator_value": "用户名"},
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(len(resp.data["alternatives"]), 2)
        self.assertEqual(len(resp.data["locators"]), 3)
        self.assertEqual(resp.data["locators"][0]["locator_type"], "css")

        elements = self.viewer_client.get(f"{API}/pages/{page_id}/elements/")
        self.assertEqual(elements.status_code, 200)
        self.assertEqual(len(elements.data), 1)
        self.assertEqual(elements.data[0]["name"], "用户名输入框")

        listing = self.viewer_client.get(f"{API}/elements/", {"page": page_id})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)

    def test_invalid_locator_type_is_rejected(self):
        page = self.create_page()
        resp = self.editor_client.post(
            f"{API}/elements/",
            {"page": page.id, "name": "非法定位", "locator_type": "regex",
             "locator_value": "^abc$"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "validation_error")

    def test_elements_bulk_upsert(self):
        page = self.create_page()
        payload = {
            "page": page.id,
            "elements": [
                {"name": "用户名", "locator_type": "testid", "locator_value": "user"},
                {"name": "密码", "locator_type": "css", "locator_value": "#pwd",
                 "alternatives": [{"locator_type": "id", "locator_value": "pwd"}]},
            ],
        }
        resp = self.editor_client.post(f"{API}/elements/bulk/", payload, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["created"], 2)
        self.assertEqual(resp.data["updated"], 0)

        payload["elements"][0]["locator_value"] = "user-v2"
        resp = self.editor_client.post(f"{API}/elements/bulk/", payload, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["created"], 0)
        self.assertEqual(resp.data["updated"], 2)
        self.assertEqual(WebElement.objects.filter(page=page).count(), 2)
        self.assertEqual(
            WebElement.objects.get(page=page, name="用户名").locator_value, "user-v2"
        )

    def test_elements_are_scoped_to_accessible_projects(self):
        mine = self.create_page("我的页面")
        self.create_element(mine)
        other_project = Project.objects.create(
            name="他人项目", project_type="web", owner=self.outsider
        )
        other_page = WebPage.objects.create(project=other_project, name="他人页面")
        self.create_element(other_page, name="他人元素")

        resp = self.editor_client.get(f"{API}/elements/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)

    def test_midscene_script_crud_and_generate(self):
        case = self.create_case(
            "MidScene 关联用例",
            steps=[step("goto", target="https://example.com/login"),
                   step("click", target="登录按钮")],
        )
        resp = self.editor_client.post(
            f"{API}/midscene-scripts/",
            {"project": self.project.id, "name": "登录 MidScene",
             "script_type": "yaml", "case": case.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        script_id = resp.data["id"]

        resp = self.editor_client.post(f"{API}/midscene-scripts/{script_id}/generate/")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["status"], "generated")
        document = yaml.safe_load(resp.data["content"])
        self.assertIn("tasks", document)
        self.assertEqual(document["target"]["url"], "https://example.com/login")
        script = MidSceneScript.objects.get(pk=script_id)
        self.assertTrue(script.content.strip())

    def test_midscene_generate_without_case_fails_cleanly(self):
        resp = self.editor_client.post(
            f"{API}/midscene-scripts/",
            {"project": self.project.id, "name": "空脚本", "script_type": "yaml"},
            format="json",
        )
        script_id = resp.data["id"]
        resp = self.editor_client.post(f"{API}/midscene-scripts/{script_id}/generate/")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "missing_case")


class SuiteCrudTests(WebTestingBaseTestCase):
    def test_suite_crud(self):
        case = self.create_case("套件用例")
        resp = self.editor_client.post(
            f"{API}/suites/",
            {"project": self.project.id, "name": "回归套件",
             "case_ids": [case.id], "browser": "firefox", "headless": False},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        suite_id = resp.data["id"]
        self.assertEqual(resp.data["case_count"], 1)
        self.assertEqual(resp.data["browser"], "firefox")
        self.assertFalse(resp.data["headless"])

        resp = self.editor_client.patch(
            f"{API}/suites/{suite_id}/", {"name": "回归套件-改"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["name"], "回归套件-改")

        self.assertTrue(WebUITestSuite.objects.filter(pk=suite_id).exists())
        resp = self.owner_client.delete(f"{API}/suites/{suite_id}/")
        self.assertEqual(resp.status_code, 204)
