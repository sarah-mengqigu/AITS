"""双引擎兼容性测试：内置 StateGraph 与真实 LangGraph 行为必须一致。

覆盖三件事：
1. 引擎选择（auto / builtin / langgraph 的回退规则）；
2. 7 个 Agent 在两种引擎下的输出**逐字节相同**、节点顺序相同；
3. 异常语义一致：非法图 → ``invalid_graph``，超步数 → ``agent_max_steps``。
"""

from __future__ import annotations

import json
import unittest

from django.test import TestCase, override_settings

from apps.ai_core.services.agents.registry import run_agent
from apps.ai_core.services.graph import (
    END,
    LANGGRAPH_AVAILABLE,
    get_stategraph,
    resolve_engine,
)
from apps.common.api.api_exception_handler import BusinessError

ENGINES = ("builtin", "langgraph") if LANGGRAPH_AVAILABLE else ("builtin",)

AGENT_PAYLOADS: dict[str, dict] = {
    "api_testcase": {
        "endpoint": {
            "method": "POST",
            "path": "/api/users",
            "summary": "创建用户",
            "parameters": [
                {"name": "page", "in": "query", "required": True,
                 "schema": {"type": "integer"}}
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
        },
        "context": "用户中心",
    },
    "api_scenario": {
        "requirement": "用户先创建商品再下单并查询订单详情",
        "endpoints": [
            {"method": "GET", "path": "/api/v1/products", "summary": "商品列表",
             "parameters": [], "request_body": None},
            {"method": "POST", "path": "/api/v1/products", "summary": "创建商品",
             "parameters": [], "request_body": {"type": "object"}},
            {"method": "POST", "path": "/api/v1/orders", "summary": "下单",
             "parameters": [], "request_body": {"type": "object"}},
            {"method": "GET", "path": "/api/v1/users/{userId}", "summary": "用户详情",
             "parameters": [{"name": "userId", "in": "path", "example": "42"}]},
        ],
    },
    "postman_translator": {
        "script": (
            "pm.test('status ok', function () { pm.response.to.have.status(200); });\n"
            "pm.test('id exists', function () { pm.expect(pm.response.json().id).to.not.eql(null); });\n"
            "pm.environment.set('token', pm.response.json().token);"
        )
    },
    "webui_testcase": {
        "requirement": "支持账号密码登录；密码错误提示",
        "base_url": "https://demo.test",
    },
    "webui_playwright": {
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
    },
    "midscene": {
        "requirement": "打开首页并点击登录按钮",
        "url": "https://demo.test",
    },
    "midscene_script": {
        "requirement": "打开首页并断言标题",
        "url": "https://demo.test",
        "steps": [{"name": "打开", "action": "打开首页", "expect": "标题非空"}],
    },
}


class EngineSelectionTests(TestCase):
    def test_auto_prefers_langgraph_when_installed(self):
        with override_settings(AITS_AGENT_ENGINE="auto"):
            self.assertEqual(
                resolve_engine(), "langgraph" if LANGGRAPH_AVAILABLE else "builtin"
            )

    def test_builtin_is_enforced(self):
        with override_settings(AITS_AGENT_ENGINE="builtin"):
            self.assertEqual(resolve_engine(), "builtin")
            self.assertEqual(get_stategraph(dict).engine, "builtin")

    def test_langgraph_falls_back_when_package_missing(self):
        with override_settings(AITS_AGENT_ENGINE="langgraph"):
            expected = "langgraph" if LANGGRAPH_AVAILABLE else "builtin"
            self.assertEqual(resolve_engine(), expected)

    def test_unknown_value_falls_back_to_auto(self):
        with override_settings(AITS_AGENT_ENGINE="something-else"):
            self.assertEqual(
                resolve_engine(), "langgraph" if LANGGRAPH_AVAILABLE else "builtin"
            )

    def test_get_stategraph_uses_selected_engine(self):
        for engine in ENGINES:
            with self.subTest(engine=engine), override_settings(AITS_AGENT_ENGINE=engine):
                self.assertEqual(get_stategraph(dict).engine, engine)


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph is not installed")
class AgentEngineParityTests(TestCase):
    """Same payload, same mock model → the two engines must agree exactly."""

    def _run(self, engine: str, name: str, payload: dict) -> dict:
        with override_settings(AITS_AGENT_ENGINE=engine):
            return run_agent(name, payload)

    def test_all_agents_produce_identical_results(self):
        for name, payload in AGENT_PAYLOADS.items():
            with self.subTest(agent=name):
                builtin = self._run("builtin", name, payload)
                langgraph = self._run("langgraph", name, payload)

                self.assertEqual(builtin["status"], "success", builtin)
                self.assertEqual(langgraph["status"], "success", langgraph)
                self.assertEqual(
                    json.dumps(builtin["result"], sort_keys=True, ensure_ascii=False),
                    json.dumps(langgraph["result"], sort_keys=True, ensure_ascii=False),
                    f"{name}: engines produced different results",
                )
                self.assertEqual(
                    [step["node"] for step in builtin["steps"]],
                    [step["node"] for step in langgraph["steps"]],
                    f"{name}: engines executed different nodes",
                )

    def test_invalid_graph_is_rejected_before_execution(self):
        for engine in ENGINES:
            with self.subTest(engine=engine), override_settings(AITS_AGENT_ENGINE=engine):
                graph = get_stategraph(dict)
                graph.add_node("a", lambda state: {})
                graph.set_entry_point("a")
                graph.add_edge("a", "missing")
                with self.assertRaises(BusinessError) as ctx:
                    graph.compile()
                self.assertEqual(ctx.exception.biz_code, "invalid_graph")

    def test_missing_entry_point_is_rejected(self):
        for engine in ENGINES:
            with self.subTest(engine=engine), override_settings(AITS_AGENT_ENGINE=engine):
                graph = get_stategraph(dict)
                graph.add_node("a", lambda state: {})
                with self.assertRaises(BusinessError) as ctx:
                    graph.compile()
                self.assertEqual(ctx.exception.biz_code, "invalid_graph")

    def test_step_limit_is_translated_to_business_error(self):
        for engine in ENGINES:
            with self.subTest(engine=engine), override_settings(
                AITS_AGENT_ENGINE=engine, AITS_MAX_AGENT_STEPS=3
            ):
                graph = get_stategraph(dict)
                graph.add_node("loop", lambda state: {"n": state.get("n", 0) + 1})
                graph.set_entry_point("loop")
                graph.add_conditional_edges("loop", lambda state: "again",
                                            {"again": "loop"})
                compiled = graph.compile()
                with self.assertRaises(BusinessError) as ctx:
                    compiled.invoke({"n": 0})
                self.assertEqual(ctx.exception.biz_code, "agent_max_steps")

    def test_conditional_routing_parity(self):
        def build():
            graph = get_stategraph(dict)
            graph.add_node("start", lambda state: {"path": state.get("path") or "left"})
            graph.add_node("left", lambda state: {"result": "L"})
            graph.add_node("right", lambda state: {"result": "R"})
            graph.set_entry_point("start")
            graph.add_conditional_edges(
                "start", lambda state: state.get("path"), {"left": "left", "right": "right"}
            )
            graph.add_edge("left", END)
            graph.add_edge("right", END)
            return graph.compile()

        outputs = {}
        for engine in ENGINES:
            with override_settings(AITS_AGENT_ENGINE=engine):
                outputs[engine] = build().invoke({"path": "right"})["result"]
        self.assertEqual(set(outputs.values()), {"R"})
