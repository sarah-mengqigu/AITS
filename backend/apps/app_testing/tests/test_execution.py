"""Execution orchestration tests (simulated determinism, error persistence)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import override_settings

from apps.app_testing.models import AppTestRun
from apps.app_testing.services import execution
from apps.app_testing.tests.base import AppTestingBaseTestCase
from apps.common.api.api_exception_handler import BusinessError


class ExecutionModeTests(AppTestingBaseTestCase):
    def test_execution_mode_falls_back_to_simulated_without_sonic(self):
        with override_settings(AITS_EXECUTION_MODE="real", SONIC_BASE_URL=""):
            self.assertEqual(execution.execution_mode(), "simulated")
        with override_settings(AITS_EXECUTION_MODE="simulated",
                               SONIC_BASE_URL="http://sonic.test"):
            self.assertEqual(execution.execution_mode(), "simulated")
        with override_settings(AITS_EXECUTION_MODE="real",
                               SONIC_BASE_URL="http://sonic.test"):
            self.assertEqual(execution.execution_mode(), "real")


class ExecuteSuiteTests(AppTestingBaseTestCase):
    def test_execute_suite_returns_run_id_and_full_record(self):
        first = self.create_case(name="登录成功")
        second = self.create_case(name="下单成功")
        suite = self.create_suite(case_ids=[first.id, second.id])

        run_id = execution.execute_suite(suite.id)
        self.assertIsInstance(run_id, int)
        run = AppTestRun.objects.get(pk=run_id)
        self.assertEqual(run.suite_id, suite.id)
        self.assertEqual(run.status, "passed")
        self.assertEqual((run.total, run.passed, run.failed, run.skipped), (2, 2, 0, 0))
        self.assertAlmostEqual(run.pass_rate, 100.0)
        self.assertEqual(run.summary["mode"], "simulated")
        self.assertEqual(len(run.summary["cases"]), 2)
        self.assertTrue(all(item["status"] == "passed" for item in run.summary["cases"]))
        self.assertIsNotNone(run.started_at)
        self.assertIsNotNone(run.finished_at)
        self.assertGreaterEqual(run.duration_ms, 1)

        report = json.loads(Path(run.report_path).read_text(encoding="utf-8"))
        self.assertEqual(report["run_id"], run.id)
        self.assertEqual(report["mode"], "simulated")
        self.assertEqual(report["summary"]["total"], 2)
        self.assertEqual(report["status"], "passed")

    def test_execute_suite_deterministic_failure(self):
        good = self.create_case(name="登录成功")
        bad = self.create_case(name="支付失败")
        suite = self.create_suite(case_ids=[good.id, bad.id])

        run_id = execution.execute_suite(suite.id)
        run = AppTestRun.objects.get(pk=run_id)
        self.assertEqual(run.status, "failed")
        self.assertEqual((run.passed, run.failed), (1, 1))
        self.assertAlmostEqual(run.pass_rate, 50.0)
        self.assertIn("断言失败", run.error_message)
        # same input -> same output
        second_run = AppTestRun.objects.get(pk=execution.execute_suite(suite.id))
        self.assertEqual(
            [item["status"] for item in second_run.summary["cases"]],
            [item["status"] for item in run.summary["cases"]],
        )

    def test_inactive_or_missing_cases_are_counted_as_skipped(self):
        active = self.create_case(name="登录成功")
        inactive = self.create_case(name="旧用例", is_active=False)
        suite = self.create_suite(case_ids=[active.id, inactive.id, 999999])

        run = AppTestRun.objects.get(pk=execution.execute_suite(suite.id))
        self.assertEqual(run.total, 1)
        self.assertEqual(run.skipped, 2)
        self.assertEqual(run.passed, 1)
        self.assertEqual(run.status, "passed")

    def test_execute_suite_missing_suite_raises_not_found(self):
        with self.assertRaises(BusinessError) as ctx:
            execution.execute_suite(999999)
        self.assertEqual(ctx.exception.biz_code, "not_found")

    def test_execute_suite_is_idempotent_for_terminal_runs(self):
        case = self.create_case(name="登录成功")
        suite = self.create_suite(case_ids=[case.id])
        run = execution.create_suite_run(suite)
        run.status = "passed"
        run.save(update_fields=["status"])
        self.assertEqual(execution.execute_run(run.id), run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, "passed")


class ExecuteCaseTests(AppTestingBaseTestCase):
    def test_execute_case_without_suite(self):
        case = self.create_case(name="登录成功")
        run_id = execution.execute_case(case.id)
        run = AppTestRun.objects.get(pk=run_id)
        self.assertIsNone(run.suite_id)
        self.assertEqual(run.total, 1)
        self.assertEqual(run.status, "passed")
        self.assertEqual(run.summary["case_ids"], [case.id])
        self.assertTrue(run.summary["single_case"])
        self.assertTrue(Path(run.report_path).exists())

    def test_execute_case_missing_case_raises_not_found(self):
        with self.assertRaises(BusinessError) as ctx:
            execution.execute_case(999999)
        self.assertEqual(ctx.exception.biz_code, "not_found")


class RealExecutionTests(AppTestingBaseTestCase):
    @override_settings(AITS_EXECUTION_MODE="real", SONIC_BASE_URL="http://sonic.test")
    def test_real_mode_maps_sonic_result(self):
        case = self.create_case(name="登录成功")
        suite = self.create_suite(case_ids=[case.id])
        client = MagicMock()
        client.run_suite.return_value = {"suiteId": "sonic-suite-1"}
        client.suite_result.return_value = {
            "status": "passed",
            "cases": [{"name": "登录成功", "status": "passed", "duration": 1200}],
        }
        with patch("apps.app_testing.services.execution.get_sonic_client",
                   return_value=client):
            run = AppTestRun.objects.get(pk=execution.execute_suite(suite.id))

        self.assertEqual(run.status, "passed")
        self.assertEqual(run.total, 1)
        self.assertEqual(run.summary["mode"], "real")
        self.assertEqual(run.summary["sonic_suite_id"], "sonic-suite-1")
        self.assertEqual(run.sonic_suite_id, "sonic-suite-1")
        client.run_suite.assert_called_once()

    @override_settings(AITS_EXECUTION_MODE="real", SONIC_BASE_URL="http://sonic.test")
    def test_real_mode_exception_is_persisted_as_error(self):
        case = self.create_case(name="登录成功")
        suite = self.create_suite(case_ids=[case.id])
        client = MagicMock()
        client.run_suite.side_effect = BusinessError(
            message="Sonic 服务不可用", code="sonic_unavailable", status_code=503
        )
        with patch("apps.app_testing.services.execution.get_sonic_client",
                   return_value=client):
            run_id = execution.execute_suite(suite.id)

        run = AppTestRun.objects.get(pk=run_id)
        self.assertEqual(run.status, "error")
        self.assertIn("Sonic 服务不可用", run.error_message)
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(run.summary["status"], "error")
        self.assertNotEqual(run.status, "running")
        report = json.loads(Path(run.report_path).read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "error")

    @override_settings(AITS_EXECUTION_MODE="simulated")
    def test_simulated_never_calls_sonic(self):
        case = self.create_case(name="登录成功")
        suite = self.create_suite(case_ids=[case.id])
        with patch("apps.app_testing.services.sonic_client.requests") as fake_requests:
            execution.execute_suite(suite.id)
        fake_requests.request.assert_not_called()
