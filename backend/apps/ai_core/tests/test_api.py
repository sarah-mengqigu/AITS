"""HTTP 层测试：/api/ai/ 配置 CRUD、权限、RAG、MCP、Agent、用量统计。"""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ai_core.models import LLMConfiguration, LLMUsageLog, MCPTool
from apps.ai_core.services.model_manager import ModelManager
from apps.ai_core.tests.helpers import (
    TempMediaMixin,
    add_member,
    create_project,
    create_user,
)
from apps.projects.models import KnowledgeDocument

LLM_CONFIGS_URL = "/api/ai/llm-configs/"
RAG_CONFIGS_URL = "/api/ai/rag-configs/"
RAG_INDEX_URL = "/api/ai/rag/index/"
RAG_SEARCH_URL = "/api/ai/rag/search/"
RAG_STATS_URL = "/api/ai/rag/stats/"
MCP_CONFIGS_URL = "/api/ai/mcp-configs/"
MCP_TOOLS_URL = "/api/ai/mcp-tools/"
USAGE_LOGS_URL = "/api/ai/usage-logs/"
USAGE_STATS_URL = "/api/ai/usage-stats/"
AGENTS_URL = "/api/ai/agents/"


class AIApiTestCase(TestCase):
    def setUp(self):
        self.staff = create_user("api-staff", staff=True)
        self.owner = create_user("api-owner")
        self.admin = create_user("api-admin")
        self.editor = create_user("api-editor")
        self.outsider = create_user("api-outsider")
        self.project = create_project(self.owner, name="AI 接口项目")
        add_member(self.project, self.admin, "admin")
        add_member(self.project, self.editor, "editor")
        self.client = APIClient()

    def auth(self, user):
        self.client.force_authenticate(user=user)


