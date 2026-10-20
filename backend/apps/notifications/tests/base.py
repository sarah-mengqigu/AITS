"""Shared fixtures for notifications tests."""

from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.notifications.models import (
    CHANNEL_CODES,
    EmailConfig,
    NotificationChannel,
    NotificationReceiver,
)
from apps.projects.models import Project, ProjectMember

User = get_user_model()


class FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, payload=None, status_code=200, text=""):
        self.payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class NotificationTestBase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@example.com", "Passw0rd!")
        self.admin = User.objects.create_user("admin", "admin@example.com", "Passw0rd!")
        self.editor = User.objects.create_user("editor", "editor@example.com", "Passw0rd!")
        self.viewer = User.objects.create_user("viewer", "viewer@example.com", "Passw0rd!")
        self.outsider = User.objects.create_user(
            "outsider", "outsider@example.com", "Passw0rd!"
        )
        self.staff = User.objects.create_user(
            "staff", "staff@example.com", "Passw0rd!", is_staff=True
        )
        self.project = Project.objects.create(
            name="演示项目", project_type="api", owner=self.owner
        )
        ProjectMember.objects.create(project=self.project, user=self.admin, role="admin")
        ProjectMember.objects.create(project=self.project, user=self.editor, role="editor")
        ProjectMember.objects.create(project=self.project, user=self.viewer, role="viewer")

        self.channels = {}
        for code in CHANNEL_CODES:
            channel, _ = NotificationChannel.objects.get_or_create(
                channel_code=code, defaults={"name": code}
            )
            self.channels[code] = channel

        self.dingtalk_receiver = NotificationReceiver.objects.create(
            project=self.project,
            name="钉钉-测试群",
            channel=self.channels["dingtalk"],
            webhook_url="https://example.com/dingtalk",
        )
        self.email_receiver = NotificationReceiver.objects.create(
            project=self.project,
            name="邮件-测试组",
            channel=self.channels["email"],
            target_address="qa@example.com,lead@example.com",
        )
        EmailConfig.objects.create(
            host="smtp.example.com",
            port=465,
            username="aits",
            password="secret",
            from_email="aits@example.com",
            is_active=True,
        )

    def task(self, trigger_condition="always", receiver_ids=None, name="每日回归"):
        return {
            "id": 42,
            "name": name,
            "project": self.project,
            "trigger_condition": trigger_condition,
            "notice_targets": (
                receiver_ids
                if receiver_ids is not None
                else [self.dingtalk_receiver.id]
            ),
        }

    def log(self, **overrides):
        data = {
            "id": 7,
            "status": "failed",
            "total": 10,
            "passed": 8,
            "failed": 2,
            "skipped": 0,
            "pass_rate": 80.0,
            "started_at": datetime(2026, 1, 2, 3, 4, 5),
            "report_urls": ["/reports/42.html"],
        }
        data.update(overrides)
        return data
