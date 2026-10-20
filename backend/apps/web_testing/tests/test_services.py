"""Service layer tests: script builder, runner, execution, generator."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from django.conf import settings

from apps.web_testing.models import (
    WebUITestCase,
    WebUITestExecution,
    WebUITestSuite,
)
from apps.web_testing.services import execution as execution_service
from apps.web_testing.services.generator import generate_steps_from_nl
from apps.web_testing.services.runner import (
    RealPlaywrightRunner,
    RunnerUnavailable,
    SimulatedRunner,
    evaluate_steps,
)
from apps.web_testing.services.script_builder import (
    generate_async_playwright_script,
    generate_midscene_script,
    generate_playwright_script,
)
from apps.web_testing.tests.base import WebTestingBaseTestCase, step


class ScriptBuilderTests(WebTestingBaseTestCase):
    def test_playwright_script_is_valid_python_and_uses_pom(self):
        page = self.create_page("登录页", "https://example.com/login")
        self.create_element(page, name="用户名输入框", locator_type="css",
                            locator_value="#username",
                            alternatives=[{"locator_type": "testid",
                                           "locator_value": "username"}])
        case = self.create_case(
            "登录脚本",
            steps=[
                step("goto", target="https://example.com/login"),
                step("fill", target="用户名输入框", value="admin"),
                step("click", target="登录按钮"),
                step("assert_text", target="body", value="欢迎"),
                step("wait", value=300),
            ],
            assertions=[{"type": "url", "value": "https://example.com/home"}],
            pom_refs=[page.id],
        )
        script = generate_playwright_script(case)
        compile(script, "<playwright>", "exec")
        self.assertIn("sync_playwright", script)
        self.assertIn("page.goto(", script)
        self.assertIn("to_contain_text", script)
        self.assertIn("to_have_url", script)
        self.assertIn("wait_for_timeout(300)", script)
        self.assertIn("def locate(page, key)", script)
        # POM element resolves through the page object model helper
        self.assertIn('locate(page, "用户名输入框")', script)
        self.assertIn("#username", script)

    def test_async_playwright_script_is_valid_python(self):
        case = self.create_case("异步脚本", steps=[step("goto", target="https://a.b")])
        script = generate_async_playwright_script(case)
        compile(script, "<playwright-async>", "exec")
        self.assertIn("async_playwright", script)
        self.assertIn("async def run", script)
        self.assertIn("asyncio.run", script)

    def test_midscene_script_yaml_structure(self):
        case = self.create_case(
            "MidScene 结构",
            steps=[
                step("goto", target="https://example.com/login"),
                step("fill", target="用户名", value="admin"),
                step("click", target="登录按钮"),
                step("assert_text", target="body", value="欢迎"),
                step("wait", value=500),
            ],
        )
        document = yaml.safe_load(generate_midscene_script(case))
        self.assertEqual(document["target"]["url"], "https://example.com/login")
        self.assertEqual(document["target"]["browser"], "chromium")
        flow = document["tasks"][0]["flow"]
        self.assertTrue(any("ai" in item for item in flow))
        self.assertTrue(any("aiAssert" in item for item in flow))
        self.assertTrue(any("aiWaitFor" in item for item in flow))


class RunnerTests(WebTestingBaseTestCase):
    def test_evaluate_steps_defaults_to_passed(self):
        status, log, error = evaluate_steps([
            {"action": "goto", "target": "https://example.com"},
            {"action": "click", "target": "#btn"},
        ])
        self.assertEqual(status, "passed")
        self.assertEqual(len(log), 2)
        self.assertEqual(error, "")

    def test_evaluate_steps_detects_expectation_mismatch(self):
        status, log, error = evaluate_steps([
            {"action": "assert_text", "value": "Hello", "expect": "Hello"},
            {"action": "assert_text", "value": "Hello", "expect": "Bye"},
        ])
        self.assertEqual(status, "failed")
        self.assertEqual(log[1]["status"], "failed")
        self.assertIn("Bye", error)

    def test_simulated_runner_writes_allure_results(self):
        self.create_case("占位")  # ensures project scoping is exercised
        plan = {
            "execution_id": 4242,
            "cases": [
                {"case_id": 1, "name": "用例 A", "steps": [{"action": "goto",
                                                            "target": "https://a"}]},
                {"case_id": 2, "name": "用例 B",
                 "steps": [{"action": "assert_text", "value": "x", "expect": "y"}]},
            ],
        }
        runner = SimulatedRunner(execution_id=4242)
        progress_calls = []
        report = runner.run(plan, on_progress=lambda percent, msg:
                            progress_calls.append((percent, msg)))

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["summary"]["total"], 2)
        self.assertEqual(report["summary"]["passed"], 1)
        self.assertEqual(report["summary"]["failed"], 1)
        self.assertEqual(report["summary"]["pass_rate"], 50.0)
        self.assertTrue(progress_calls)

        results_dir = Path(settings.ALLURE_RESULTS_ROOT) / "4242"
        files = sorted(results_dir.glob("*-result.json"))
        self.assertEqual(len(files), 2)
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        for field in ("name", "status", "stage", "start", "stop", "labels", "steps"):
            self.assertIn(field, payload)
        self.assertIn(payload["status"], {"passed", "failed", "broken", "skipped"})
        self.assertEqual(payload["stage"], "finished")

    def test_real_runner_reports_missing_playwright(self):
        runner = RealPlaywrightRunner(
            execution_id=1, availability_override=(False, "未安装 playwright 依赖")
        )
        with self.assertRaises(RunnerUnavailable) as ctx:
            runner.run({"cases": []})
        self.assertIn("Playwright", str(ctx.exception))


class ExecutionServiceTests(WebTestingBaseTestCase):
    def test_execute_suite_service_signature_and_result(self):
        ok_case = self.create_case("通过用例")
        failed_case = self.create_case(
            "失败用例", steps=[step("assert_text", value="a", expect="b")]
        )
        suite = self.create_suite("服务层套件", case_ids=[ok_case.id, failed_case.id])

        execution_id = execution_service.execute_suite(suite.id)
        self.assertIsInstance(execution_id, int)
        execution = WebUITestExecution.objects.get(pk=execution_id)
        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.total, 2)
        self.assertEqual(execution.passed, 1)
        self.assertEqual(execution.failed, 1)
        self.assertTrue(execution.summary.get("report_json"))

        report_json = Path(execution.summary["report_json"])
        self.assertTrue(report_json.exists())
        payload = json.loads(report_json.read_text(encoding="utf-8"))
        self.assertEqual(payload["summary"]["total"], 2)
        self.assertEqual(len(payload["cases"]), 2)

    def test_execute_case_service(self):
        case = self.create_case("单用例服务")
        execution_id = execution_service.execute_case(case.id)
        execution = WebUITestExecution.objects.get(pk=execution_id)
        self.assertEqual(execution.status, "passed")
        self.assertEqual(execution.total, 1)
        self.assertEqual(execution.summary["single_case"], True)
        self.assertEqual(execution.details.count(), 1)

    def test_execute_suite_missing_suite_raises(self):
        from apps.common.api.api_exception_handler import BusinessError

        with self.assertRaises(BusinessError) as ctx:
            execution_service.execute_suite(999999)
        self.assertEqual(ctx.exception.biz_code, "not_found")

    def test_run_execution_is_idempotent_for_finished_execution(self):
        suite = self.create_suite("幂等套件", case_ids=[self.create_case("幂等用例").id])
        execution_id = execution_service.execute_suite(suite.id)
        before = WebUITestExecution.objects.get(pk=execution_id)
        detail_count = before.details.count()

        again = execution_service.run_execution(execution_id)
        self.assertEqual(again, execution_id)
        after = WebUITestExecution.objects.get(pk=execution_id)
        self.assertEqual(after.status, before.status)
        self.assertEqual(after.details.count(), detail_count)

    def test_cancelled_execution_is_not_run(self):
        execution = WebUITestExecution.objects.create(
            project=self.project, name="已取消", status="cancelled",
            summary={"case_ids": []},
        )
        returned = execution_service.run_execution(execution.id)
        self.assertEqual(returned, execution.id)
        execution.refresh_from_db()
        self.assertEqual(execution.status, "cancelled")


class GeneratorTests(WebTestingBaseTestCase):
    def test_rule_based_generation(self):
        result = generate_steps_from_nl(
            "打开 https://example.com/login\n"
            "在用户名输入 admin\n"
            "点击登录按钮\n"
            "验证页面包含 欢迎"
        )
        self.assertEqual(result["generated_by"], "rule")
        actions = [item["action"] for item in result["steps"]]
        self.assertEqual(actions[0], "goto")
        self.assertIn("fill", actions)
        self.assertIn("click", actions)
        self.assertIn("assert_text", actions)
        self.assertTrue(result["name"])

    def test_empty_natural_language_raises(self):
        from apps.common.api.api_exception_handler import BusinessError

        with self.assertRaises(BusinessError) as ctx:
            generate_steps_from_nl("   ")
        self.assertEqual(ctx.exception.biz_code, "missing_natural_language")

    def test_generate_case_from_nl_can_persist(self):
        from apps.web_testing.services.generator import generate_case_from_nl

        result = generate_case_from_nl(
            "打开 https://example.com\n点击立即体验", self.project, name="NL 用例", save=True
        )
        self.assertIn("case_id", result)
        case = WebUITestCase.objects.get(pk=result["case_id"])
        self.assertEqual(case.name, "NL 用例")
        self.assertEqual(case.source, "ai")
        self.assertEqual(case.steps, result["steps"])