class LLMConfigurationApiTests(AIApiTestCase):
    def test_crud_masks_api_key_and_test_action(self):
        self.auth(self.staff)
        response = self.client.post(
            LLM_CONFIGS_URL,
            {
                "name": "openai-global",
                "provider": "openai",
                "model_name": "gpt-4o-mini",
                "api_key": "sk-abcdefgh1234",
                "base_url": "https://api.example.com/v1",
                "model_type": "text",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        config_id = response.data["id"]
        self.assertEqual(response.data["api_key"], "sk-****1234")
        self.assertNotIn("sk-abcdefgh1234", str(response.data))
        self.assertEqual(
            LLMConfiguration.objects.get(pk=config_id).api_key, "sk-abcdefgh1234"
        )

        listing = self.client.get(LLM_CONFIGS_URL)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(listing.data["results"][0]["api_key"], "sk-****1234")

        # PATCH with the masked echo must keep the real key
        patched = self.client.patch(
            f"{LLM_CONFIGS_URL}{config_id}/",
            {"api_key": "sk-****1234", "temperature": 0.3},
            format="json",
        )
        self.assertEqual(patched.status_code, 200, patched.data)
        config = LLMConfiguration.objects.get(pk=config_id)
        self.assertEqual(config.api_key, "sk-abcdefgh1234")
        self.assertAlmostEqual(config.temperature, 0.3)

        test_response = self.client.post(f"{LLM_CONFIGS_URL}{config_id}/test/")
        self.assertEqual(test_response.status_code, 200, test_response.data)
        self.assertTrue(test_response.data["success"])
        self.assertTrue(test_response.data["mock"])

    def test_test_action_requires_write_permission(self):
        config = LLMConfiguration.objects.create(
            name="global-probe", provider="mock", model_type="text"
        )
        self.auth(self.outsider)
        denied = self.client.post(f"{LLM_CONFIGS_URL}{config.id}/test/")
        self.assertEqual(denied.status_code, 403, denied.data)
        self.auth(self.staff)
        allowed = self.client.post(f"{LLM_CONFIGS_URL}{config.id}/test/")
        self.assertEqual(allowed.status_code, 200, allowed.data)
        self.assertTrue(allowed.data["success"])

    def test_set_default_endpoint_enforces_mutual_exclusion(self):
        self.auth(self.staff)
        first = LLMConfiguration.objects.create(
            name="first", provider="mock", model_type="text", is_default=True
        )
        second = LLMConfiguration.objects.create(
            name="second", provider="mock", model_type="text"
        )
        vision = LLMConfiguration.objects.create(
            name="vision", provider="mock", model_type="vision", is_default=True
        )
        response = self.client.post(
            f"{LLM_CONFIGS_URL}{second.id}/set-default/", format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        first.refresh_from_db()
        second.refresh_from_db()
        vision.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)
        self.assertTrue(vision.is_default)  # different model_type is untouched

    def test_global_config_write_requires_staff(self):
        self.auth(self.outsider)
        denied = self.client.post(
            LLM_CONFIGS_URL, {"name": "global", "provider": "mock"}, format="json"
        )
        self.assertEqual(denied.status_code, 403, denied.data)
        self.assertEqual(denied.data["code"], "permission_denied")

        self.auth(self.staff)
        allowed = self.client.post(
            LLM_CONFIGS_URL, {"name": "global", "provider": "mock"}, format="json"
        )
        self.assertEqual(allowed.status_code, 201, allowed.data)

    def test_project_config_write_requires_admin(self):
        self.auth(self.editor)
        denied = self.client.post(
            LLM_CONFIGS_URL,
            {"project": self.project.id, "name": "editor-config", "provider": "mock"},
            format="json",
        )
        self.assertEqual(denied.status_code, 403, denied.data)

        self.auth(self.admin)
        allowed = self.client.post(
            LLM_CONFIGS_URL,
            {"project": self.project.id, "name": "admin-config", "provider": "mock"},
            format="json",
        )
        self.assertEqual(allowed.status_code, 201, allowed.data)

    def test_project_config_not_visible_to_outsider(self):
        LLMConfiguration.objects.create(
            project=self.project, name="project-config", provider="mock"
        )
        global_config = LLMConfiguration.objects.create(
            name="global-config", provider="mock"
        )
        self.auth(self.outsider)
        listing = self.client.get(LLM_CONFIGS_URL)
        self.assertEqual(listing.status_code, 200)
        ids = [row["id"] for row in listing.data["results"]]
        self.assertIn(global_config.id, ids)
        self.assertNotIn(self.project.llm_configs.first().id, ids)

        self.auth(self.editor)
        listing = self.client.get(LLM_CONFIGS_URL, {"project": self.project.id})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)

    def test_config_requires_authentication(self):
        response = self.client.get(LLM_CONFIGS_URL)
        self.assertIn(response.status_code, (401, 403))


class AgentApiTests(AIApiTestCase):
    def test_list_and_run_agents(self):
        self.auth(self.editor)
        listing = self.client.get(AGENTS_URL)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 7)
        names = {agent["name"] for agent in listing.data["results"]}
        self.assertEqual(len(names), 7)

        response = self.client.post(
            "/api/ai/agents/api_testcase/run/",
            {
                "payload": {
                    "endpoint": {"method": "GET", "path": "/api/ping"},
                    "context": "健康检查",
                }
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(len(response.data["result"]["cases"]), 4)

    def test_run_agent_accepts_flat_payload(self):
        self.auth(self.owner)
        response = self.client.post(
            "/api/ai/agents/midscene/run/",
            {"requirement": "打开首页", "url": "https://demo.test"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["result"]["script_type"], "yaml")

    def test_unknown_agent_returns_404(self):
        self.auth(self.editor)
        response = self.client.post(
            "/api/ai/agents/unknown_agent/run/", {"payload": {}}, format="json"
        )
        self.assertEqual(response.status_code, 404, response.data)
        self.assertEqual(response.data["code"], "agent_not_found")


class RAGConfigurationApiTests(AIApiTestCase):
    def test_rag_config_crud_and_set_default(self):
        self.auth(self.staff)
        first = self.client.post(
            RAG_CONFIGS_URL,
            {"name": "global-rag", "chunk_size": 800, "chunk_overlap": 100},
            format="json",
        )
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data["chunk_size"], 800)
        second = self.client.post(
            RAG_CONFIGS_URL, {"name": "global-rag-2"}, format="json"
        )
        self.assertEqual(second.status_code, 201, second.data)

        set_default = self.client.post(
            f"{RAG_CONFIGS_URL}{second.data['id']}/set-default/", format="json"
        )
        self.assertEqual(set_default.status_code, 200, set_default.data)
        self.assertTrue(set_default.data["is_default"])

        listing = self.client.get(RAG_CONFIGS_URL)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 2)

        patched = self.client.patch(
            f"{RAG_CONFIGS_URL}{first.data['id']}/",
            {"collection_name": "aits-docs"},
            format="json",
        )
        self.assertEqual(patched.status_code, 200, patched.data)

        deleted = self.client.delete(f"{RAG_CONFIGS_URL}{first.data['id']}/")
        self.assertEqual(deleted.status_code, 204)

    def test_rag_config_validation_and_permissions(self):
        self.auth(self.staff)
        invalid = self.client.post(
            RAG_CONFIGS_URL,
            {"name": "bad", "chunk_size": 100, "chunk_overlap": 200},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400, invalid.data)

        self.auth(self.editor)
        denied = self.client.post(
            RAG_CONFIGS_URL,
            {"project": self.project.id, "name": "editor-rag"},
            format="json",
        )
        self.assertEqual(denied.status_code, 403, denied.data)

        self.auth(self.owner)
        allowed = self.client.post(
            RAG_CONFIGS_URL,
            {"project": self.project.id, "name": "owner-rag", "is_default": True},
            format="json",
        )
        self.assertEqual(allowed.status_code, 201, allowed.data)
        self.assertTrue(allowed.data["is_default"])


class RagApiTests(TempMediaMixin, AIApiTestCase):
    def setUp(self):
        super().setUp()
        self.document = KnowledgeDocument.objects.create(
            project=self.project,
            title="登录说明",
            content="用户登录接口 POST /api/login，参数 username/password，成功后返回 token。",
        )

    def test_index_search_and_stats(self):
        self.auth(self.editor)
        indexed = self.client.post(
            RAG_INDEX_URL, {"document_id": self.document.id}, format="json"
        )
        self.assertEqual(indexed.status_code, 200, indexed.data)
        self.assertGreaterEqual(indexed.data["chunk_count"], 1)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, "indexed")

        searched = self.client.post(
            RAG_SEARCH_URL,
            {"query": "登录 token", "project": self.project.id, "top_k": 3},
            format="json",
        )
        self.assertEqual(searched.status_code, 200, searched.data)
        self.assertGreaterEqual(searched.data["count"], 1)
        hit = searched.data["results"][0]
        self.assertEqual(hit["source"], "登录说明")
        self.assertEqual(
            set(hit.keys()), {"text", "score", "source", "document_id"}
        )

        stats = self.client.get(RAG_STATS_URL)
        self.assertEqual(stats.status_code, 200)
        self.assertGreaterEqual(stats.data["documents"], 1)
        self.assertGreaterEqual(stats.data["chunks"], 1)

    def test_rag_validation_and_permissions(self):
        self.auth(self.editor)
        missing_document = self.client.post(RAG_INDEX_URL, {}, format="json")
        self.assertEqual(missing_document.status_code, 400, missing_document.data)

        missing_query = self.client.post(RAG_SEARCH_URL, {}, format="json")
        self.assertEqual(missing_query.status_code, 400, missing_query.data)

        self.auth(self.outsider)
        forbidden_index = self.client.post(
            RAG_INDEX_URL, {"document_id": self.document.id}, format="json"
        )
        self.assertEqual(forbidden_index.status_code, 403, forbidden_index.data)
        forbidden_search = self.client.post(
            RAG_SEARCH_URL, {"query": "登录", "project": self.project.id}, format="json"
        )
        self.assertEqual(forbidden_search.status_code, 403, forbidden_search.data)


