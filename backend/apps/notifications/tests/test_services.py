"""Service layer tests for the 通知中心 module (no network access)."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.common.api.api_exception_handler import BusinessError
from apps.notifications import services
from apps.notifications.models import (
    EmailConfig,
    NotificationChannel,
    NotificationLog,
    NotificationReceiver,
)
from apps.notifications.tests.base import FakeResponse, NotificationTestBase
from apps.projects.models import Project


class ChannelSeedTests(TestCase):
    def test_five_builtin_channels_are_seeded_by_migration(self):
        codes = set(
            NotificationChannel.objects.values_list("channel_code", flat=True)
        )
        self.assertTrue(
            {"dingtalk", "wechat_work", "feishu", "email", "webhook"} <= codes
        )
        self.assertTrue(
            NotificationChannel.objects.filter(
                channel_code="dingtalk", is_active=True
            ).exists()
        )


class MarkdownTests(TestCase):
    @override_settings(SITE_URL="https://aits.example.com")
    def test_build_markdown_contains_task_stats_conclusion_time_and_link(self):
        markdown = services.build_markdown(
            task_name="每日回归",
            total=10,
            passed=8,
            failed=2,
            skipped=0,
            pass_rate=80,
            status="failed",
            started_at=datetime(2026, 1, 2, 3, 4, 5),
            report_url="/reports/42.html",
        )
        self.assertIn("## 定时任务执行结果", markdown)
        self.assertIn("**任务名称**: 每日回归", markdown)
        self.assertIn("**通过/失败/跳过/总计**: 8/2/0/10", markdown)
        self.assertIn("**成功率**: 80.0%", markdown)
        self.assertIn("**测试结论**: 测试未通过", markdown)
        self.assertIn("**开始时间**: 2026-01-02 03:04:05", markdown)
        self.assertIn(
            "**报告链接**: [查看报告](https://aits.example.com/reports/42.html)", markdown
        )

    def test_build_markdown_computes_pass_rate_and_pass_conclusion(self):
        markdown = services.build_markdown(
            task_name="冒烟", total=4, passed=4, failed=0, skipped=0
        )
        self.assertIn("**成功率**: 100.0%", markdown)
        self.assertIn("**测试结论**: 测试通过", markdown)

    def test_build_email_html_renders_html_tags(self):
        html = services.build_email_html(
            "## 定时任务执行结果\n"
            "**任务名称**: 每日回归\n"
            "**报告链接**: [查看报告](https://aits.example.com/reports/1.html)"
        )
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<html", html)
        self.assertIn("<h2>定时任务执行结果</h2>", html)
        self.assertIn("<strong>任务名称</strong>", html)
        self.assertIn(
            '<a href="https://aits.example.com/reports/1.html">查看报告</a>', html
        )
        self.assertIn("</body>", html)


class SenderTests(TestCase):
    def test_send_dingtalk_nonzero_errcode_raises_business_error(self):
        response = FakeResponse({"errcode": 310000, "errmsg": "invalid token"})
        with patch.object(services.requests, "post", return_value=response) as post:
            with self.assertRaises(BusinessError) as ctx:
                services.send_dingtalk("https://example.com/ding", "md", "标题")
        self.assertEqual(ctx.exception.biz_code, "dingtalk_send_failed")
        self.assertIn("invalid token", ctx.exception.message)
        self.assertEqual(post.call_args.kwargs["timeout"], 10)
        self.assertEqual(
            post.call_args.kwargs["json"]["msgtype"], "markdown"
        )

    def test_send_dingtalk_success(self):
        response = FakeResponse({"errcode": 0, "errmsg": "ok"})
        with patch.object(services.requests, "post", return_value=response) as post:
            result = services.send_dingtalk("https://example.com/ding", "md", "标题")
        self.assertEqual(result["channel"], "dingtalk")
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(
            post.call_args.kwargs["json"]["markdown"]["text"], "md"
        )

    def test_send_wecom_nonzero_errcode_raises_business_error(self):
        response = FakeResponse({"errcode": 93000, "errmsg": "invalid webhook url"})
        with patch.object(services.requests, "post", return_value=response):
            with self.assertRaises(BusinessError) as ctx:
                services.send_wecom("https://example.com/wecom", "md", "标题")
        self.assertEqual(ctx.exception.biz_code, "wecom_send_failed")

    def test_send_feishu_nonzero_code_raises_business_error(self):
        response = FakeResponse({"code": 19021, "msg": "sign match fail"})
        with patch.object(services.requests, "post", return_value=response):
            with self.assertRaises(BusinessError) as ctx:
                services.send_feishu("https://example.com/feishu", "md", "标题")
        self.assertEqual(ctx.exception.biz_code, "feishu_send_failed")

    def test_send_webhook_posts_json_payload(self):
        response = FakeResponse({"ok": True})
        payload = {"title": "t", "markdown": "md"}
        with patch.object(services.requests, "post", return_value=response) as post:
            result = services.send_webhook("https://example.com/hook", payload)
        self.assertEqual(result["channel"], "webhook")
        self.assertEqual(post.call_args.kwargs["json"], payload)
        self.assertEqual(post.call_args.kwargs["timeout"], 10)

    def test_send_webhook_http_error_raises_business_error(self):
        response = FakeResponse({"error": "oops"}, status_code=500)
        with patch.object(services.requests, "post", return_value=response):
            with self.assertRaises(BusinessError) as ctx:
                services.send_webhook("https://example.com/hook", {"a": 1})
        self.assertEqual(ctx.exception.biz_code, "notification_http_error")

    def test_send_email_builds_multipart_message_with_dynamic_smtp(self):
        message = MagicMock()
        message.send.return_value = 1
        config = EmailConfig(
            host="smtp.example.com",
            port=465,
            username="aits",
            password="secret",
            from_email="aits@example.com",
            use_ssl=True,
            use_tls=False,
        )
        markdown = "## 定时任务执行结果\n**任务名称**: 每日回归"
        with patch.object(
            services, "EmailMultiAlternatives", return_value=message
        ) as message_cls, patch.object(services, "get_connection") as get_connection:
            result = services.send_email(
                config, "执行结果", markdown, "qa@example.com; lead@example.com"
            )

        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["recipients"], ["qa@example.com", "lead@example.com"])
        message_cls.assert_called_once()
        self.assertEqual(
            message_cls.call_args.kwargs["to"], ["qa@example.com", "lead@example.com"]
        )
        html = message.attach_alternative.call_args.args[0]
        self.assertIn("<html", html)
        self.assertEqual(message.attach_alternative.call_args.args[1], "text/html")
        smtp_kwargs = get_connection.call_args.kwargs
        self.assertEqual(smtp_kwargs["host"], "smtp.example.com")
        self.assertEqual(smtp_kwargs["port"], 465)
        self.assertTrue(smtp_kwargs["use_ssl"])
        self.assertFalse(smtp_kwargs["use_tls"])
        self.assertEqual(smtp_kwargs["password"], "secret")

    def test_send_email_without_config_raises(self):
        with self.assertRaises(BusinessError) as ctx:
            services.send_email({"host": ""}, "标题", "md", "a@example.com")
        self.assertEqual(ctx.exception.biz_code, "email_not_configured")

    def test_send_email_without_targets_raises(self):
        with self.assertRaises(BusinessError) as ctx:
            services.send_email(
                {"host": "smtp.example.com", "from_email": "a@example.com"},
                "标题",
                "md",
                "",
            )
        self.assertEqual(ctx.exception.biz_code, "email_no_recipients")


class EmailConfigModelTests(TestCase):
    def test_only_one_active_config(self):
        first = EmailConfig.objects.create(host="smtp1.example.com", is_active=True)
        second = EmailConfig.objects.create(host="smtp2.example.com", is_active=True)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)
        self.assertEqual(EmailConfig.get_solo().pk, second.pk)


class TriggerNotificationTests(NotificationTestBase):
    def test_always_trigger_sends_to_every_channel(self):
        task = self.task(receiver_ids=[self.dingtalk_receiver.id, self.email_receiver.id])
        with patch.object(
            services, "send_dingtalk", return_value={"channel": "dingtalk"}
        ) as send_ding, patch.object(
            services, "send_email", return_value={"channel": "email"}
        ) as send_mail:
            result = services.trigger_notification(task, self.log())

        self.assertFalse(result["skipped"])
        self.assertEqual(result["sent"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(result["results"]), 2)
        send_ding.assert_called_once()
        send_mail.assert_called_once()
        # email receivers get the comma separated target list
        self.assertEqual(send_mail.call_args.args[3], "qa@example.com,lead@example.com")

        logs = NotificationLog.objects.filter(scheduled_task_id=42).order_by("id")
        self.assertEqual(logs.count(), 2)
        self.assertEqual({log.status for log in logs}, {"success"})
        self.assertEqual({log.channel_code for log in logs}, {"dingtalk", "email"})
        for log in logs:
            self.assertIn("每日回归", log.content)
            self.assertEqual(log.scheduled_task_name, "每日回归")
            self.assertEqual(log.task_execution_log_id, 7)

    def test_fail_condition_skips_when_all_passed(self):
        task = self.task(trigger_condition="fail")
        log = self.log(status="passed", total=10, passed=10, failed=0, pass_rate=100)
        with patch.object(services, "send_dingtalk") as send_ding:
            result = services.trigger_notification(task, log)
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "all_passed")
        self.assertEqual(result["sent"], 0)
        send_ding.assert_not_called()
        self.assertEqual(NotificationLog.objects.count(), 0)

    def test_fail_condition_sends_when_there_are_failures(self):
        task = self.task(trigger_condition="fail")
        with patch.object(
            services, "send_dingtalk", return_value={"channel": "dingtalk"}
        ) as send_ding:
            result = services.trigger_notification(task, self.log(status="failed"))
        self.assertFalse(result["skipped"])
        self.assertEqual(result["sent"], 1)
        send_ding.assert_called_once()
        self.assertEqual(NotificationLog.objects.get().status, "success")

    def test_no_targets_returns_zero_sent(self):
        task = self.task(receiver_ids=[])
        with patch.object(services, "send_dingtalk") as send_ding:
            result = services.trigger_notification(task, self.log())
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["reason"], "no_targets")
        send_ding.assert_not_called()
        self.assertEqual(NotificationLog.objects.count(), 0)

    def test_one_channel_failure_does_not_block_the_others(self):
        task = self.task(receiver_ids=[self.dingtalk_receiver.id, self.email_receiver.id])
        with patch.object(
            services,
            "send_dingtalk",
            side_effect=BusinessError(message="钉钉挂了", code="dingtalk_send_failed"),
        ), patch.object(
            services, "send_email", return_value={"channel": "email"}
        ) as send_mail:
            result = services.trigger_notification(task, self.log())

        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["failed"], 1)
        send_mail.assert_called_once()
        statuses = {item["channel_code"]: item["status"] for item in result["results"]}
        self.assertEqual(
            statuses, {"dingtalk": "failed", "email": "success"}
        )
        dingtalk_log = NotificationLog.objects.get(channel_code="dingtalk")
        email_log = NotificationLog.objects.get(channel_code="email")
        self.assertEqual(dingtalk_log.status, "failed")
        self.assertIn("钉钉挂了", dingtalk_log.error_message)
        self.assertEqual(email_log.status, "success")
        self.assertEqual(email_log.error_message, "")

    def test_channel_api_error_is_recorded_as_failed_log(self):
        task = self.task()
        response = FakeResponse({"errcode": 310000, "errmsg": "invalid token"})
        with patch.object(services.requests, "post", return_value=response):
            result = services.trigger_notification(task, self.log())
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["failed"], 1)
        log = NotificationLog.objects.get()
        self.assertEqual(log.status, "failed")
        self.assertIn("钉钉发送失败", log.error_message)

    def test_result_stats_override_execution_log(self):
        task = self.task(trigger_condition="fail")
        log = self.log(status="passed", total=1, passed=1, failed=0, pass_rate=100)
        result_payload = {
            "status": "failed",
            "total": 4,
            "passed": 1,
            "failed": 3,
            "skipped": 0,
            "report_url": "/reports/99.html",
        }
        with patch.object(
            services, "send_dingtalk", return_value={"channel": "dingtalk"}
        ) as send_ding:
            result = services.trigger_notification(task, log, result=result_payload)
        self.assertFalse(result["skipped"])
        send_ding.assert_called_once()
        self.assertIn("1/3/0/4", result["markdown"])
        self.assertIn("/reports/99.html", result["markdown"])

    def test_stats_can_be_derived_from_cases(self):
        task = self.task()
        result_payload = {
            "status": "failed",
            "cases": [{"status": "passed"}, {"status": "failed"}, {"status": "skipped"}],
        }
        with patch.object(
            services, "send_dingtalk", return_value={"channel": "dingtalk"}
        ):
            result = services.trigger_notification(task, None, result=result_payload)
        self.assertIn("1/1/1/3", result["markdown"])

    def test_trigger_accepts_object_task(self):
        task = SimpleNamespace(
            id=99,
            name="对象定时任务",
            project=self.project,
            trigger_condition="always",
            notice_targets=[self.dingtalk_receiver],
        )
        with patch.object(
            services, "send_dingtalk", return_value={"channel": "dingtalk"}
        ) as send_ding:
            result = services.trigger_notification(task, self.log())
        self.assertEqual(result["sent"], 1)
        send_ding.assert_called_once()
        log = NotificationLog.objects.get()
        self.assertEqual(log.scheduled_task_id, 99)
        self.assertEqual(log.scheduled_task_name, "对象定时任务")

    def test_inactive_receiver_is_not_notified(self):
        self.dingtalk_receiver.is_active = False
        self.dingtalk_receiver.save(update_fields=["is_active"])
        task = self.task()
        with patch.object(services, "send_dingtalk") as send_ding:
            result = services.trigger_notification(task, self.log())
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["reason"], "no_targets")
        send_ding.assert_not_called()

    def test_integer_task_id_without_scheduled_tasks_module_is_safe(self):
        # 设计文档的入口是 trigger_notification(scheduled_task_id, ...)。在
        # scheduled_tasks 尚未实现时也要优雅返回，而不是抛异常。
        result = services.trigger_notification(987654, self.log())
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(NotificationLog.objects.count(), 0)

    def test_disabled_channel_is_recorded_as_failure(self):
        channel = self.channels["dingtalk"]
        channel.is_active = False
        channel.save(update_fields=["is_active"])
        with patch.object(services, "send_dingtalk") as send_ding:
            result = services.trigger_notification(self.task(), self.log())
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["failed"], 1)
        send_ding.assert_not_called()
        log = NotificationLog.objects.get()
        self.assertEqual(log.status, "failed")
        self.assertIn("停用", log.error_message)
        self.assertEqual(log.channel_code, "dingtalk")

    def test_resolve_targets_filters_inactive_and_foreign_project(self):
        inactive = NotificationReceiver.objects.create(
            project=self.project,
            name="停用",
            channel=self.channels["dingtalk"],
            webhook_url="https://example.com/off",
            is_active=False,
        )
        other_project = Project.objects.create(
            name="其他项目", project_type="api", owner=self.owner
        )
        foreign = NotificationReceiver.objects.create(
            project=other_project,
            name="别的项目",
            channel=self.channels["dingtalk"],
            webhook_url="https://example.com/other",
        )
        targets = services.resolve_targets(
            self.project, [self.dingtalk_receiver.id, inactive.id, foreign.id]
        )
        self.assertEqual([receiver.id for receiver in targets], [self.dingtalk_receiver.id])
