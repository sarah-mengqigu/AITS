"""``dispatch_task`` orchestration tests (all modules mocked / offline)."""

from __future__ import annotations

import importlib
from unittest import mock

from apps.api_testing.models import APITestExecution
from apps.scheduled_tasks.models import (
    STATUS_ERROR,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_PENDING,
    TaskExecutionLog,
)
from apps.scheduled_tasks.services import dispatcher
from apps.scheduled_tasks.tests.base import ScheduledTasksBaseTestCase


class DispatchApiSuiteTests(ScheduledTasksBaseTestCase):
    """api suites: ``execute_suite`` contract returns the execution id."""

    def _fake_api_executor(self, captured, total=5, passed=5, failed=0, skipped=0,
                          status="passed"):
        def fake_execute_suite(suite_id, environment_id=None, triggered_by=None,
                               trigger_type="manual"):
            captured["args"] = (suite_id, environment_id, triggered_by, trigger_type)
            execution = APITestExecution.objects.create(
                project=self.project,
                name="模拟 API 执行",
                status=status,
                trigger_type=trigger_type,
                triggered_by=triggered_by,
                total=total,
                passed=passed,
                failed=failed,
                skipped=skipped,
                pass_rate=round(passed / total * 100, 2) if total else 0.0,
            )
            return execution.id

        return fake_execute_suite

    def test_api_suite_returns_passed_log_with_stats(self):
        task = self.create_task(suite_type="api", suite_ids=[7])
        captured = {}

        with mock.patch(
            "apps.api_testing.services.execution.execute_suite",
            side_effect=self._fake_api_executor(captured),
        ) as patched:
            log_id = dispatcher.dispatch_task(
                task.id, triggered_by=self.editor, trigger_type="manual"
            )

        self.assertIsNotNone(log_id)
        log = TaskExecutionLog.objects.get(pk=log_id)
        self.assertEqual(log.status, STATUS_PASSED)
        self.assertEqual(log.task_id, task.id)
        self.assertEqual(log.scheduled_task_name, task.name)
        self.assertEqual(log.suite_type, "api")
        self.assertEqual((log.total, log.passed, log.failed, log.skipped), (5, 5, 0, 0))
        self.assertEqual(log.pass_rate, 100.0)
        self.assertIsNotNone(log.started_at)
        self.assertIsNotNone(log.finished_at)
        self.assertGreaterEqual(log.duration_ms, 0)
        self.assertEqual(log.triggered_by_id, self.editor.id)

        # executor called once with the documented positional contract
        self.assertEqual(patched.call_count, 1)
        suite_id, environment_id, triggered_by, trigger_type = captured["args"]
        self.assertEqual(suite_id, 7)
        self.assertEqual(environment_id, self.environment.id)
        self.assertEqual(triggered_by, self.editor)
        self.assertEqual(trigger_type, "manual")

        # per-suite results + report urls are persisted
        step = log.step_log["suites"][0]
        self.assertEqual(step["suite_id"], 7)
        self.assertEqual(step["status"], STATUS_PASSED)
        self.assertIsNotNone(step["execution_id"])
        self.assertEqual(log.report_urls[0]["suite_id"], 7)
        self.assertEqual(
            log.report_urls[0]["report_url"],
            f"/api/api-testing/executions/{step['execution_id']}/report/",
        )

        # timestamps are refreshed on the task
        task.refresh_from_db()
        self.assertIsNotNone(task.last_run_at)
        self.assertIsNotNone(task.next_run_at)

    def test_partial_failure_yields_failed_with_pass_rate(self):
        task = self.create_task(suite_type="api", suite_ids=[1, 2])
        results = [
            {"execution_id": 11, "status": "passed", "total": 5, "passed": 5},
            {"execution_id": 12, "status": "failed", "total": 5, "passed": 3, "failed": 2},
        ]
        with mock.patch(
            "apps.api_testing.services.execution.execute_suite", side_effect=results
        ):
            log_id = dispatcher.dispatch_task(task.id)

        log = TaskExecutionLog.objects.get(pk=log_id)
        self.assertEqual(log.status, STATUS_FAILED)
        self.assertEqual((log.total, log.passed, log.failed), (10, 8, 2))
        self.assertEqual(log.pass_rate, 80.0)
        self.assertTrue(log.error_message)
        self.assertEqual(len(log.step_log["suites"]), 2)

    def test_all_suites_error_yields_error_status(self):
        task = self.create_task(suite_type="api", suite_ids=[1])
        with mock.patch(
            "apps.api_testing.services.execution.execute_suite",
            side_effect=RuntimeError("执行器崩溃"),
        ):
            log_id = dispatcher.dispatch_task(task.id)  # must not raise

        log = TaskExecutionLog.objects.get(pk=log_id)
        self.assertEqual(log.status, STATUS_ERROR)
        self.assertIn("执行器崩溃", log.error_message)
        self.assertIn("RuntimeError", log.step_log["errors"][0])

    def test_missing_module_is_recorded_as_error_without_raising(self):
        task = self.create_task(suite_type="app", suite_ids=[5])
        real_import = importlib.import_module

        def fake_import(path, *args, **kwargs):
            if path.startswith("apps.app_testing"):
                raise ImportError(
                    "No module named 'apps.app_testing.services.execution'"
                )
            return real_import(path, *args, **kwargs)

        with mock.patch.object(dispatcher, "_import_module", side_effect=fake_import):
            log_id = dispatcher.dispatch_task(task.id)

        log = TaskExecutionLog.objects.get(pk=log_id)
        self.assertEqual(log.status, STATUS_ERROR)
        step = log.step_log["suites"][0]
        self.assertEqual(step["status"], STATUS_ERROR)
        self.assertIn("ImportError", step["error"])
        self.assertIn("app_testing", step["error"])
        self.assertEqual(log.total, 0)
        self.assertIn("ImportError", log.error_message)


