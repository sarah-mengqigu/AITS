"""Service level execution tests (simulated runner, no network)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from apps.api_testing.models import APITestExecution
from apps.api_testing.services.execution import execute_case, execute_suite, run_execution
from apps.api_testing.tests.base import APITestFixture


class ExecutionServiceTests(APITestFixture):
    def test_execute_suite_statistics_details_and_report(self):
        passing = self.create_case(
            name="通过用例",
            assertions=[{"type": "status_code", "expected": 200}],
            request_config={
                "method": "GET",
                "url": "/pets",
                "mock_response": {"status_code": 200, "json": {"data": [1]}},
            },
        )
        failing = self.create_case(
            name="失败用例",
            assertions=[{"type": "status_code", "expected": 200}],
            request_config={
                "method": "GET",
                "url": "/pets",
                "mock_response": {"status_code": 500, "json": {"error": "boom"}},
            },
        )
        suite = self.create_suite([passing, failing])

        execution_id = execute_suite(suite.id)
        execution = APITestExecution.objects.get(pk=execution_id)
        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.total, 2)
        self.assertEqual(execution.passed, 1)
        self.assertEqual(execution.failed, 1)
        self.assertEqual(execution.skipped, 0)
        self.assertEqual(execution.pass_rate, 50.0)
        self.assertEqual(execution.project_id, self.project.id)
        self.assertEqual(execution.suite_id, suite.id)
        self.assertEqual(execution.environment_id, self.environment.id)
        self.assertIsNotNone(execution.started_at)
        self.assertIsNotNone(execution.finished_at)

        details = list(execution.case_details.order_by("order"))
        self.assertEqual(len(details), 2)
        self.assertEqual(details[0].case_name, "通过用例")
        self.assertEqual(details[0].status, "passed")
        self.assertEqual(details[1].status, "failed")
        self.assertTrue(details[1].error_message)
        self.assertEqual(details[0].test_case_id, passing.id)
        self.assertEqual(details[0].request["method"], "GET")

        self.assertEqual(execution.suite_details.count(), 1)
        suite_detail = execution.suite_details.first()
        self.assertEqual(suite_detail.suite_id, suite.id)
        self.assertEqual(suite_detail.total, 2)
        self.assertEqual(suite_detail.passed, 1)
        self.assertEqual(suite_detail.failed, 1)
        self.assertEqual(suite_detail.status, "failed")

        report_path = Path(execution.report_path)
        self.assertTrue(report_path.is_file())
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["summary"]["total"], 2)
        self.assertEqual(len(payload["cases"]), 2)
        self.assertEqual(payload["execution"]["id"], execution.id)
        self.assertEqual(payload["artifacts"]["mode"], "simulated")
        self.assertEqual(execution.summary["case_ids"], [passing.id, failing.id])

    def test_execute_suite_resolves_environment_variables(self):
        case = self.create_case(
            name="环境变量用例",
            assertions=[{"type": "status_code", "expected": 200}],
            request_config={
                "method": "GET",
                "url": "/pets",
                "headers": {"X-Stage": "${stage}"},
                "mock_response": {"status_code": 200, "json": {}},
            },
        )
        suite = self.create_suite([case])
        execution_id = execute_suite(suite.id, environment_id=self.environment.id)
        execution = APITestExecution.objects.get(pk=execution_id)
        self.assertEqual(execution.status, "passed")
        detail = execution.case_details.first()
        self.assertEqual(detail.request["headers"]["X-Stage"], "dev")

    def test_execute_case_creates_single_detail(self):
        case = self.create_case(
            name="单用例",
            assertions=[
                {"type": "status_code", "expected": 200},
                {"type": "json_path", "path": "data.id", "expected": 7},
            ],
            request_config={
                "method": "GET",
                "url": "/pets",
                "mock_response": {"status_code": 200, "json": {"data": {"id": 7}}},
            },
        )
        execution_id = execute_case(case.id)
        execution = APITestExecution.objects.get(pk=execution_id)
        self.assertEqual(execution.status, "passed")
        self.assertIsNone(execution.suite_id)
        self.assertEqual(execution.total, 1)
        self.assertEqual(execution.passed, 1)
        self.assertEqual(execution.pass_rate, 100.0)
        self.assertEqual(execution.case_details.count(), 1)
        detail = execution.case_details.first()
        self.assertEqual(detail.test_case_id, case.id)
        self.assertEqual(detail.status, "passed")
        self.assertEqual(execution.summary["test_case_id"], case.id)

    def test_execution_error_state_is_terminal(self):
        case = self.create_case(name="异常用例")
        suite = self.create_suite([case])

        class BoomRunner:
            mode = "simulated"

            def run(self, plan, on_progress=None):  # noqa: ANN001
                raise RuntimeError("runner exploded")

        with patch("apps.api_testing.services.execution.get_runner",
                   return_value=BoomRunner()):
            execution_id = execute_suite(suite.id)

        execution = APITestExecution.objects.get(pk=execution_id)
        self.assertEqual(execution.status, "error")
        self.assertIn("runner exploded", execution.error_message)
        self.assertIsNotNone(execution.finished_at)
        self.assertEqual(execution.case_details.count(), 0)

    def test_run_execution_is_idempotent_for_finished_records(self):
        case = self.create_case(name="重复执行")
        suite = self.create_suite([case])
        execution_id = execute_suite(suite.id)
        first = APITestExecution.objects.get(pk=execution_id)
        self.assertEqual(first.status, "passed")
        # Running the same record again resets details instead of duplicating them.
        run_execution(execution_id)
        second = APITestExecution.objects.get(pk=execution_id)
        self.assertEqual(second.status, "passed")
        self.assertEqual(second.case_details.count(), 1)
