"""7 个 Agent + registry 的契约测试（全部走 Mock provider，离线）。"""

from __future__ import annotations

import yaml
from django.test import TestCase

from apps.ai_core.models import LLMUsageLog
from apps.ai_core.services.agents.base import BaseAgent
from apps.ai_core.services.agents.registry import (
    AGENTS,
    get_agent,
    list_agents,
    run_agent,
)
from apps.common.api.api_exception_handler import BusinessError
from apps.common.parsers.yaml_json import parse_yaml

EXPECTED_AGENTS = {
    "api_testcase",
    "api_scenario",
    "postman_translator",
    "webui_testcase",
    "webui_playwright",
    "midscene",
    "midscene_script",
}


class RegistryTests(TestCase):
    def test_registry_lists_seven_agents(self):
        agents = list_agents()
        self.assertEqual(len(agents), 7)
        self.assertEqual({agent["name"] for agent in agents}, EXPECTED_AGENTS)
        self.assertTrue(all(agent["description"] for agent in agents))
        self.assertEqual(set(AGENTS), EXPECTED_AGENTS)

    def test_get_agent_returns_fresh_instances_and_unknown_raises_404(self):
        first = get_agent("api_testcase")
        second = get_agent("api_testcase")
        self.assertIsInstance(first, BaseAgent)
        self.assertIsNot(first, second)
        with self.assertRaises(BusinessError) as ctx:
            get_agent("not_exists")
        self.assertEqual(ctx.exception.biz_code, "agent_not_found")
        self.assertEqual(ctx.exception.status_code, 404)