class DispatchWebSuiteTests(ScheduledTasksBaseTestCase):
    """web suites: a dict result (simulated / degraded executor) is accepted."""

    def test_web_suite_returns_passed_log(self):
        task = self.create_task(suite_type="web", suite_ids=[3, 4])
        results = [
            {"execution_id": 21, "status": "passed", "total": 4, "passed": 4,
             "report_url": "/api/web-testing/executions/21/report/"},
            {"total": 2, "passed": 1, "failed": 1, "skipped": 0},
        ]

        with mock.patch(
            "apps.web_testing.services.execution.execute_suite", side_effect=results
        ) as patched:
            log_id = dispatcher.dispatch_task(task.id, trigger_type="scheduled")

        log = TaskExecutionLog.objects.get(pk=log_id)
        self.assertEqual(patched.call_count, 2)
        self.assertEqual(
            patched.call_args_list[0][0][:2], (3, self.environment.id)
        )
        self.assertEqual(log.suite_type, "web")
        self.assertEqual(log.status, STATUS_FAILED)  # one suite reported a failure
        self.assertEqual((log.total, log.passed, log.failed), (6, 5, 1))
        self.assertEqual(log.pass_rate, 83.33)
        self.assertEqual(log.step_log["suites"][0]["report_url"],
                         "/api/web-testing/executions/21/report/")

    def test_web_all_passed(self):
        task = self.create_task(suite_type="web", suite_ids=[3])
        with mock.patch(
            "apps.web_testing.services.execution.execute_suite",
            return_value={"total": 3, "passed": 3, "failed": 0},
        ):
            log_id = dispatcher.dispatch_task(task.id)

        log = TaskExecutionLog.objects.get(pk=log_id)
        self.assertEqual(log.status, STATUS_PASSED)
        self.assertEqual(log.pass_rate, 100.0)


class DispatchAppSuiteTests(ScheduledTasksBaseTestCase):
    """app suites: ``AppTestRun`` is the execution record to read stats from."""

    def test_app_suite_reads_stats_from_app_run(self):
        from apps.app_testing.models import AppTestRun

        task = self.create_task(suite_type="app", suite_ids=[2])

        def fake_execute_suite(suite_id, environment_id=None, triggered_by=None,
                               trigger_type="manual"):
            run = AppTestRun.objects.create(
                project=self.project,
                name="模拟 App 执行",
                status="failed",
                total=4,
                passed=3,
                failed=1,
                skipped=0,
                pass_rate=75.0,
                report_path="reports/app/2.json",
            )
            return run.id

        with mock.patch(
            "apps.app_testing.services.execution.execute_suite",
            side_effect=fake_execute_suite,
        ) as patched:
            log_id = dispatcher.dispatch_task(task.id)

        log = TaskExecutionLog.objects.get(pk=log_id)
        self.assertEqual(patched.call_count, 1)
        self.assertEqual(log.suite_type, "app")
        self.assertEqual(log.status, STATUS_FAILED)
        self.assertEqual((log.total, log.passed, log.failed), (4, 3, 1))
        self.assertEqual(log.pass_rate, 75.0)
        step = log.step_log["suites"][0]
        self.assertEqual(step["suite_type"], "app")
        self.assertEqual(step["execution_id"], log.report_urls[0]["execution_id"])