class MCPApiTests(AIApiTestCase):
    def test_mcp_config_create_refresh_and_tool_list(self):
        self.auth(self.staff)
        created = self.client.post(
            MCP_CONFIGS_URL,
            {
                "name": "filesystem",
                "transport": "stdio",
                "server_config": {
                    "command": "npx",
                    "tools": [
                        {"name": "list_files", "description": "列出目录"},
                        {"name": "read_file", "description": "读取文件"},
                    ],
                },
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        config_id = created.data["id"]
        self.assertEqual(created.data["tool_count"], 0)

        refreshed = self.client.post(
            f"{MCP_CONFIGS_URL}{config_id}/refresh_tools/", format="json"
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.data)
        self.assertEqual(refreshed.data["count"], 2)
        self.assertEqual(refreshed.data["status"], "connected")
        self.assertEqual(MCPTool.objects.filter(config_id=config_id).count(), 2)

        tools = self.client.get(MCP_TOOLS_URL, {"config": config_id})
        self.assertEqual(tools.status_code, 200)
        self.assertEqual(tools.data["count"], 2)

    def test_mcp_config_permissions(self):
        self.auth(self.editor)
        denied = self.client.post(
            MCP_CONFIGS_URL,
            {"project": self.project.id, "name": "editor-mcp", "transport": "sse"},
            format="json",
        )
        self.assertEqual(denied.status_code, 403, denied.data)

        self.auth(self.owner)
        allowed = self.client.post(
            MCP_CONFIGS_URL,
            {"project": self.project.id, "name": "owner-mcp", "transport": "sse",
             "server_config": {"tools": ["ping"]}},
            format="json",
        )
        self.assertEqual(allowed.status_code, 201, allowed.data)
        refreshed = self.client.post(
            f"{MCP_CONFIGS_URL}{allowed.data['id']}/refresh_tools/", format="json"
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.data)
        self.assertEqual(refreshed.data["count"], 1)


class UsageApiTests(AIApiTestCase):
    def setUp(self):
        super().setUp()
        self.manager = ModelManager()
        self.manager.chat(
            [{"role": "user", "content": "生成用例"}],
            project=self.project,
            agent_name="api_testcase",
            task_type="api_testcase",
            task_id=1,
        )
        self.manager.chat(
            [{"role": "user", "content": "生成场景"}],
            agent_name="api_scenario",
            task_type="api_scenario",
            task_id=2,
        )
        self.failed_log = LLMUsageLog.objects.create(
            agent_name="api_testcase",
            task_type="api_testcase",
            success=False,
            error_message="boom",
        )

    def test_usage_log_filters(self):
        self.auth(self.owner)
        by_agent = self.client.get(USAGE_LOGS_URL, {"agent": "api_testcase"})
        self.assertEqual(by_agent.status_code, 200)
        self.assertEqual(by_agent.data["count"], 2)
        self.assertTrue(
            all(row["agent_name"] == "api_testcase" for row in by_agent.data["results"])
        )

        failures = self.client.get(USAGE_LOGS_URL, {"success": "false"})
        self.assertEqual(failures.status_code, 200)
        self.assertEqual(failures.data["count"], 1)
        self.assertFalse(failures.data["results"][0]["success"])

        today = timezone.localdate().isoformat()
        recent = self.client.get(USAGE_LOGS_URL, {"date_from": today})
        self.assertEqual(recent.status_code, 200)
        self.assertEqual(recent.data["count"], 3)

        invalid_date = self.client.get(USAGE_LOGS_URL, {"date_from": "not-a-date"})
        self.assertEqual(invalid_date.status_code, 400, invalid_date.data)

    def test_usage_logs_are_project_scoped(self):
        outsider_log = LLMUsageLog.objects.create(agent_name="outsider_agent")
        self.auth(self.outsider)
        response = self.client.get(USAGE_LOGS_URL)
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(outsider_log.id, ids)
        self.assertIn(self.failed_log.id, ids)  # global log is visible
        project_logs = LLMUsageLog.objects.filter(project=self.project).count()
        self.assertEqual(project_logs, 1)
        self.assertNotIn(
            LLMUsageLog.objects.filter(project=self.project).first().id, ids
        )

    def test_usage_stats_aggregation(self):
        self.auth(self.owner)
        response = self.client.get(USAGE_STATS_URL)
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data
        self.assertEqual(data["total"]["requests"], 3)
        self.assertEqual(data["total"]["failed"], 1)
        self.assertGreater(data["total"]["total_tokens"], 0)
        self.assertTrue(data["by_day"])
        self.assertEqual(len(data["by_day"]), 1)
        agent_names = {row["agent"] for row in data["by_agent"]}
        self.assertEqual(agent_names, {"api_testcase", "api_scenario"})
        model_rows = data["by_model"]
        self.assertGreaterEqual(len(model_rows), 1)
        self.assertEqual(model_rows[0]["model"], "mock")

        by_agent = self.client.get(USAGE_STATS_URL, {"agent": "api_scenario"})
        self.assertEqual(by_agent.status_code, 200)
        self.assertEqual(by_agent.data["total"]["requests"], 1)