class AgentContractTests(TestCase):
    def test_api_testcase_agent_generates_four_types(self):
        endpoint = {
            "method": "POST",
            "path": "/api/users",
            "summary": "创建用户",
            "parameters": [
                {"name": "page", "in": "query", "required": True, "schema": {"type": "integer"}}
            ],
            "request_body": {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                        }
                    }
                }
            },
        }
        outcome = run_agent("api_testcase", {"endpoint": endpoint, "context": "用户中心"})
        self.assertEqual(outcome["status"], "success", outcome)
        cases = outcome["result"]["cases"]
        self.assertEqual(len(cases), 4)
        self.assertEqual(
            {case["test_type"] for case in cases},
            {"positive", "negative", "boundary", "security"},
        )
        for case in cases:
            self.assertIn("name", case)
            self.assertEqual(case["case_type"], "endpoint")
            self.assertEqual(case["request"]["method"], "POST")
            self.assertEqual(case["request"]["path"], "/api/users")
            self.assertTrue(case["assertions"])
        self.assertEqual(outcome["result"]["endpoint"]["path"], "/api/users")

    def test_api_scenario_agent_builds_steps(self):
        outcome = run_agent(
            "api_scenario",
            {
                "requirement": "用户登录后创建订单",
                "endpoints": [
                    {"method": "POST", "path": "/api/login", "summary": "登录"},
                    {"method": "POST", "path": "/api/orders", "summary": "创建订单"},
                ],
            },
        )
        self.assertEqual(outcome["status"], "success", outcome)
        scenario = outcome["result"]["scenario"]
        self.assertTrue(scenario["name"])
        self.assertTrue(scenario["description"])
        self.assertEqual(len(scenario["steps"]), 2)
        self.assertEqual(scenario["steps"][0]["request"]["method"], "POST")
        self.assertEqual(scenario["steps"][1]["request"]["path"], "/api/orders")
        for step in scenario["steps"]:
            self.assertIn("name", step)
            self.assertIn("request", step)
            self.assertIsInstance(step["assertions"], list)
            self.assertIsInstance(step["extract"], dict)
        step_nodes = [step["node"] for step in outcome["steps"]]
        self.assertEqual(step_nodes, ["prepare", "intent", "map_endpoints", "build_steps", "validate"])

    def test_postman_translator_rule_parsing(self):
        script = (
            'pm.test("status 200", function () { pm.response.to.have.status(200); });\n'
            'pm.test("id", function () { pm.expect(pm.response.json().data.id).to.eql(3); });\n'
            'pm.environment.set("token", pm.response.json().data.token);\n'
            'pm.environment.set("env", "dev");\n'
        )
        outcome = run_agent("postman_translator", {"script": script})
        self.assertEqual(outcome["status"], "success", outcome)
        result = outcome["result"]
        self.assertGreaterEqual(len(result["validations"]), 2)
        for validation in result["validations"]:
            self.assertIn("expression", validation)
            self.assertIn("expected", validation)
            self.assertIn("message", validation)
        self.assertIn("status_code", result["validations"][0]["expression"])
        self.assertEqual(result["variables"].get("env"), "dev")
        self.assertTrue(
            any(extract["name"] == "token" and extract["path"] == "data.token"
                for extract in result["extracts"])
        )

    def test_postman_translator_llm_fallback(self):
        outcome = run_agent(
            "postman_translator", {"script": "doSomethingCustom(); // no rule"}
        )
        self.assertEqual(outcome["status"], "success", outcome)
        result = outcome["result"]
        self.assertTrue(result["validations"])
        self.assertTrue(result["extracts"])

    def test_webui_testcase_agent_design_and_review(self):
        outcome = run_agent(
            "webui_testcase",
            {"requirement": "支持账号密码登录；密码错误提示", "base_url": "https://demo.test"},
        )
        self.assertEqual(outcome["status"], "success", outcome)
        cases = outcome["result"]["cases"]
        self.assertTrue(cases)
        for case in cases:
            self.assertTrue(case["name"])
            self.assertIn(case["priority"], {"high", "medium", "low"})
            self.assertTrue(case["steps"])
            for step in case["steps"]:
                self.assertEqual(
                    set(step.keys()), {"action", "target", "value", "expect"}
                )
        self.assertEqual(
            outcome["result"]["summary"]["total"], len(cases)
        )
        self.assertIn("design", [step["node"] for step in outcome["steps"]])
        self.assertIn("review", [step["node"] for step in outcome["steps"]])

    def test_webui_playwright_agent_script_compiles(self):
        payload = {
            "case": {
                "name": "登录",
                "steps": [
                    {"action": "goto", "target": "/login"},
                    {"action": "fill", "target": "#username", "value": "admin"},
                    {"action": "click", "target": "#submit"},
                    {"action": "expect", "target": ".welcome", "expect": "登录成功"},
                ],
            },
            "pom": {"pages": [{"name": "LoginPage"}]},
        }
        outcome = run_agent("webui_playwright", payload)
        self.assertEqual(outcome["status"], "success", outcome)
        script = outcome["result"]["script"]
        self.assertEqual(outcome["result"]["language"], "python")
        self.assertIn("from playwright.sync_api import", script)
        self.assertIn("#username", script)
        self.assertIn("LoginPage", script)
        compile(script, "<generated>", "exec")  # must be syntactically valid

    def test_midscene_agent_yaml_contract(self):
        outcome = run_agent(
            "midscene", {"requirement": "打开首页并点击登录按钮", "url": "https://demo.test"}
        )
        self.assertEqual(outcome["status"], "success", outcome)
        result = outcome["result"]
        self.assertEqual(result["script_type"], "yaml")
        document = parse_yaml(result["content"])
        self.assertEqual(document["target"], "https://demo.test")
        self.assertTrue(document["tasks"])
        for task in document["tasks"]:
            self.assertTrue(any(key in task["flow"][0] for key in ("ai", "aiAssert")))
            self.assertIn("flow", task)

    def test_midscene_script_agent_returns_content_and_actions(self):
        outcome = run_agent(
            "midscene_script",
            {
                "requirement": "打开首页并断言标题",
                "url": "https://demo.test",
                "steps": [
                    {"name": "打开", "action": "打开首页", "expect": "标题非空"},
                ],
            },
        )
        self.assertEqual(outcome["status"], "success", outcome)
        result = outcome["result"]
        document = yaml.safe_load(result["content"])
        self.assertEqual(document["target"], "https://demo.test")
        self.assertTrue(document["tasks"])
        self.assertTrue(result["actions"])
        for action in result["actions"]:
            self.assertIn("type", action)
            self.assertIn("instruction", action)
        self.assertIn("validate", [step["node"] for step in outcome["steps"]])

    def test_agent_usage_logged_with_task_context(self):
        outcome = run_agent(
            "api_testcase",
            {
                "endpoint": {"method": "GET", "path": "/api/ping"},
                "project_id": None,
            },
            stream_task_id="task-42",
        )
        self.assertEqual(outcome["status"], "success", outcome)
        self.assertGreater(outcome["usage"]["total_tokens"], 0)
        self.assertGreaterEqual(outcome["usage"]["calls"], 1)
        log = LLMUsageLog.objects.filter(agent_name="api_testcase").latest("id")
        self.assertEqual(log.task_id, "task-42")
        self.assertEqual(log.task_type, "api_testcase")

    def test_run_agent_flattens_result_keys_for_cross_module_use(self):
        outcome = run_agent(
            "webui_playwright",
            {"case": {"steps": [{"action": "goto", "target": "/home"}]}},
        )
        self.assertEqual(outcome["status"], "success", outcome)
        self.assertIn("script", outcome)  # flattened convenience copy
        self.assertEqual(outcome["script"], outcome["result"]["script"])
        self.assertIn("from playwright.sync_api import", outcome["script"])

        agent_outcome = run_agent("api_testcase", {"endpoint": {"path": "/x"}})
        self.assertIn("cases", agent_outcome)
        self.assertEqual(len(agent_outcome["cases"]), 4)

    def test_agent_error_contract(self):
        class BoomAgent(BaseAgent):
            name = "boom"
            description = "always fails"

            def compose_result(self, payload, llm_data, state):
                raise BusinessError(message="生成失败", code="boom_error")

        outcome = BoomAgent().run({})
        self.assertEqual(outcome["status"], "error")
        self.assertEqual(outcome["code"], "boom_error")
        self.assertIn("生成失败", outcome["error"])
