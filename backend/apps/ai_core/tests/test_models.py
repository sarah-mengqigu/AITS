"""模型行为测试：默认配置互斥、api_key 掩码、MCP 工具刷新。"""

from __future__ import annotations

from django.test import TestCase

from apps.ai_core.models import (
    LLMConfiguration,
    MCPConfiguration,
    MCPTool,
    RAGConfiguration,
    mask_api_key,
)
from apps.ai_core.serializers import (
    LLMConfigurationSerializer,
    MCPConfigurationSerializer,
)
from apps.ai_core.tests.helpers import create_project, create_user


class LLMConfigurationTests(TestCase):
    def setUp(self):
        self.user = create_user("llm-owner")
        self.project = create_project(self.user, name="LLM 项目")

    def test_default_is_unique_per_project_and_model_type(self):
        first = LLMConfiguration.objects.create(
            project=self.project, name="a", provider="mock", model_type="text",
            is_default=True,
        )
        second = LLMConfiguration.objects.create(
            project=self.project, name="b", provider="mock", model_type="text",
            is_default=True,
        )
        third = LLMConfiguration.objects.create(
            project=self.project, name="c", provider="mock", model_type="vision",
            is_default=True,
        )
        global_config = LLMConfiguration.objects.create(
            name="global", provider="mock", model_type="text", is_default=True
        )
        first.refresh_from_db()
        third.refresh_from_db()
        global_config.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)
        self.assertTrue(third.is_default)  # different model_type keeps its own default
        self.assertTrue(global_config.is_default)  # different scope keeps its own default

    def test_api_key_is_masked(self):
        config = LLMConfiguration.objects.create(
            name="masked",
            provider="openai",
            model_name="gpt-4o-mini",
            api_key="sk-abcdefgh1234",
            base_url="https://api.example.com/v1",
        )
        self.assertEqual(config.masked_api_key, "sk-****1234")
        self.assertEqual(mask_api_key(""), "")
        self.assertEqual(mask_api_key("ab"), "sk-****ab")

        data = LLMConfigurationSerializer(config).data
        self.assertEqual(data["api_key"], "sk-****1234")
        self.assertEqual(config.api_key, "sk-abcdefgh1234")

    def test_masked_value_never_overwrites_stored_key(self):
        config = LLMConfiguration.objects.create(
            name="keep-key", provider="openai", api_key="sk-real-key-9999"
        )
        serializer = LLMConfigurationSerializer(
            config,
            data={"api_key": "sk-****9999", "model_name": "gpt-4o"},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        config.refresh_from_db()
        self.assertEqual(config.api_key, "sk-real-key-9999")
        self.assertEqual(config.model_name, "gpt-4o")


class RAGConfigurationTests(TestCase):
    def test_single_default_per_project(self):
        user = create_user("rag-owner")
        project = create_project(user, name="RAG 项目")
        first = RAGConfiguration.objects.create(project=project, name="r1", is_default=True)
        second = RAGConfiguration.objects.create(project=project, name="r2", is_default=True)
        first.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)
        self.assertEqual(second.effective_chunk_overlap, 200)


class MCPConfigurationTests(TestCase):
    def test_refresh_tools_syncs_rows(self):
        config = MCPConfiguration.objects.create(
            name="filesystem",
            transport="stdio",
            server_config={
                "command": "npx",
                "tools": [
                    {
                        "name": "list_files",
                        "description": "列出目录",
                        "input_schema": {"type": "object"},
                    },
                    {"name": "read_file", "description": "读取文件"},
                ],
            },
        )
        result = config.refresh_tools()
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["status"], "connected")
        self.assertEqual(MCPTool.objects.filter(config=config).count(), 2)
        self.assertEqual(config.last_status, "connected")
        self.assertEqual(config.tool_count, 2)

        # Shrinking the declared tool list removes stale rows.
        config.server_config = {"tools": [{"name": "list_files"}]}
        config.save()
        result = config.refresh_tools()
        self.assertEqual(result["count"], 1)
        self.assertEqual(
            list(MCPTool.objects.filter(config=config).values_list("name", flat=True)),
            ["list_files"],
        )

    def test_refresh_tools_uses_deterministic_fallback(self):
        config = MCPConfiguration.objects.create(
            name="Remote MCP", transport="sse", server_config={"url": "http://localhost:9000/sse"}
        )
        result = config.refresh_tools()
        self.assertEqual(result["count"], 1)
        self.assertTrue(result["tools"][0]["name"].endswith("_ping"))

    def test_serializer_exposes_tool_count(self):
        config = MCPConfiguration.objects.create(name="mcp", server_config={"tools": ["a", "b"]})
        config.refresh_tools()
        data = MCPConfigurationSerializer(config).data
        self.assertEqual(data["tool_count"], 2)
        self.assertEqual(data["last_status"], "connected")