class DispatchNotificationTests(ScheduledTasksBaseTestCase):
    def _run_with_notifier(self, notifier):
        task = self.create_task(suite_type="api", suite_ids=[9])
        with mock.patch(
            "apps.api_testing.services.execution.execute_suite",
            return_value={"total": 3, "passed": 3, "failed": 0, "status": "passed"},
        ), mock.patch(
            "apps.notifications.services.trigger_notification", **notifier
        ) as patched:
            log_id = dispatcher.dispatch_task(task.id, triggered_by=self.editor)
        return task, log_id, patched

    def test_notification_receives_task_log_and_result(self):
        task, log_id, patched = self._run_with_notifier(
            {"return_value": {"sent": 2, "failed": 0}}
        )
        log = TaskExecutionLog.objects.get(pk=log_id)

        patched.assert_called_once()
        args, kwargs = patched.call_args
        self.assertEqual(args[0].pk, task.pk)
        self.assertEqual(kwargs["execution_log"].pk, log_id)
        self.assertEqual(kwargs["result"]["total"], 3)
        self.assertEqual(kwargs["result"]["passed"], 3)
        self.assertEqual(kwargs["result"]["status"], STATUS_PASSED)
        self.assertEqual(log.status, STATUS_PASSED)

        notification = log.step_log["notification"]
        self.assertEqual(notification["sent"], 2)
        self.assertEqual(notification["failed"], 0)
        self.assertNotIn("error", notification)

    def test_notification_failure_keeps_task_status(self):
        task, log_id, _patched = self._run_with_notifier(
            {"side_effect": RuntimeError("webhook 断网")}
        )
        log = TaskExecutionLog.objects.get(pk=log_id)
        self.assertEqual(log.status, STATUS_PASSED)
        self.assertEqual(log.passed, 3)
        notification = log.step_log["notification"]
        self.assertEqual(notification["failed"], 1)
        self.assertIn("webhook 断网", notification["error"])


class DispatchLogLifecycleTests(ScheduledTasksBaseTestCase):
    def test_unknown_task_returns_none(self):
        self.assertIsNone(dispatcher.dispatch_task(999999))

    def test_existing_pending_log_is_reused(self):
        """The ``run`` API pre-creates the pending log so its id stays stable."""
        task = self.create_task(suite_type="api", suite_ids=[1])
        log = TaskExecutionLog.objects.create(
            task=task,
            scheduled_task_name=task.name,
            suite_type=task.suite_type,
            status=STATUS_PENDING,
            triggered_by=self.viewer,
        )
        with mock.patch(
            "apps.api_testing.services.execution.execute_suite",
            return_value={"total": 1, "passed": 1, "failed": 0},
        ):
            log_id = dispatcher.dispatch_task(task.id, execution_log_id=log.id)

        self.assertEqual(log_id, log.id)
        self.assertEqual(TaskExecutionLog.objects.filter(task=task).count(), 1)
        log.refresh_from_db()
        self.assertEqual(log.status, STATUS_PASSED)
        self.assertEqual(log.triggered_by_id, self.viewer.id)

    def test_empty_suite_ids_yields_error(self):
        task = self.create_task(suite_type="api", suite_ids=[])
        log_id = dispatcher.dispatch_task(task.id)
        log = TaskExecutionLog.objects.get(pk=log_id)
        self.assertEqual(log.status, STATUS_ERROR)
        self.assertIn("未配置", log.error_message)

    def test_load_execution_stats_reads_the_execution_row(self):
        execution = APITestExecution.objects.create(
            project=self.project, name="直接构造", status="failed",
            total=10, passed=8, failed=2, skipped=0, pass_rate=80.0,
        )
        stats = dispatcher.load_execution_stats("api", execution.id)
        self.assertEqual(stats["status"], "failed")
        self.assertEqual((stats["total"], stats["passed"], stats["failed"]), (10, 8, 2))
        self.assertEqual(stats["pass_rate"], 80.0)
        self.assertIsNone(dispatcher.load_execution_stats("api", 999999))
