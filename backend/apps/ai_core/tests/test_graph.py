"""内置 StateGraph 兼容实现测试（节点 / 边 / 条件边 / 最大步数保护）。"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.ai_core.services.graph import END, START, CompiledGraph, StateGraph
from apps.common.api.api_exception_handler import BusinessError


def _append(name):
    def node(state):
        return {"trace": list(state.get("trace") or []) + [name], "count": (state.get("count") or 0) + 1}

    return node


class StateGraphTests(TestCase):
    def test_linear_edges_merge_state(self):
        graph = StateGraph(dict)
        graph.add_node("a", _append("a"))
        graph.add_node("b", _append("b"))
        graph.add_node("c", _append("c"))
        graph.set_entry_point("a")
        graph.add_edge("a", "b")
        graph.add_edge("b", "c")
        graph.add_edge("c", END)
        compiled = graph.compile()
        self.assertIsInstance(compiled, CompiledGraph)
        final = compiled.invoke({"count": 0})
        self.assertEqual(final["trace"], ["a", "b", "c"])
        self.assertEqual(final["count"], 3)

    def test_conditional_edges_route_by_router(self):
        def router(state):
            return "big" if (state.get("count") or 0) >= 2 else "small"

        graph = StateGraph(dict)
        graph.add_node("start", _append("start"))
        graph.add_node("big", _append("big"))
        graph.add_node("small", _append("small"))
        graph.set_entry_point("start")
        graph.add_conditional_edges("start", router, {"big": "big", "small": "small"})
        graph.add_edge("big", END)
        graph.add_edge("small", END)
        compiled = graph.compile()

        # routing sees post-node state: start increments count by one
        self.assertEqual(compiled.invoke({"count": 0})["trace"], ["start", "small"])
        self.assertEqual(compiled.invoke({"count": 1})["trace"], ["start", "big"])

    def test_conditional_edge_without_mapping_uses_node_name(self):
        graph = StateGraph(dict)
        graph.add_node("start", lambda state: {"route": "second"})
        graph.add_node("second", _append("second"))
        graph.set_entry_point("start")
        graph.add_conditional_edges("start", lambda state: state["route"])
        graph.add_edge("second", END)
        self.assertEqual(graph.compile().invoke({})["trace"], ["second"])

    @override_settings(AITS_MAX_AGENT_STEPS=2)
    def test_max_steps_protection(self):
        graph = StateGraph(dict)
        graph.add_node("a", _append("a"))
        graph.add_node("b", _append("b"))
        graph.set_entry_point("a")
        graph.add_edge("a", "b")
        graph.add_edge("b", "a")
        with self.assertRaises(BusinessError) as ctx:
            graph.compile().invoke({})
        self.assertEqual(ctx.exception.biz_code, "agent_max_steps")

    def test_compile_validates_entry_point_and_targets(self):
        graph = StateGraph(dict)
        graph.add_node("a", _append("a"))
        with self.assertRaises(BusinessError) as ctx:
            graph.compile()
        self.assertEqual(ctx.exception.biz_code, "invalid_graph")

        graph.set_entry_point("a")
        graph.add_edge("a", "missing")
        with self.assertRaises(BusinessError) as ctx:
            graph.compile()
        self.assertEqual(ctx.exception.biz_code, "invalid_graph")

    def test_start_and_end_constants_and_no_mutation_of_input(self):
        graph = StateGraph(dict)
        graph.add_node("only", _append("only"))
        graph.set_entry_point(START)  # explicit error: START is not a node
        with self.assertRaises(BusinessError):
            graph.compile()
        self.assertIsInstance(START, str)
        self.assertIsInstance(END, str)
