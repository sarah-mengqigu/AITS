"""API tests for the 通知中心 module."""

from unittest.mock import patch

from rest_framework.test import APIClient

from apps.common.api.api_exception_handler import BusinessError
from apps.notifications import services
from apps.notifications.models import (
    EmailConfig,
    NotificationLog,
    NotificationReceiver,
)
from apps.notifications.tests.base import NotificationTestBase
from apps.projects.models import Project


class NotificationApiTests(NotificationTestBase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def auth(self, user):
        self.client.force_authenticate(user)

    # -- channels -----------------------------------------------------------
    def test_channels_require_authentication(self):
        response = self.client.get("/api/notifications/channels/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "unauthorized")

    def test_channels_list_and_detail_are_readable(self):
        self.auth(self.viewer)
        response = self.client.get("/api/notifications/channels/")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 5)
        codes = {item["channel_code"] for item in response.data["results"]}
        self.assertTrue({"dingtalk", "wechat_work", "feishu", "email", "webhook"} <= codes)

        detail = self.client.get(
            f"/api/notifications/channels/{self.channels['dingtalk'].id}/"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["channel_code"], "dingtalk")

    def test_channel_write_requires_staff(self):
        url = f"/api/notifications/channels/{self.channels['dingtalk'].id}/"
        self.auth(self.owner)
        denied = self.client.patch(url, {"description": "x"}, format="json")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.data["code"], "permission_denied")

        self.auth(self.staff)
        allowed = self.client.patch(url, {"description": "更新后的说明"}, format="json")
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.data["description"], "更新后的说明")

    # -- receivers ----------------------------------------------------------
    def _receiver_payload(self, name="新增接收人", **overrides):
        payload = {
            "project": self.project.id,
            "name": name,
            "channel": self.channels["dingtalk"].id,
            "webhook_url": "https://example.com/new-receiver",
        }
        payload.update(overrides)
        return payload

    def test_receiver_create_requires_project_admin(self):
        self.auth(self.editor)
        denied = self.client.post(
            "/api/notifications/receivers/", self._receiver_payload(), format="json"
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.data["code"], "permission_denied")

        self.auth(self.admin)
        created = self.client.post(
            "/api/notifications/receivers/", self._receiver_payload(), format="json"
        )
        self.assertEqual(created.status_code, 201, created.data)
        receiver_id = created.data["id"]
        self.assertEqual(created.data["channel_code"], "dingtalk")
        self.assertEqual(created.data["project"], self.project.id)

        # viewer 可读不可写
        self.auth(self.viewer)
        listed = self.client.get("/api/notifications/receivers/")
        self.assertEqual(listed.status_code, 200)
        detail_url = f"/api/notifications/receivers/{receiver_id}/"
        self.assertEqual(self.client.get(detail_url).status_code, 200)
        denied_update = self.client.patch(detail_url, {"name": "改名"}, format="json")
        self.assertEqual(denied_update.status_code, 403)

        self.auth(self.admin)
        updated = self.client.patch(detail_url, {"name": "改名成功"}, format="json")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["name"], "改名成功")
        self.assertEqual(self.client.delete(detail_url).status_code, 204)

    def test_receiver_list_filters_and_project_scope(self):
        inactive = NotificationReceiver.objects.create(
            project=self.project,
            name="停用接收人",
            channel=self.channels["feishu"],
            webhook_url="https://example.com/inactive",
            is_active=False,
        )
        other_project = Project.objects.create(
            name="外部项目", project_type="api", owner=self.owner
        )
        NotificationReceiver.objects.create(
            project=other_project,
            name="外部接收人",
            channel=self.channels["feishu"],
            webhook_url="https://example.com/foreign",
        )
        self.auth(self.viewer)

        response = self.client.get(
            "/api/notifications/receivers/", {"project": self.project.id}
        )
        self.assertEqual(response.status_code, 200)
        # dingtalk + email (active) + inactive feishu
        self.assertEqual(response.data["count"], 3)

        response = self.client.get(
            "/api/notifications/receivers/", {"project": self.project.id, "is_active": "false"}
        )
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], inactive.id)

        response = self.client.get("/api/notifications/receivers/", {"is_active": "true"})
        names = {item["name"] for item in response.data["results"]}
        self.assertNotIn("外部接收人", names)

        self.auth(self.outsider)
        response = self.client.get("/api/notifications/receivers/")
        self.assertEqual(response.data["count"], 0)

    def test_global_receiver_write_requires_staff(self):
        payload = {
            "name": "全局通知群",
            "channel": self.channels["dingtalk"].id,
            "webhook_url": "https://example.com/global",
        }
        self.auth(self.owner)
        denied = self.client.post("/api/notifications/receivers/", payload, format="json")
        self.assertEqual(denied.status_code, 403)

        self.auth(self.staff)
        created = self.client.post("/api/notifications/receivers/", payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertIsNone(created.data["project"])
        # staff 列表可见全局接收对象（不在其项目范围内）
        listed = self.client.get("/api/notifications/receivers/")
        ids = {item["id"] for item in listed.data["results"]}
        self.assertIn(created.data["id"], ids)

    # -- email config -------------------------------------------------------
    def test_email_config_permissions_and_masked_password(self):
        self.auth(self.viewer)
        response = self.client.get("/api/notifications/email-config/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["host"], "smtp.example.com")
        self.assertEqual(response.data["password"], "******")
        self.assertEqual(response.data["port"], 465)

        self.auth(self.editor)
        denied = self.client.patch(
            "/api/notifications/email-config/", {"host": "evil.example.com"}, format="json"
        )
        self.assertEqual(denied.status_code, 403)

        self.auth(self.staff)
        updated = self.client.patch(
            "/api/notifications/email-config/",
            {"host": "smtp2.example.com", "port": 587},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["host"], "smtp2.example.com")
        self.assertEqual(updated.data["password"], "******")
        # 掩码回传不会覆盖真实密码
        self.assertEqual(EmailConfig.objects.get().password, "secret")
        masked = self.client.patch(
            "/api/notifications/email-config/", {"password": "******"}, format="json"
        )
        self.assertEqual(masked.status_code, 200)
        self.assertEqual(EmailConfig.objects.get().password, "secret")

        replaced = self.client.put(
            "/api/notifications/email-config/",
            {
                "host": "smtp3.example.com",
                "port": 465,
                "username": "aits",
                "password": "new-secret",
                "from_email": "noreply@example.com",
                "use_ssl": True,
                "use_tls": False,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(replaced.status_code, 200, replaced.data)
        config = EmailConfig.objects.get()
        self.assertEqual(config.host, "smtp3.example.com")
        self.assertEqual(config.password, "new-secret")
        self.assertEqual(config.from_email, "noreply@example.com")

    # -- test endpoint ------------------------------------------------------
    def test_test_endpoint_sends_and_writes_success_log(self):
        self.auth(self.viewer)
        denied = self.client.post(
            "/api/notifications/test/",
            {"receiver_id": self.dingtalk_receiver.id},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        self.auth(self.editor)
        with patch.object(
            services, "send_dingtalk", return_value={"channel": "dingtalk"}
        ) as send:
            response = self.client.post(
                "/api/notifications/test/",
                {"receiver_id": self.dingtalk_receiver.id, "title": "连通性测试"},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["sent"], 1)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], "https://example.com/dingtalk")
        log = NotificationLog.objects.get()
        self.assertEqual(log.receiver_id, self.dingtalk_receiver.id)
        self.assertEqual(log.channel_code, "dingtalk")
        self.assertEqual(log.status, "success")
        self.assertEqual(log.title, "连通性测试")
        self.assertIn("通知测试", log.content)

    def test_test_endpoint_uses_email_receiver_targets(self):
        self.auth(self.admin)
        with patch.object(
            services, "send_email", return_value={"channel": "email"}
        ) as send:
            response = self.client.post(
                "/api/notifications/test/",
                {"receiver_id": self.email_receiver.id},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["sent"], 1)
        send.assert_called_once()
        self.assertEqual(
            send.call_args.args[3], "qa@example.com,lead@example.com"
        )
        self.assertEqual(NotificationLog.objects.get().channel_code, "email")

    def test_test_endpoint_raw_channel_requires_staff(self):
        payload = {
            "channel_code": "webhook",
            "webhook_url": "https://example.com/hook",
        }
        self.auth(self.editor)
        denied = self.client.post("/api/notifications/test/", payload, format="json")
        self.assertEqual(denied.status_code, 403)

        self.auth(self.staff)
        with patch.object(
            services, "send_webhook", return_value={"channel": "webhook"}
        ) as send:
            response = self.client.post("/api/notifications/test/", payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["sent"], 1)
        send.assert_called_once()
        self.assertEqual(NotificationLog.objects.get().channel_code, "webhook")

    def test_test_endpoint_failure_writes_failed_log(self):
        self.auth(self.admin)
        with patch.object(
            services,
            "send_dingtalk",
            side_effect=BusinessError(message="token 无效", code="dingtalk_send_failed"),
        ):
            response = self.client.post(
                "/api/notifications/test/",
                {"receiver_id": self.dingtalk_receiver.id},
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "dingtalk_send_failed")
        log = NotificationLog.objects.get()
        self.assertEqual(log.status, "failed")
        self.assertIn("token 无效", log.error_message)

    # -- logs ---------------------------------------------------------------
    def test_logs_filtering_and_project_scope(self):
        own_success = NotificationLog.objects.create(
            project=self.project,
            receiver=self.dingtalk_receiver,
            channel_code="dingtalk",
            title="成功通知",
            content="md",
            status="success",
        )
        NotificationLog.objects.create(
            project=self.project,
            receiver=self.email_receiver,
            channel_code="email",
            title="失败通知",
            content="md",
            status="failed",
            error_message="smtp down",
        )
        other_project = Project.objects.create(
            name="外部项目", project_type="api", owner=self.outsider
        )
        NotificationLog.objects.create(
            project=other_project,
            channel_code="webhook",
            title="外部通知",
            content="md",
            status="failed",
        )

        self.auth(self.owner)
        listed = self.client.get("/api/notifications/logs/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["count"], 2)

        failed_only = self.client.get("/api/notifications/logs/", {"status": "failed"})
        self.assertEqual(failed_only.data["count"], 1)
        self.assertEqual(failed_only.data["results"][0]["channel_code"], "email")

        by_channel = self.client.get(
            "/api/notifications/logs/", {"channel_code": "dingtalk"}
        )
        self.assertEqual(by_channel.data["count"], 1)
        self.assertEqual(by_channel.data["results"][0]["id"], own_success.id)

        other_scope = self.client.get(
            "/api/notifications/logs/", {"project": other_project.id}
        )
        self.assertEqual(other_scope.data["count"], 0)

        detail = self.client.get(f"/api/notifications/logs/{own_success.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["receiver_name"], self.dingtalk_receiver.name)

        self.auth(self.outsider)
        self.assertEqual(
            self.client.get("/api/notifications/logs/").data["count"], 1
        )

    def test_logs_require_authentication(self):
        response = self.client.get("/api/notifications/logs/")
        self.assertEqual(response.status_code, 401)
