"""LangChain 胶水层测试：Prompt / 输出解析 / 模型 / Embeddings / 向量库 / 工具。"""

from __future__ import annotations

import json
from unittest import mock

from django.test import TestCase, override_settings

from apps.ai_core.models import LLMConfiguration, LLMUsageLog, MCPConfiguration
from apps.ai_core.services import langchain_status
from apps.ai_core.services.langchain_bridge import (
    CHAT_OPENAI_AVAILABLE,
    LANGCHAIN_AVAILABLE,
    VECTORSTORE_AVAILABLE,
    build_chat_model,
    build_mcp_tools,
    build_vector_store,
    parse_json_output,
    render_messages,
)
from apps.ai_core.services.llm_service import LLMService
from apps.ai_core.services.rag_service import RAGService, embed_text
from apps.ai_core.tests.helpers import create_project, create_user
from apps.common.api.api_exception_handler import BusinessError
from apps.projects.models import KnowledgeDocument


class CapabilityTests(TestCase):
    def test_langchain_capabilities_are_present(self):
        status = langchain_status()
        self.assertTrue(status["langchain_core"])
        self.assertTrue(status["chat_openai"])
        self.assertTrue(status["vectorstore"])
        self.assertTrue(LANGCHAIN_AVAILABLE)
        self.assertTrue(CHAT_OPENAI_AVAILABLE)
        self.assertTrue(VECTORSTORE_AVAILABLE)


class PromptAndParserTests(TestCase):
    def test_render_messages_keeps_braces_in_prompt(self):
        user_prompt = '请返回 {"cases": [{"name": "x"}]}，不要解释'
        messages = render_messages("系统提示", user_prompt)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertEqual(messages[0]["content"], "系统提示")
        self.assertEqual(messages[1]["content"], user_prompt)

    def test_parse_json_output_accepts_fenced_and_prose_json(self):
        payload = {"cases": [{"name": "登录"}]}
        fenced = f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"
        self.assertEqual(parse_json_output(fenced), payload)
        prose = f"好的，结果如下：{json.dumps(payload)} 希望有帮助"
        self.assertEqual(parse_json_output(prose), payload)

    def test_parse_json_output_returns_none_for_garbage(self):
        self.assertIsNone(parse_json_output("完全不是 JSON"))
        self.assertIsNone(parse_json_output(""))


class ChatModelTests(TestCase):
    def setUp(self):
        self.config = LLMConfiguration.objects.create(
            project=None,
            name="langchain-openai",
            provider="openai",
            model_name="gpt-4o-mini",
            api_key="sk-test-1234",
            base_url="https://gateway.example.com/v1",
            temperature=0.3,
            max_tokens=512,
            model_type="text",
            is_default=True,
        )

    def test_build_chat_model_binds_provider_settings(self):
        model = build_chat_model(self.config)
        self.assertEqual(model.model_name, "gpt-4o-mini")
        self.assertEqual(model.openai_api_base, "https://gateway.example.com/v1")
        self.assertEqual(model.openai_api_key.get_secret_value(), "sk-test-1234")
        self.assertEqual(model.max_tokens, 512)

    def test_azure_provider_uses_api_key_header(self):
        azure = LLMConfiguration.objects.create(
            name="azure", provider="azure", model_name="gpt-4",
            api_key="azure-key", base_url="https://x.openai.azure.com",
            model_type="text",
        )
        model = build_chat_model(azure)
        self.assertEqual(model.default_headers.get("api-key"), "azure-key")

    @override_settings(AI_MOCK_MODE=False, AITS_LLM_BACKEND="langchain")
    def test_llm_service_uses_langchain_backend(self):
        fake = {
            "text": '{"cases": []}',
            "prompt_tokens": 12,
            "completion_tokens": 5,
            "total_tokens": 17,
            "model": "gpt-4o-mini-2024",
            "raw": {"finish_reason": "stop"},
        }
        with mock.patch(
            "apps.ai_core.services.llm_service.invoke_chat_model", return_value=fake
        ) as patched:
            service = LLMService(config=self.config)
            result = service.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(service.backend, "langchain")
        patched.assert_called_once()
        self.assertEqual(result.text, fake["text"])
        self.assertEqual(result.total_tokens, 17)
        self.assertEqual(result.model, "gpt-4o-mini-2024")
        self.assertEqual(result.provider, "openai")
        log = LLMUsageLog.objects.latest("id")
        self.assertTrue(log.success)
        self.assertEqual(log.total_tokens, 17)

    @override_settings(AI_MOCK_MODE=False, AITS_LLM_BACKEND="http")
    def test_llm_service_can_force_http_backend(self):
        self.assertEqual(LLMService(config=self.config).backend, "http")

    @override_settings(AI_MOCK_MODE=True)
    def test_mock_mode_does_not_call_langchain(self):
        with mock.patch(
            "apps.ai_core.services.llm_service.invoke_chat_model"
        ) as patched:
            result = LLMService(config=self.config).chat(
                [{"role": "user", "content": "生成用例"}]
            )
        patched.assert_not_called()
        self.assertTrue(result.provider == "mock")


