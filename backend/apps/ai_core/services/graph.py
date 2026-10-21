"""Agent 图编排层：内置实现 + 可选 LangGraph，二者语义兼容。

引擎选择
--------
``settings.AITS_AGENT_ENGINE``：

* ``auto``（默认）：安装了 ``langgraph`` 就用真实库，否则用内置实现；
* ``builtin``：强制使用内置实现（离线 / 无第三方依赖环境）；
* ``langgraph``：强制使用 LangGraph（未安装时告警并回退内置，保证服务可启动）。

兼容性保证
----------
业务代码只依赖 :func:`get_stategraph`，两种引擎行为一致：

* 同一套建图 API：``add_node / add_edge / add_conditional_edges /
  set_entry_point / compile().invoke()``；
* 同样的**编译期校验**（入口点、未注册节点、条件分支目标），失败抛
  ``BusinessError(code="invalid_graph")``；
* 同样的**步数保护**：超过 ``settings.AITS_MAX_AGENT_STEPS`` 抛
  ``BusinessError(code="agent_max_steps")``（LangGraph 的
  ``GraphRecursionError`` 会被翻译成同一错误码）；
* ``START`` / ``END`` 常量相同（``__start__`` / ``__end__``），
  因此 Agent 代码无需区分引擎。

内置实现本身仍是公开类 :class:`StateGraph`，现有测试与调用方不受影响。
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
VALID_ENGINES = ("auto", "builtin", "langgraph")

if LANGGRAPH_AVAILABLE:  # pragma: no cover - depends on optional dependency
    import warnings

    # langgraph 1.0.x emits this pending-deprecation warning on import; it is
    # noise for our usage (we never pass `allowed_objects`).
    warnings.filterwarnings("ignore", message=".*allowed_objects.*")


# ---------------------------------------------------------------------------
# engine resolution
# ---------------------------------------------------------------------------
def max_agent_steps() -> int:
    try:
        return max(1, int(getattr(settings, "AITS_MAX_AGENT_STEPS", 12)))
    except (TypeError, ValueError):
        return 12


def resolve_engine() -> str:
    """Return the effective engine: ``builtin`` or ``langgraph``."""
    try:
        configured = str(getattr(settings, "AITS_AGENT_ENGINE", "auto") or "auto").lower()
    except Exception:  # pragma: no cover - settings unavailable
        configured = "auto"
    if configured not in VALID_ENGINES:
        logger.warning("unknown AITS_AGENT_ENGINE=%r, using auto", configured)
        configured = "auto"
    if configured == "auto":
        return "langgraph" if LANGGRAPH_AVAILABLE else "builtin"
    if configured == "langgraph" and not LANGGRAPH_AVAILABLE:
        logger.warning(
            "AITS_AGENT_ENGINE=langgraph but the package is missing; "
            "falling back to the built-in engine"
        )
        return "builtin"
    return configured


# ---------------------------------------------------------------------------
# validation shared by both engines
# ---------------------------------------------------------------------------
def validate_graph_spec(nodes: dict, edges: dict, conditional_edges: dict,
                        entry_point: str | None) -> None:
    """Raise ``BusinessError(invalid_graph)`` for structurally broken graphs."""
    if not entry_point:
        raise BusinessError(message="未设置 entry point", code="invalid_graph")
    if entry_point not in nodes:
        raise BusinessError(
            message=f"entry point {entry_point} 未注册为节点", code="invalid_graph"
        )
    for source, targets in edges.items():
        if source not in (START,) and source not in nodes:
            raise BusinessError(message=f"边起点 {source} 未注册", code="invalid_graph")
        for target in targets:
            if target not in (END,) and target not in nodes:
                raise BusinessError(message=f"边终点 {target} 未注册", code="invalid_graph")
    for node, (router, mapping) in conditional_edges.items():
        if node not in nodes:
            raise BusinessError(message=f"条件边节点 {node} 未注册", code="invalid_graph")
        if not callable(router):
            raise BusinessError(message="router 必须可调用", code="invalid_graph")
        for target in (mapping or {}).values():
            if target not in (END,) and target not in nodes:
                raise BusinessError(
                    message=f"条件分支目标 {target} 未注册", code="invalid_graph"
                )


# ---------------------------------------------------------------------------
# built-in engine
# ---------------------------------------------------------------------------
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
        validate_graph_spec(self.nodes, self.edges, self.conditional_edges, self.entry_point)
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
        return max_agent_steps()

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


# ---------------------------------------------------------------------------
# LangGraph adapter (only used when the real engine is selected)
# ---------------------------------------------------------------------------
class _LangGraphCompiledAdapter:
    """Normalise LangGraph's runtime behaviour to the AITS contract."""

    def __init__(self, compiled, max_steps: int):
        self._compiled = compiled
        self._max_steps = max_steps

    def invoke(self, state: dict | None = None, config: dict | None = None) -> dict:
        payload = dict(state or {})
        runtime_config = dict(config or {})
        runtime_config.setdefault("recursion_limit", self._max_steps)
        try:
            result = self._compiled.invoke(payload, runtime_config)
        except BusinessError:
            raise
        except Exception as exc:  # translate engine specific failures
            if type(exc).__name__ in {"GraphRecursionError", "RecursionError"} or (
                "recursion limit" in str(exc).lower()
            ):
                raise BusinessError(
                    message=(
                        f"Agent 执行步数超过上限 {self._max_steps}（可能存在环路）"
                    ),
                    code="agent_max_steps",
                ) from exc
            raise
        if not isinstance(result, dict):
            raise BusinessError(
                message="图执行结果不是 dict", code="invalid_graph_state"
            )
        return result


