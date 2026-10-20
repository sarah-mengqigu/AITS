"""API tests for ``/api/scheduled-tasks/`` (tasks / logs / cron preview)."""

from __future__ import annotations

from unittest import mock

from django.utils import timezone
from django_celery_beat.models import PeriodicTask

from apps.scheduled_tasks.models import (
    STATUS_ERROR,
    STATUS_PASSED,
    ScheduledTask,
    TaskExecutionLog,
    periodic_task_name_for,
)
from apps.scheduled_tasks.tests.base import (
    CRON_PREVIEW_URL,
    LOGS_URL,
    TASKS_URL,
    ScheduledTasksBaseTestCase,
)


class ScheduledTaskCrudApiTests(ScheduledTasksBaseTestCase):
    def test_create_task_returns_201_and_syncs_beat(self):
        with self.committed():
            response = self.editor_client.post(
                TASKS_URL, self.task_payload(), format="json"
            )
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data
        self.assertEqual(data["name"], "每日冒烟")
        self.assertEqual(data["suite_count"], 2)
        self.assertEqual(data["created_by"], self.editor.id)
        self.assertIsNotNone(data["next_run_at"])
        self.assertEqual(
            data["periodic_task_name"], periodic_task_name_for(data["id"])
        )
        self.assertTrue(PeriodicTask.objects.filter(name=data["periodic_task_name"]).exists())

    def test_create_task_invalid_cron_returns_validation_error(self):
        with self.committed():
            response = self.editor_client.post(
                TASKS_URL,
                self.task_payload(cron_expression="0 25 * * *"),
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "validation_error")
        self.assertIn("cron_expression", response.data["errors"])
        self.assertFalse(ScheduledTask.objects.exists())

    def test_create_task_empty_suite_ids_returns_400(self):
        with self.committed():
            response = self.editor_client.post(
                TASKS_URL, self.task_payload(suite_ids=[]), format="json"
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "validation_error")
        self.assertIn("suite_ids", response.data["errors"])

    def test_create_task_suite_ids_must_be_integer_array(self):
        for bad in ("1,2", {"id": 1}, [{"name": "x"}], [0]):
            with self.committed():
                response = self.editor_client.post(
                    TASKS_URL, self.task_payload(suite_ids=bad), format="json"
                )
            self.assertEqual(response.status_code, 400, bad)
            self.assertIn("suite_ids", response.data["errors"])
        self.assertFalse(ScheduledTask.objects.exists())

    def test_create_task_environment_must_belong_to_project(self):
        with self.committed():
            response = self.editor_client.post(
                TASKS_URL,
                self.task_payload(environment=self.other_environment.id),
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("environment", response.data["errors"])

    def test_update_cron_via_api_resyncs_beat(self):
        task = self.create_task(cron_expression="0 3 * * *", created_by=self.editor)
        name = periodic_task_name_for(task.id)
        with self.committed():
            response = self.editor_client.patch(
                f"{TASKS_URL}{task.id}/",
                {"cron_expression": "45 6 * * *"},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.data)
        task.refresh_from_db()
        self.assertEqual(task.cron_expression, "45 6 * * *")
        periodic = PeriodicTask.objects.get(name=name)
        self.assertEqual(periodic.crontab.minute, "45")
        self.assertEqual(periodic.crontab.hour, "6")
        self.assertEqual(PeriodicTask.objects.filter(name=name).count(), 1)

    def test_list_is_scoped_to_accessible_projects(self):
        self.create_task()
        self.create_task(project=self.other_project, name="别人的任务",
                         environment=None, created_by=self.outsider)

        response = self.viewer_client.get(TASKS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "每日冒烟")

        outsider_response = self.outsider_client.get(TASKS_URL)
        self.assertEqual(outsider_response.data["count"], 1)
        self.assertEqual(outsider_response.data["results"][0]["name"], "别人的任务")

    def test_list_filters(self):
        self.create_task(name="api 任务", suite_type="api")
        self.create_task(name="web 任务", suite_type="web", is_enabled=False)

        self.assertEqual(
            self.owner_client.get(f"{TASKS_URL}?suite_type=web").data["count"], 1
        )
        self.assertEqual(
            self.owner_client.get(f"{TASKS_URL}?is_enabled=false").data["count"], 1
        )
        self.assertEqual(
            self.owner_client.get(f"{TASKS_URL}?search=api").data["count"], 1
        )
        self.assertEqual(
            self.owner_client.get(f"{TASKS_URL}?project={self.other_project.id}").data[
                "count"
            ],
            0,
        )

    def test_viewer_cannot_create_task(self):
        with self.committed():
            response = self.viewer_client.post(
                TASKS_URL, self.task_payload(), format="json"
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "permission_denied")
        self.assertFalse(ScheduledTask.objects.exists())

    def test_create_task_with_notice_targets(self):
        with self.committed():
            response = self.editor_client.post(
                TASKS_URL,
                self.task_payload(notice_targets=[self.receiver.id]),
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["notice_targets"], [self.receiver.id])
        self.assertEqual(response.data["notice_target_names"], ["值班群"])

    def test_notice_targets_must_belong_to_project(self):
        with self.committed():
            response = self.editor_client.post(
                TASKS_URL,
                self.task_payload(notice_targets=[self.other_receiver.id]),
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("notice_targets", response.data["errors"])
        self.assertFalse(ScheduledTask.objects.exists())

    def test_delete_requires_admin(self):
        task = self.create_task(created_by=self.editor)
        url = f"{TASKS_URL}{task.id}/"

        self.assertEqual(self.viewer_client.delete(url).status_code, 403)
        self.assertEqual(self.editor_client.delete(url).status_code, 403)

        with self.committed():
            response = self.admin_client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ScheduledTask.objects.filter(pk=task.id).exists())

    def test_anonymous_is_rejected(self):
        self.assertIn(self.anonymous_client.get(TASKS_URL).status_code, (401, 403))
        self.assertIn(self.anonymous_client.get(CRON_PREVIEW_URL).status_code, (401, 403))


class ScheduledTaskActionApiTests(ScheduledTasksBaseTestCase):
    def test_run_action_returns_202_with_log_id(self):
        task = self.create_task(suite_ids=[11])
        with mock.patch(
            "apps.api_testing.services.execution.execute_suite",
            return_value={"total": 4, "passed": 4, "failed": 0, "status": "passed"},
        ) as patched:
            response = self.editor_client.post(f"{TASKS_URL}{task.id}/run/")

        self.assertEqual(response.status_code, 202, response.data)
        self.assertIn("task_id", response.data)
        self.assertIn("log_id", response.data)
        self.assertEqual(response.data["task_id"], response.data["log_id"])
        # eager execution in tests -> the real, already finished status
        self.assertEqual(response.data["status"], STATUS_PASSED)
        self.assertEqual(response.data["execution_log"]["status"], STATUS_PASSED)
        self.assertEqual(patched.call_count, 1)

        log = TaskExecutionLog.objects.get(pk=response.data["log_id"])
        self.assertEqual(log.task_id, task.id)
        self.assertEqual(log.triggered_by_id, self.editor.id)
        self.assertIsNotNone(log.celery_task_id)

    def test_run_action_forbidden_for_viewer(self):
        task = self.create_task()
        response = self.viewer_client.post(f"{TASKS_URL}{task.id}/run/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "permission_denied")
        self.assertFalse(TaskExecutionLog.objects.exists())

    def test_run_action_records_error_when_suite_cannot_run(self):
        # suite id 1 does not exist in this project -> the app_testing executor
        # raises BusinessError, which the dispatcher must record (never 500).
        task = self.create_task(suite_type="app", suite_ids=[1])
        response = self.editor_client.post(f"{TASKS_URL}{task.id}/run/")
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(response.data["status"], STATUS_ERROR)
        log = TaskExecutionLog.objects.get(pk=response.data["log_id"])
        self.assertEqual(log.status, STATUS_ERROR)
        self.assertTrue(log.step_log["errors"])

    def test_toggle_action_flips_flag_and_beat(self):
        task = self.create_task()
        name = periodic_task_name_for(task.id)
        self.assertTrue(PeriodicTask.objects.get(name=name).enabled)

        with self.committed():
            response = self.editor_client.post(f"{TASKS_URL}{task.id}/toggle/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["is_enabled"])
        self.assertFalse(PeriodicTask.objects.get(name=name).enabled)

        with self.committed():
            response = self.editor_client.post(f"{TASKS_URL}{task.id}/toggle/")
        self.assertTrue(response.data["is_enabled"])
        self.assertTrue(PeriodicTask.objects.get(name=name).enabled)

    def test_task_logs_action_paginates(self):
        task = self.create_task()
        for index in range(3):
            TaskExecutionLog.objects.create(
                task=task,
                scheduled_task_name=task.name,
                suite_type="api",
                status="passed",
                total=index,
            )
        response = self.viewer_client.get(f"{TASKS_URL}{task.id}/logs/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 3)

    def test_logs_list_filters(self):
        first = self.create_task(name="任务一")
        second = self.create_task(name="任务二")
        TaskExecutionLog.objects.create(
            task=first, scheduled_task_name=first.name, suite_type="api", status="passed"
        )
        TaskExecutionLog.objects.create(
            task=second, scheduled_task_name=second.name, suite_type="web", status="failed"
        )

        all_logs = self.owner_client.get(LOGS_URL)
        self.assertEqual(all_logs.data["count"], 2)

        self.assertEqual(
            self.owner_client.get(f"{LOGS_URL}?status=passed").data["count"], 1
        )
        self.assertEqual(
            self.owner_client.get(f"{LOGS_URL}?suite_type=web").data["count"], 1
        )
        filtered = self.owner_client.get(f"{LOGS_URL}?task={first.id}")
        self.assertEqual(filtered.data["count"], 1)
        self.assertEqual(filtered.data["results"][0]["task"], first.id)

        outsourced = self.outsider_client.get(LOGS_URL)
        self.assertEqual(outsourced.data["count"], 0)

    def test_log_detail_includes_step_log(self):
        task = self.create_task()
        log = TaskExecutionLog.objects.create(
            task=task,
            scheduled_task_name=task.name,
            suite_type="api",
            status="passed",
            step_log={"suites": [{"suite_id": 1, "status": "passed"}]},
        )
        response = self.viewer_client.get(f"{LOGS_URL}{log.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["step_log"]["suites"][0]["suite_id"], 1)
        self.assertEqual(response.data["project_id"], self.project.id)


class CronPreviewApiTests(ScheduledTasksBaseTestCase):
    def test_cron_preview_valid(self):
        response = self.owner_client.get(f"{CRON_PREVIEW_URL}?expr=0 3 * * *")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["valid"])
        self.assertEqual(response.data["description"], "每天 03:00 执行")
        self.assertEqual(len(response.data["next_runs"]), 5)

    def test_cron_preview_invalid(self):
        response = self.owner_client.get(f"{CRON_PREVIEW_URL}?expr=bad")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["valid"])
        self.assertEqual(response.data["next_runs"], [])
        self.assertTrue(response.data["message"])

    def test_cron_preview_requires_expression(self):
        response = self.owner_client.get(CRON_PREVIEW_URL)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["valid"])

    def test_task_next_run_hint_matches_preview(self):
        """The task's stored ``next_run_at`` is consistent with the preview."""
        task = self.create_task(cron_expression="0 3 * * *")
        self.assertGreater(task.next_run_at, timezone.now())
        preview = self.owner_client.get(f"{CRON_PREVIEW_URL}?expr=0 3 * * *").data
        self.assertTrue(preview["next_runs"][0].endswith("03:00:00"))
