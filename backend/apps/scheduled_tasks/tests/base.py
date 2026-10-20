"""Shared fixtures for the 定时任务 (scheduled_tasks) test suite."""

from __future__ import annotations

from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.notifications.models import NotificationChannel, NotificationReceiver
from apps.projects.models import Environment, Project, ProjectMember
from apps.scheduled_tasks.models import ScheduledTask

User = get_user_model()

API = "/api/scheduled-tasks"
TASKS_URL = f"{API}/tasks/"
LOGS_URL = f"{API}/logs/"
CRON_PREVIEW_URL = f"{API}/cron/preview/"


class ScheduledTasksBaseTestCase(TestCase):
    """Users, one project (owner/admin/editor/viewer), env + a receiver."""

    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@x.com", "Passw0rd!")
        self.admin = User.objects.create_user("admin", "admin@x.com", "Passw0rd!")
        self.editor = User.objects.create_user("editor", "editor@x.com", "Passw0rd!")
        self.viewer = User.objects.create_user("viewer", "viewer@x.com", "Passw0rd!")
        self.outsider = User.objects.create_user("outsider", "outsider@x.com", "Passw0rd!")

        self.project = Project.objects.create(
            name="定时任务项目", project_type="api", owner=self.owner
        )
        ProjectMember.objects.create(project=self.project, user=self.admin, role="admin")
        ProjectMember.objects.create(project=self.project, user=self.editor, role="editor")
        ProjectMember.objects.create(project=self.project, user=self.viewer, role="viewer")

        self.environment = Environment.objects.create(
            project=self.project, name="测试环境", env_type="test",
            base_url="https://example.com", is_default=True,
        )
        self.other_project = Project.objects.create(
            name="其他项目", project_type="api", owner=self.outsider
        )
        self.other_environment = Environment.objects.create(
            project=self.other_project, name="其他环境"
        )

        self.dingtalk, _ = NotificationChannel.objects.get_or_create(
            channel_code="dingtalk", defaults={"name": "钉钉"}
        )
        self.receiver = NotificationReceiver.objects.create(
            project=self.project, name="值班群", channel=self.dingtalk,
            webhook_url="https://example.com/hook",
        )
        self.other_receiver = NotificationReceiver.objects.create(
            project=self.other_project, name="别人的群", channel=self.dingtalk,
            webhook_url="https://example.com/other",
        )

        self.owner_client = self._authenticated(self.owner)
        self.admin_client = self._authenticated(self.admin)
        self.editor_client = self._authenticated(self.editor)
        self.viewer_client = self._authenticated(self.viewer)
        self.outsider_client = self._authenticated(self.outsider)
        self.anonymous_client = APIClient()

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _authenticated(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    @contextmanager
    def committed(self):
        """Run ``transaction.on_commit`` callbacks (beat sync) inside a TestCase.

        ``TestCase`` wraps every test in a transaction that is rolled back, so
        Django defers (and then discards) ``on_commit`` hooks.  Wrapping the DB
        writes makes the deferred ``PeriodicTask`` sync observable.
        """
        with self.captureOnCommitCallbacks(execute=True):
            yield

    def task_payload(self, **overrides):
        payload = {
            "project": self.project.id,
            "name": "每日冒烟",
            "suite_type": "api",
            "suite_ids": [1, 2],
            "cron_expression": "0 3 * * *",
            "timezone": "Asia/Shanghai",
            "trigger_condition": "always",
            "is_enabled": True,
            "description": "",
        }
        payload.update(overrides)
        return payload

    def create_task(self, **overrides):
        """Create a task and execute the deferred beat sync."""
        payload = self.task_payload()
        data = {
            "project": self.project,
            "name": payload["name"],
            "suite_type": payload["suite_type"],
            "suite_ids": payload["suite_ids"],
            "cron_expression": payload["cron_expression"],
            "timezone": payload["timezone"],
            "trigger_condition": payload["trigger_condition"],
            "is_enabled": payload["is_enabled"],
            "description": payload["description"],
            "environment": self.environment,
            "created_by": self.owner,
        }
        data.update(overrides)
        with self.committed():
            return ScheduledTask.objects.create(**data)
