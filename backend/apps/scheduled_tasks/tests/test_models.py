"""Model + django_celery_beat synchronisation tests."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.scheduled_tasks.models import (
    PERIODIC_TASK_NAME_TEMPLATE,
    SCHEDULED_TASK_ROUTE,
    ScheduledTask,
    TaskExecutionLog,
    normalize_suite_ids,
    periodic_task_name_for,
)
from apps.scheduled_tasks.tests.base import ScheduledTasksBaseTestCase


class ScheduledTaskModelTests(ScheduledTasksBaseTestCase):
    def test_create_task_creates_periodic_task(self):
        """Creating a task mirrors it into django_celery_beat."""
        task = self.create_task(cron_expression="*/15 * * * *")

        periodic = PeriodicTask.objects.get(
            name=PERIODIC_TASK_NAME_TEMPLATE.format(task_id=task.id)
        )
        self.assertEqual(periodic.name, periodic_task_name_for(task.id))
        self.assertEqual(periodic.name, task.periodic_task_name)
        self.assertEqual(periodic.task, SCHEDULED_TASK_ROUTE)
        self.assertEqual(periodic.args, f"[{task.id}]")
        self.assertTrue(periodic.enabled)
        self.assertIsNone(periodic.interval)
        self.assertIsNotNone(periodic.crontab_id)
        self.assertEqual(periodic.crontab.minute, "*/15")
        self.assertEqual(periodic.crontab.hour, "*")
        self.assertEqual(periodic.crontab.day_of_month, "*")
        self.assertEqual(periodic.crontab.month_of_year, "*")
        self.assertEqual(periodic.crontab.day_of_week, "*")
        self.assertEqual(str(periodic.crontab.timezone), "Asia/Shanghai")

    def test_create_task_computes_next_run_at(self):
        task = self.create_task(cron_expression="0 3 * * *")
        self.assertIsNotNone(task.next_run_at)
        self.assertGreater(task.next_run_at, timezone.now())
        self.assertIsNone(task.last_run_at)

    def test_update_cron_syncs_periodic_task_without_duplicates(self):
        task = self.create_task(cron_expression="0 3 * * *")
        name = periodic_task_name_for(task.id)

        with self.committed():
            task.cron_expression = "30 4 * * 1-5"
            task.save()

        periodic = PeriodicTask.objects.get(name=name)
        self.assertEqual(PeriodicTask.objects.filter(name=name).count(), 1)
        self.assertEqual(periodic.crontab.minute, "30")
        self.assertEqual(periodic.crontab.hour, "4")
        self.assertEqual(periodic.crontab.day_of_week, "1-5")
        self.assertEqual(periodic.args, f"[{task.id}]")
        self.assertEqual(CrontabSchedule.objects.count(), 2)  # old + new, no dupes

    def test_disable_task_disables_periodic_task(self):
        task = self.create_task()
        name = periodic_task_name_for(task.id)
        self.assertTrue(PeriodicTask.objects.get(name=name).enabled)

        with self.committed():
            task.is_enabled = False
            task.save()

        self.assertFalse(PeriodicTask.objects.get(name=name).enabled)

        with self.committed():
            task.is_enabled = True
            task.save()
        self.assertTrue(PeriodicTask.objects.get(name=name).enabled)

    def test_delete_task_deletes_periodic_task(self):
        task = self.create_task()
        name = periodic_task_name_for(task.id)
        self.assertTrue(PeriodicTask.objects.filter(name=name).exists())

        with self.committed():
            task.delete()

        self.assertFalse(PeriodicTask.objects.filter(name=name).exists())

    def test_model_clean_rejects_invalid_cron_and_empty_suites(self):
        task = ScheduledTask(
            project=self.project,
            name="非法任务",
            suite_type="api",
            suite_ids=[],
            cron_expression="0 25 * * *",
        )
        with self.assertRaises(DjangoValidationError) as ctx:
            task.clean()
        self.assertIn("cron_expression", ctx.exception.message_dict)
        self.assertIn("suite_ids", ctx.exception.message_dict)

    def test_normalize_suite_ids(self):
        self.assertEqual(normalize_suite_ids([1, "2"]), [1, 2])
        self.assertEqual(normalize_suite_ids([{"id": 3}]), [3])
        for bad in ([], ["abc"], "1,2", None, [0]):
            with self.assertRaises(ValueError):
                normalize_suite_ids(bad)

    def test_invalid_cron_keeps_next_run_at_empty(self):
        task = ScheduledTask.objects.create(
            project=self.project,
            name="坏 cron",
            suite_type="api",
            suite_ids=[1],
            cron_expression="not a cron",
        )
        self.assertIsNone(task.next_run_at)


class TaskExecutionLogModelTests(ScheduledTasksBaseTestCase):
    def test_log_defaults_and_fields(self):
        task = self.create_task()
        log = TaskExecutionLog.objects.create(
            task=task, scheduled_task_name=task.name, suite_type=task.suite_type
        )
        self.assertEqual(log.status, "pending")
        self.assertFalse(log.is_terminal)
        self.assertEqual(log.report_urls, [])
        self.assertEqual(log.step_log, {})
        self.assertEqual(log.duration_ms, 0)
        self.assertEqual(task.logs.count(), 1)

        log.status = "passed"
        self.assertTrue(log.is_terminal)

    def test_log_is_cascaded_with_task(self):
        """``task`` is ``null=True`` but still ``on_delete=CASCADE`` (contract)."""
        task = self.create_task()
        log_id = TaskExecutionLog.objects.create(
            task=task, scheduled_task_name=task.name, suite_type=task.suite_type
        ).id
        with self.committed():
            task.delete()
        self.assertFalse(TaskExecutionLog.objects.filter(pk=log_id).exists())

    def test_log_keeps_task_name_snapshot(self):
        task = self.create_task()
        log = TaskExecutionLog.objects.create(
            task=task, scheduled_task_name=task.name, suite_type=task.suite_type
        )
        TaskExecutionLog.objects.filter(pk=log.pk).update(task=None)
        log.refresh_from_db()
        self.assertIsNone(log.task_id)
        self.assertEqual(log.scheduled_task_name, "每日冒烟")