class _GraphProxy:
    """Engine agnostic builder: records the spec, then delegates to the engine.

    Recording the structure lets both engines share ``validate_graph_spec`` so a
    broken graph fails with the same ``invalid_graph`` error before execution.
    """

    def __init__(self, state_schema, engine: str):
        self.engine = engine
        self.state_schema = state_schema
        self.nodes: dict[str, callable] = {}
        self.edges: dict[str, list[str]] = {}
        self.conditional_edges: dict[str, tuple[callable, dict | None]] = {}
        self.entry_point: str | None = None

        if engine == "langgraph":
            from langgraph.graph import StateGraph as RealStateGraph

            self._builder = RealStateGraph(state_schema or dict)
        else:
            self._builder = StateGraph(state_schema)

    # -- building ------------------------------------------------------
    def add_node(self, name: str, fn):
        if not name or name in (START, END):
            raise BusinessError(message=f"非法节点名称: {name}", code="invalid_graph")
        if not callable(fn):
            raise BusinessError(message=f"节点 {name} 必须可调用", code="invalid_graph")
        self.nodes[str(name)] = fn
        self._builder.add_node(str(name), fn)
        return self

    def add_edge(self, source: str, target: str):
        self.edges.setdefault(str(source), []).append(str(target))
        self._builder.add_edge(str(source), str(target))
        return self

    def add_conditional_edges(self, node: str, router, mapping: dict | None = None):
        if not callable(router):
            raise BusinessError(message="router 必须可调用", code="invalid_graph")
        if mapping is not None and not isinstance(mapping, dict):
            raise BusinessError(message="mapping 必须是 dict", code="invalid_graph")
        self.conditional_edges[str(node)] = (router, mapping)
        self._builder.add_conditional_edges(str(node), router, mapping)
        return self

    def set_entry_point(self, name: str):
        self.entry_point = str(name)
        self._builder.set_entry_point(str(name))
        return self

    # -- compilation ---------------------------------------------------
    def compile(self):
        validate_graph_spec(self.nodes, self.edges, self.conditional_edges, self.entry_point)
        try:
            compiled = self._builder.compile()
        except BusinessError:
            raise
        except ValueError as exc:
            raise BusinessError(
                message=f"编译 Agent 图失败: {exc}", code="invalid_graph"
            ) from exc
        if self.engine == "langgraph":
            return _LangGraphCompiledAdapter(compiled, max_agent_steps())
        return compiled


def get_stategraph(state_schema=None):
    """Return the graph builder for the configured engine.

    This is the only entry point business code (agents) should use.
    """
    engine = resolve_engine()
    if engine == "langgraph" and not LANGGRAPH_AVAILABLE:  # pragma: no cover
        engine = "builtin"
    return _GraphProxy(state_schema, engine)
