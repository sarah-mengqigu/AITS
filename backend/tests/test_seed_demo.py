"""Guards the ``seed_demo`` management command (the out-of-box demo path)."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.api_testing.models import APITestCase, APITestExecution, APITestSuite
from apps.app_testing.models import AppTestCase, AppTestRun
from apps.performance.models import PerformanceExecution, PerformanceScenario
from apps.projects.models import Project
from apps.scheduled_tasks.models import ScheduledTask, TaskExecutionLog
from apps.web_testing.models import WebUITestCase, WebUITestExecution


class SeedDemoCommandTests(TestCase):
    def test_seed_creates_full_workspace(self):
        out = StringIO()
        call_command("seed_demo", stdout=out)
        output = out.getvalue()
        self.assertIn("AITS 演示数据已就绪", output)

        self.assertEqual(Project.objects.count(), 4)
        self.assertEqual(
            set(Project.objects.values_list("project_type", flat=True)),
            {"api", "web", "app", "perf"},
        )
        self.assertGreaterEqual(APITestCase.objects.count(), 4)
        self.assertTrue(APITestSuite.objects.exists())
        self.assertTrue(APITestExecution.objects.exists())
        self.assertTrue(WebUITestCase.objects.exists())
        self.assertTrue(WebUITestExecution.objects.exists())
        self.assertTrue(AppTestCase.objects.exists())
        self.assertTrue(AppTestRun.objects.exists())
        self.assertTrue(PerformanceScenario.objects.exists())
        self.assertTrue(PerformanceExecution.objects.exists())
        self.assertTrue(ScheduledTask.objects.exists())
        self.assertTrue(TaskExecutionLog.objects.exists())

        # every execution must be terminal
        for execution in APITestExecution.objects.all():
            self.assertNotEqual(execution.status, "running")
        for execution in WebUITestExecution.objects.all():
            self.assertNotEqual(execution.status, "running")
        for execution in PerformanceExecution.objects.all():
            self.assertNotEqual(execution.status, "running")

    def test_seed_is_idempotent(self):
        call_command("seed_demo", stdout=StringIO())
        project_count = Project.objects.count()
        case_count = APITestCase.objects.count()
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(Project.objects.count(), project_count)
        self.assertEqual(APITestCase.objects.count(), case_count)
