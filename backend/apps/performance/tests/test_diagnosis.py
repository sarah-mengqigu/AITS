"""AI diagnosis tests - rule fallback, webhook parsing and notifications."""

from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings

from apps.common.api.api_exception_handler import BusinessError
from apps.notifications.models import NotificationChannel, NotificationReceiver
from apps.performance.constants import NOTIFY_TARGET_CACHE_KEY
from apps.performance.models import AiDiagnosisRecord
from apps.performance.services.diagnosis import (
    diagnose_execution,
    handle_grafana_webhook,
    resolve_notify_receiver,
    rule_diagnosis,
)
from apps.performance.tests.base import PerformanceFixture, grafana_payload


class _FakeLLMResult:
    text = "LLM 诊断结论：服务端连接池耗尽导致超时，建议扩容并降低并发。"


class _FakeLLMService:
    is_mock = False

    def __init__(self, *args, **kwargs):  # noqa: D401 - mimic LLMService signature
        self.args = args
        self.kwargs = kwargs

    def chat(self, *args, **kwargs):
        return _FakeLLMResult()


class RuleDiagnosisTests(PerformanceFixture):
    def test_rule_diagnosis_contains_metrics_findings_and_suggestions(self):
        execution = self.create_execution(
            status="failed",
            total_requests=1000,
            avg_tps=12.5,
            p50_response_time=100,
            p95_response_time=3500,
            p99_response_time=8000,
            error_rate=0.25,
            status_code_dist={"200": 750, "500": 200, "429": 50},
        )
        content = rule_diagnosis(execution)

        self.assertIn("规则引擎", content)
        self.assertIn("25.00%", content)
        self.assertIn("## 关键发现", content)
        self.assertIn("## 优化建议", content)
        self.assertIn("429", content)
        self.assertGreater(len(content), 100)

    def test_rule_diagnosis_healthy_execution(self):
        execution = self.create_execution(
            status="passed",
            total_requests=500,
            avg_tps=50,
            p50_response_time=80,
            p95_response_time=120,
            p99_response_time=300,
            error_rate=0.0,
            status_code_dist={"200": 500},
        )
        content = rule_diagnosis(execution)
        self.assertIn("健康", content)
        self.assertIn("建议", content)

    def test_rule_diagnosis_without_execution_uses_alert(self):
        alert = grafana_payload(project_id=self.project.id)["alerts"][0]
        content = rule_diagnosis(None, alert)
        self.assertIn("排查建议", content)
        self.assertIn("AITSHighErrorRate", content)


class DiagnoseExecutionTests(PerformanceFixture):
    def test_creates_manual_record_with_content(self):
        execution = self.create_execution(
            status="failed", error_rate=0.2, p95_response_time=3000,
            status_code_dist={"200": 800, "500": 200},
        )
        record = diagnose_execution(execution)

        self.assertIsInstance(record, AiDiagnosisRecord)
        self.assertEqual(record.source, "manual")
        self.assertEqual(record.execution_id, execution.id)
        self.assertEqual(record.project_id, self.project.id)
        self.assertTrue(record.diagnosis_content.strip())
        self.assertIsNone(record.notified_at)

    def test_uses_llm_when_not_mock(self):
        execution = self.create_execution(status="failed", error_rate=0.2)
        with patch(
            "apps.ai_core.services.llm_service.LLMService", _FakeLLMService
        ):
            record = diagnose_execution(execution)
        self.assertIn("LLM 诊断结论", record.diagnosis_content)

    def test_falls_back_to_rules_when_llm_unavailable(self):
        execution = self.create_execution(status="failed", error_rate=0.3)
        with patch(
            "apps.ai_core.services.llm_service.LLMService",
            side_effect=RuntimeError("llm down"),
        ):
            record = diagnose_execution(execution)
        self.assertIn("规则引擎", record.diagnosis_content)
        self.assertTrue(record.diagnosis_content.strip())

    def test_llm_mock_mode_uses_rules(self):
        execution = self.create_execution(status="passed", error_rate=0.0)
        record = diagnose_execution(execution)
        # AI_MOCK_MODE=True in tests, so the readable rule engine output is used.
        self.assertIn("规则引擎", record.diagnosis_content)


