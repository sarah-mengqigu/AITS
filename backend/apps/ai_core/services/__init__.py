"""Public service layer of the AI 核心 module.

Other modules must depend only on the symbols exported here (see
``docs/ARCHITECTURE.md`` §2.7).
"""

from apps.ai_core.services.agents.base import BaseAgent
from apps.ai_core.services.agents.registry import (
    AGENTS,
    get_agent,
    list_agents,
    run_agent,
)
from apps.ai_core.services.graph import (
    END,
    START,
    CompiledGraph,
    StateGraph,
    get_stategraph,
    resolve_engine,
)
from apps.ai_core.services.llm_service import LLMResult, LLMService
from apps.ai_core.services.model_manager import ModelManager, get_model_manager
from apps.ai_core.services.rag_service import RAGService, embed_text, split_text

__all__ = [
    "AGENTS",
    "BaseAgent",
    "CompiledGraph",
    "END",
    "LLMResult",
    "LLMService",
    "ModelManager",
    "RAGService",
    "START",
    "StateGraph",
    "get_stategraph",
    "resolve_engine",
    "embed_text",
    "get_agent",
    "get_model_manager",
    "list_agents",
    "run_agent",
    "split_text",
]
