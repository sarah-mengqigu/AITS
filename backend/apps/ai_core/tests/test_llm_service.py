"""LLMService / ModelManager 单元测试（全部离线，使用 Mock provider）。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase, override_settings

from apps.ai_core.models import LLMConfiguration, LLMUsageLog
from apps.ai_core.services.llm_service import LLMService
from apps.ai_core.services.model_manager import ModelManager, get_model_manager
from apps.common.api.api_exception_handler import BusinessError
from apps.ai_core.tests.helpers import create_project, create_user


class MockProviderTests(TestCase):
    def test_mock_mode_is_deterministic_per_keyword(self):
        service = LLMService()
        self.assertTrue(service.is_mock)

        first = service.chat([{"role": "user", "content": "请生成 testcase/用例"}])
        second = service.chat([{"role": "user", "content": "请生成 testcase/用例"}])
        self.assertEqual(first.text, second.text)
        payload = json.loads(first.text)
        self.assertIn("cases", payload)
        self.assertGreaterEqual(len(payload["cases"]), 4)
        self.assertEqual(first.provider, "mock")
        self.assertGreater(first.total_tokens, 0)

        script = service.chat([{"role": "user", "content": "给我 playwright 脚本"}])
        self.assertIn("from playwright.sync_api import", script.text)

        diagnosis = service.chat([{"role": "user", "content": "请诊断这个性能问题"}])
        parsed = json.loads(diagnosis.text)
        self.assertIn("diagnosis", parsed)
        self.assertIn("suggestions", parsed)

    def test_agent_tag_routes_to_specialised_mock_output(self):
        service = LLMService()
        result = service.chat(
            [{"role": "user", "content": "[agent:midscene] 生成脚本"}]
        )
        parsed = json.loads(result.text)
        self.assertEqual(parsed["script_type"], "yaml")
        self.assertIn("tasks", parsed["content"])

    def test_usage_log_written_with_agent_context(self):
        service = LLMService()
        service.agent_name = "api_testcase"
        service.task_type = "api_testcase"
        service.task_id = "77"
        service.chat([{"role": "user", "content": "生成用例"}])
        log = LLMUsageLog.objects.latest("id")
        self.assertEqual(log.agent_name, "api_testcase")
        self.assertEqual(log.task_type, "api_testcase")
        self.assertEqual(log.task_id, "77")
        self.assertTrue(log.success)
        self.assertGreater(log.total_tokens, 0)
        self.assertIn("生成用例", log.request_preview)


class RemoteProviderTests(TestCase):
    def setUp(self):
        self.config = LLMConfiguration.objects.create(
            name="openai-global",
            provider="openai",
            model_name="gpt-test",
            api_key="sk-secret-key-1234",
            base_url="https://fake-llm.local/v1",
            model_type="text",
            is_default=True,
        )

    @override_settings(AI_MOCK_MODE=False)
    def test_remote_success_parses_response(self):
        response = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"content": "hello from provider"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            "model": "gpt-test-001",
        }
        response.raise_for_status.return_value = None
        with patch("apps.ai_core.services.llm_service.requests.post",
                   return_value=response) as mocked_post:
            result = LLMService(config=self.config).chat(
                [{"role": "user", "content": "hi"}], temperature=0.1, max_tokens=16
            )
        self.assertEqual(result.text, "hello from provider")
        self.assertEqual(result.total_tokens, 18)
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.model, "gpt-test-001")
        self.assertEqual(mocked_post.call_args.kwargs["timeout"], 120)
        self.assertEqual(
            mocked_post.call_args.kwargs["headers"]["Authorization"], "Bearer sk-secret-key-1234"
        )

    @override_settings(AI_MOCK_MODE=False)
    def test_remote_failure_retries_once_then_llm_error(self):
        with patch(
            "apps.ai_core.services.llm_service.requests.post",
            side_effect=requests.RequestException("network down"),
        ) as mocked_post:
            with self.assertRaises(BusinessError) as ctx:
                LLMService(config=self.config).chat([{"role": "user", "content": "hi"}])
        self.assertEqual(ctx.exception.biz_code, "llm_error")
        self.assertEqual(mocked_post.call_count, 2)
        log = LLMUsageLog.objects.latest("id")
        self.assertFalse(log.success)
        self.assertIn("llm_error", str(ctx.exception.biz_code))


class ModelManagerTests(TestCase):
    def setUp(self):
        self.user = create_user("mm-owner")
        self.project = create_project(self.user)
        self.manager = ModelManager()

    def test_project_default_wins_over_global_default(self):
        global_config = LLMConfiguration.objects.create(
            name="global", provider="mock", model_type="text", is_default=True
        )
        project_config = LLMConfiguration.objects.create(
            project=self.project, name="project", provider="mock", model_type="text",
            is_default=True,
        )
        self.assertEqual(self.manager.get_text_model(self.project), project_config)
        self.assertEqual(self.manager.get_text_model(), global_config)
        self.assertIsNone(self.manager.get_vision_model(self.project))

    def test_chat_without_config_degrades_to_mock(self):
        result = self.manager.chat(
            [{"role": "user", "content": "帮我生成 testcase"}],
            project=self.project,
            agent_name="api_testcase",
            task_type="api_testcase",
            task_id=9,
        )
        self.assertEqual(result.provider, "mock")
        log = LLMUsageLog.objects.latest("id")
        self.assertEqual(log.agent_name, "api_testcase")
        self.assertEqual(str(log.task_id), "9")
        self.assertEqual(log.project_id, self.project.id)

    def test_get_model_manager_returns_singleton(self):
        self.assertIs(get_model_manager(), get_model_manager())