class EmbeddingAndVectorStoreTests(TestCase):
    def test_deterministic_embeddings_interface(self):
        from apps.ai_core.services.langchain_bridge import DeterministicEmbeddings

        embeddings = DeterministicEmbeddings()
        first = embeddings.embed_query("登录 token")
        second = embeddings.embed_query("登录 token")
        self.assertEqual(first, second)
        self.assertEqual(first, embed_text("登录 token"))
        batch = embeddings.embed_documents(["登录 token", "下单"])
        self.assertEqual(len(batch), 2)
        self.assertEqual(batch[0], first)

    def test_vector_store_search_order_and_metadata(self):
        store = build_vector_store(
            [
                {"text": "登录 token 校验", "document_id": 7, "source": "接口文档"},
                {"text": "订单创建流程", "document_id": 9, "source": "业务文档"},
            ]
        )
        self.assertIsNotNone(store)
        hits = store.similarity_search_with_score("登录 token", k=2)
        self.assertEqual(hits[0][0].page_content, "登录 token 校验")
        self.assertEqual(hits[0][0].metadata["document_id"], 7)
        self.assertGreater(hits[0][1], 0)

    def test_empty_entries_return_no_store(self):
        self.assertIsNone(build_vector_store([]))


class McpToolTests(TestCase):
    def setUp(self):
        self.config = MCPConfiguration.objects.create(
            project=None,
            name="filesystem-mcp",
            transport="stdio",
            server_config={
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
                "tools": [
                    {"name": "list_files", "description": "列出目录",
                     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
                    {"name": "read_file", "description": "读取文件"},
                ],
            },
        )

    def test_build_structured_tools_from_mcp_config(self):
        tools = build_mcp_tools(self.config)
        self.assertEqual({tool.name for tool in tools}, {"list_files", "read_file"})
        self.assertIn("列出目录", tools[0].description)

    def test_tool_execution_requires_real_runtime(self):
        tool = self.config.langchain_tools()[0]
        with self.assertRaises(BusinessError) as ctx:
            tool.invoke({"payload": "x"})
        self.assertEqual(ctx.exception.biz_code, "mcp_runtime_unavailable")


class RagLangChainBackendTests(TestCase):
    def setUp(self):
        self.user = create_user("rag-lc")
        self.project = create_project(self.user)
        self.document = KnowledgeDocument.objects.create(
            project=self.project,
            title="接口文档",
            content="登录接口需要 token 校验。创建订单需要商品 ID 与数量。" * 3,
        )
        self.service = RAGService(project=self.project)
        chunks = self.service.index_document(self.document)
        self.assertGreater(chunks, 0)

    def test_search_goes_through_langchain_vector_store(self):
        from apps.ai_core.services import rag_service as rag_module

        real_builder = rag_module.RAGService._langchain_search
        calls = {"count": 0}

        def counting(self, store, query, limit):
            calls["count"] += 1
            return real_builder(self, store, query, limit)

        with mock.patch.object(rag_module.RAGService, "_langchain_search", counting):
            hits = self.service.search("登录 token", project=self.project)
        self.assertEqual(calls["count"], 1)
        self.assertTrue(hits)
        self.assertIn("登录", hits[0]["text"])

    def test_langchain_results_match_builtin_cosine_results(self):
        langchain_hits = self.service.search("登录 token", project=self.project, top_k=5)
        with mock.patch(
            "apps.ai_core.services.langchain_bridge.build_vector_store",
            return_value=None,
        ):
            builtin_hits = self.service.search("登录 token", project=self.project, top_k=5)
        self.assertEqual([h["text"] for h in langchain_hits], [h["text"] for h in builtin_hits])
        for left, right in zip(langchain_hits, builtin_hits):
            self.assertAlmostEqual(left["score"], right["score"], places=5)
            self.assertEqual(left["document_id"], right["document_id"])
            self.assertEqual(left["source"], right["source"])
