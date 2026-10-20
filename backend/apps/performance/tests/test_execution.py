"""Execution orchestration tests - simulated mode only, no subprocess."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import PropertyMock, patch

from django.test import override_settings

from apps.common.api.api_exception_handler import BusinessError
from apps.performance.models import PerformanceExecution
from apps.performance.services.execution import (
    create_execution,
    execute_scenario,
    run_execution,
)
from apps.performance.services.runner import LocustRunner
from apps.performance.services.stats import parse_locust_csv
from apps.performance.tests.base import PerformanceFixture


class ExecutionServiceTests(PerformanceFixture):
    def test_simulated_execution_persists_stats_and_report(self):
        scenario = self.create_scenario(source_type="api_suite")
        config = self.create_config(users=10, spawn_rate=5, duration_seconds=30)

        execution_id = execute_scenario(
            scenario.id, config_id=config.id, trigger_type="api"
        )
        execution = PerformanceExecution.objects.get(pk=execution_id)

        self.assertEqual(execution.status, "passed")
        self.assertEqual(execution.trigger_type, "api")
        self.assertGreater(execution.total_requests, 0)
        self.assertGreater(execution.avg_tps, 0)
        self.assertGreater(execution.p95_response_time, 0)
        self.assertGreaterEqual(execution.p99_response_time, execution.p95_response_time)
        self.assertLessEqual(execution.error_rate, 0.01)
        self.assertIsNotNone(execution.started_at)
        self.assertIsNotNone(execution.finished_at)
        self.assertGreater(execution.duration_ms, 0)
        self.assertEqual(execution.summary.get("mode"), "simulated")
        self.assertIn("200", execution.status_code_dist)

        # CSV artifact exists and parses back to the stored totals.
        self.assertTrue(Path(execution.csv_path).is_file())
        parsed = parse_locust_csv(execution.csv_path)
        self.assertEqual(parsed["total_requests"], execution.total_requests)
        self.assertEqual(parsed["p95_response_time"], execution.p95_response_time)
        self.assertIn("200", parsed["status_code_dist"])

        # JSON + HTML reports exist and are complete.
        self.assertTrue(Path(execution.report_path).is_file())
        report = json.loads(Path(execution.report_path).read_text(encoding="utf-8"))
        self.assertEqual(report["execution"]["id"], execution.id)
        self.assertEqual(report["scenario"]["id"], scenario.id)
        self.assertEqual(report["plan"]["users"], 10)
        self.assertEqual(report["summary"]["total_requests"], execution.total_requests)
        self.assertTrue(report["samples"])
        self.assertTrue(Path(report["artifacts"]["history_csv"]).is_file())
        html_path = execution.summary.get("html_report_path")
        self.assertTrue(Path(html_path).is_file())
        self.assertIn("AITS 性能测试报告", Path(html_path).read_text(encoding="utf-8"))

    def test_error_rate_above_threshold_marks_failed(self):
        scenario = self.create_scenario(source_type="api_case")
        config = self.create_config(
            duration_seconds=20, config={"error_rate": 0.08}
        )

        execution_id = execute_scenario(scenario.id, config_id=config.id)
        execution = PerformanceExecution.objects.get(pk=execution_id)

        self.assertEqual(execution.status, "failed")
        self.assertGreater(execution.error_rate, 0.01)
        self.assertTrue(
            any(code.startswith("5") for code in execution.status_code_dist)
        )

    def test_low_error_rate_marks_passed(self):
        scenario = self.create_scenario(source_type="api_case")
        config = self.create_config(duration_seconds=20, config={"error_rate": 0.0})

        execution_id = execute_scenario(scenario.id, config_id=config.id)
        execution = PerformanceExecution.objects.get(pk=execution_id)

        self.assertEqual(execution.status, "passed")
        self.assertEqual(execution.error_rate, 0.0)
        self.assertEqual(execution.status_code_dist, {"200": execution.total_requests})

    def test_runner_exception_marks_error_and_never_stays_running(self):
        scenario = self.create_scenario(source_type="api_case")

        with patch(
            "apps.performance.services.execution.build_plan",
            side_effect=RuntimeError("plan builder exploded"),
        ):
            execution_id = execute_scenario(scenario.id)

        execution = PerformanceExecution.objects.get(pk=execution_id)
        self.assertEqual(execution.status, "error")
        self.assertIn("plan builder exploded", execution.error_message)
        self.assertIsNotNone(execution.finished_at)
        self.assertEqual(
            PerformanceExecution.objects.filter(status="running").count(), 0
        )

    def test_prometheus_sd_target_update_is_called(self):
        scenario = self.create_scenario(source_type="api_case")
        with patch(
            "apps.performance.services.execution.update_windows_exporter_target",
            return_value={"enabled": True, "targets": []},
        ) as mocked:
            execute_scenario(scenario.id)
        mocked.assert_called_once()

    def test_prometheus_sd_respects_disable_switch(self):
        scenario = self.create_scenario(source_type="api_case")
        with override_settings(PROMETHEUS_SD_AUTO_UPDATE=False), patch(
            "apps.performance.services.execution.update_windows_exporter_target",
            return_value={"enabled": True, "targets": []},
        ) as mocked:
            execution_id = execute_scenario(scenario.id)
        mocked.assert_not_called()
        self.assertEqual(
            PerformanceExecution.objects.get(pk=execution_id).status, "passed"
        )

    def test_locust_unavailable_degrades_to_error_record(self):
        scenario = self.create_scenario(source_type="api_case")
        with override_settings(AITS_EXECUTION_MODE="real"), patch.object(
            LocustRunner, "available", new_callable=PropertyMock
        ) as available:
            available.return_value = False
            execution_id = execute_scenario(scenario.id)

        execution = PerformanceExecution.objects.get(pk=execution_id)
        self.assertEqual(execution.status, "error")
        self.assertIn("locust", execution.error_message.lower())
        self.assertIsNotNone(execution.finished_at)

    def test_run_execution_is_idempotent_for_finished_records(self):
        scenario = self.create_scenario(source_type="api_case")
        execution = create_execution(scenario)
        execution.status = "cancelled"
        execution.save(update_fields=["status", "updated_at"])

        returned = run_execution(execution.id)

        execution.refresh_from_db()
        self.assertEqual(returned, execution.id)
        self.assertEqual(execution.status, "cancelled")
        self.assertIsNone(execution.started_at)

    def test_execute_scenario_missing_scenario_raises(self):
        with self.assertRaises(BusinessError) as ctx:
            execute_scenario(999999)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_execute_scenario_with_missing_config_raises(self):
        scenario = self.create_scenario(source_type="api_case")
        with self.assertRaises(BusinessError):
            execute_scenario(scenario.id, config_id=999999)

    def test_scenario_config_used_when_config_id_omitted(self):
        config = self.create_config(users=3, duration_seconds=10)
        scenario = self.create_scenario(source_type="api_case", config=config)

        execution_id = execute_scenario(scenario.id)
        execution = PerformanceExecution.objects.get(pk=execution_id)

        self.assertEqual(execution.config_id, config.id)
        self.assertEqual(execution.status, "passed")
        self.assertEqual(execution.summary.get("users"), 3)

    def test_simulated_runner_is_deterministic_and_bounded(self):
        scenario = self.create_scenario(source_type="api_case")
        config = self.create_config(users=20, spawn_rate=10, duration_seconds=60)

        first = PerformanceExecution.objects.get(
            pk=execute_scenario(scenario.id, config_id=config.id)
        )
        second = PerformanceExecution.objects.get(
            pk=execute_scenario(scenario.id, config_id=config.id)
        )

        self.assertEqual(first.total_requests, second.total_requests)
        self.assertEqual(first.avg_tps, second.avg_tps)
        self.assertEqual(first.p95_response_time, second.p95_response_time)
        self.assertEqual(first.status_code_dist, second.status_code_dist)

        report = json.loads(Path(second.report_path).read_text(encoding="utf-8"))
        self.assertGreater(len(report["samples"]), 0)
        self.assertLessEqual(len(report["samples"]), 60)
        self.assertEqual(report["plan"]["duration_seconds"], 60)