class GrafanaWebhookServiceTests(PerformanceFixture):
    def test_creates_grafana_record(self):
        result = handle_grafana_webhook(grafana_payload(project_id=self.project.id))

        self.assertEqual(result["status"], "processed")
        self.assertIsNotNone(result["record_id"])
        record = AiDiagnosisRecord.objects.get(pk=result["record_id"])
        self.assertEqual(record.source, "grafana")
        self.assertEqual(record.alert_name, "AITSHighErrorRate")
        self.assertEqual(record.severity, "critical")
        self.assertEqual(record.project_id, self.project.id)
        self.assertTrue(record.diagnosis_content.strip())
        self.assertIn("labels", record.raw_payload)

    def test_links_execution_and_project_from_labels(self):
        execution = self.create_execution(status="failed", error_rate=0.3)
        result = handle_grafana_webhook(grafana_payload(execution_id=execution.id))

        record = AiDiagnosisRecord.objects.get(pk=result["record_id"])
        self.assertEqual(record.execution_id, execution.id)
        self.assertEqual(record.project_id, execution.project_id)

    def test_invalid_payload_raises_business_error(self):
        for payload in ({"foo": "bar"}, {"alerts": []}, "not-a-dict", [1, 2, 3]):
            with self.assertRaises(BusinessError) as ctx:
                handle_grafana_webhook(payload)
            self.assertEqual(ctx.exception.biz_code, "invalid_payload")

    def test_multiple_alerts_create_multiple_records(self):
        payload = grafana_payload(project_id=self.project.id)
        second = dict(payload["alerts"][0])
        second["labels"] = dict(second["labels"], alertname="AITSP95LatencyHigh")
        payload["alerts"] = [payload["alerts"][0], second]

        result = handle_grafana_webhook(payload)

        self.assertEqual(result["count"], 2)
        self.assertEqual(AiDiagnosisRecord.objects.count(), 2)


class NotificationTests(PerformanceFixture):
    def setUp(self):
        super().setUp()
        self.channel, _ = NotificationChannel.objects.get_or_create(
            channel_code="dingtalk",
            defaults={"name": "钉钉", "is_active": True},
        )
        self.receiver = NotificationReceiver.objects.create(
            project=None,
            name="AI测试部门群",
            channel=self.channel,
            webhook_url="https://oapi.dingtalk.com/robot/send?access_token=demo",
            is_active=True,
        )

    def test_diagnosis_notification_sent_and_timestamped(self):
        execution = self.create_execution(status="failed", error_rate=0.2)
        with patch(
            "apps.notifications.services.trigger_notification",
            return_value={"sent": 1, "failed": 0},
        ) as mocked:
            record = diagnose_execution(execution)

        self.assertTrue(mocked.called)
        record.refresh_from_db()
        self.assertIsNotNone(record.notified_at)

    def test_notification_failure_does_not_break_diagnosis(self):
        execution = self.create_execution(status="failed", error_rate=0.2)
        with patch(
            "apps.notifications.services.trigger_notification",
            side_effect=RuntimeError("webhook exploded"),
        ):
            record = diagnose_execution(execution)
        self.assertTrue(record.diagnosis_content.strip())
        self.assertIsNone(record.notified_at)

    def test_no_receiver_skips_notification(self):
        self.receiver.delete()
        execution = self.create_execution(status="failed", error_rate=0.2)
        with patch(
            "apps.notifications.services.trigger_notification"
        ) as mocked:
            record = diagnose_execution(execution)
        mocked.assert_not_called()
        self.assertIsNone(record.notified_at)

    def test_receiver_id_setting_takes_precedence(self):
        other = NotificationReceiver.objects.create(
            project=None,
            name="另一个群",
            channel=self.channel,
            webhook_url="https://example.com/hook",
            is_active=True,
        )
        with override_settings(GRAFANA_AI_NOTIFY_RECEIVER_ID=str(other.id)):
            receiver = resolve_notify_receiver()
        self.assertEqual(receiver.id, other.id)
        self.assertEqual(cache.get(NOTIFY_TARGET_CACHE_KEY), other.id)

    def test_receiver_resolution_caches_and_recovers(self):
        first = resolve_notify_receiver()
        self.assertEqual(first.id, self.receiver.id)
        self.assertEqual(cache.get(NOTIFY_TARGET_CACHE_KEY), self.receiver.id)

        second = resolve_notify_receiver()
        self.assertEqual(second.id, self.receiver.id)

        self.receiver.delete()
        cache.delete(NOTIFY_TARGET_CACHE_KEY)
        self.assertIsNone(resolve_notify_receiver())

    def test_resolved_record_can_be_ignored(self):
        record = self.create_diagnosis()
        record.status = "ignored"
        record.save(update_fields=["status", "updated_at"])
        record.refresh_from_db()
        self.assertEqual(record.status, "ignored")
