"""Minimal LangGraph compatible ``StateGraph``.

``langgraph`` 是**可选**依赖：本文件提供一个语义兼容的最小实现，
同样的 ``StateGraph / START / END / compile().invoke()`` 用法即可运行。

* 节点函数签名：``fn(state: dict) -> dict | None``，返回的 dict 合并进状态。
* ``add_conditional_edges(node, router, mapping)``：``router(state)`` 返回 key，
  ``mapping`` 把 key 映射到节点名（缺省时 key 直接就是节点名）。
* ``settings.AITS_MAX_AGENT_STEPS`` 保护死循环，超限抛
  ``BusinessError(code="agent_max_steps")``。
"""

from __future__ import annotations

import importlib.util
import logging

from django.conf import settings

from apps.common.api.api_exception_handler import BusinessError

logger = logging.getLogger(__name__)

START = "__start__"
END = "__end__"

LANGGRAPH_AVAILABLE = importlib.util.find_spec("langgraph") is not None


class StateGraph:
    """Declarative graph builder (compatible subset of LangGraph)."""

    def __init__(self, state_schema=None):
        self.state_schema = state_schema
        self.nodes: dict[str, callable] = {}
        self.edges: dict[str, list[str]] = {}
        self.conditional_edges: dict[str, tuple[callable, dict | None]] = {}
        self.entry_point: str | None = None

    # ------------------------------------------------------------------
    # building
    # ------------------------------------------------------------------
    def add_node(self, name: str, fn):
        if not name or name in (START, END):
            raise BusinessError(message=f"非法节点名称: {name}", code="invalid_graph")
        if not callable(fn):
            raise BusinessError(message=f"节点 {name} 必须可调用", code="invalid_graph")
        self.nodes[str(name)] = fn
        return self

    def add_edge(self, source: str, target: str):
        self.edges.setdefault(str(source), []).append(str(target))
        return self

    def add_conditional_edges(self, node: str, router, mapping: dict | None = None):
        if not callable(router):
            raise BusinessError(message="router 必须可调用", code="invalid_graph")
        if mapping is not None and not isinstance(mapping, dict):
            raise BusinessError(message="mapping 必须是 dict", code="invalid_graph")
        self.conditional_edges[str(node)] = (router, mapping)
        return self

    def set_entry_point(self, name: str):
        self.entry_point = str(name)
        return self

    # ------------------------------------------------------------------
    # compilation
    # ------------------------------------------------------------------
    def compile(self) -> "CompiledGraph":
        if not self.entry_point:
            raise BusinessError(message="未设置 entry point", code="invalid_graph")
        if self.entry_point not in self.nodes:
            raise BusinessError(
                message=f"entry point {self.entry_point} 未注册为节点", code="invalid_graph"
            )
        for source, targets in self.edges.items():
            if source not in (START,) and source not in self.nodes:
                raise BusinessError(message=f"边起点 {source} 未注册", code="invalid_graph")
            for target in targets:
                if target not in (END,) and target not in self.nodes:
                    raise BusinessError(
                        message=f"边终点 {target} 未注册", code="invalid_graph"
                    )
        for node, (router, mapping) in self.conditional_edges.items():
            if node not in self.nodes:
                raise BusinessError(
                    message=f"条件边节点 {node} 未注册", code="invalid_graph"
                )
            for target in (mapping or {}).values():
                if target not in (END,) and target not in self.nodes:
                    raise BusinessError(
                        message=f"条件分支目标 {target} 未注册", code="invalid_graph"
                    )
        return CompiledGraph(
            nodes=dict(self.nodes),
            edges={key: list(value) for key, value in self.edges.items()},
            conditional_edges=dict(self.conditional_edges),
            entry_point=self.entry_point,
            state_schema=self.state_schema,
        )


class CompiledGraph:
    """Executable graph returned by :meth:`StateGraph.compile`."""

    def __init__(self, nodes, edges, conditional_edges, entry_point, state_schema=None):
        self.nodes = nodes
        self.edges = edges
        self.conditional_edges = conditional_edges
        self.entry_point = entry_point
        self.state_schema = state_schema

    @property
    def max_steps(self) -> int:
        try:
            return max(1, int(getattr(settings, "AITS_MAX_AGENT_STEPS", 12)))
        except (TypeError, ValueError):
            return 12

    def _next_node(self, current: str, state: dict) -> str:
        if current in self.conditional_edges:
            router, mapping = self.conditional_edges[current]
            key = router(state)
            if mapping is not None:
                if key not in mapping:
                    raise BusinessError(
                        message=f"条件分支未映射: {key}", code="agent_route_error"
                    )
                return mapping[key]
            return key
        targets = self.edges.get(current) or []
        return targets[0] if targets else END

    def invoke(self, state: dict | None = None, config: dict | None = None) -> dict:
        """Run the graph and return the final merged state."""
        if state is None:
            state = {}
        if not isinstance(state, dict):
            raise BusinessError(message="state 必须是 dict", code="invalid_graph_state")
        # Copy so callers keep their input untouched; nodes mutate the copy.
        state = dict(state)
        max_steps = self.max_steps
        current = self.entry_point
        steps = 0
        visited: list[str] = []
        while current != END:
            steps += 1
            if steps > max_steps:
                raise BusinessError(
                    message=f"Agent 执行步数超过上限 {max_steps}（可能存在环路）",
                    code="agent_max_steps",
                )
            node = self.nodes.get(current)
            if node is None:
                raise BusinessError(
                    message=f"节点未注册: {current}", code="invalid_graph"
                )
            visited.append(current)
            update = node(state)
            if update is not None:
                if not isinstance(update, dict):
                    raise BusinessError(
                        message=f"节点 {current} 必须返回 dict 或 None", code="invalid_graph"
                    )
                state.update(update)
            current = self._next_node(current, state)
            if current == START:  # pragma: no cover - invalid wiring
                raise BusinessError(message="图不能回到 START", code="invalid_graph")
        state.setdefault("__visited__", visited)
        return state


def get_stategraph(state_schema=None):
    """Return the real LangGraph ``StateGraph`` when installed, else built-in.

    Business code (agents) uses the built-in implementation explicitly so that
    behaviour is identical whether or not ``langgraph`` is installed; this
    factory is exposed for callers that want the real library when present.
    """
    if LANGGRAPH_AVAILABLE:  # pragma: no cover - langgraph is optional
        try:
            from langgraph.graph import StateGraph as RealStateGraph

            return RealStateGraph(state_schema)
        except Exception as exc:
            logger.warning("langgraph import failed, using built-in graph: %s", exc)
    return StateGraph(state_schema)
