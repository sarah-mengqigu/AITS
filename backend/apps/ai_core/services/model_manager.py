"""Model selection + LLM invocation facade used by every agent / business module.

``ModelManager`` resolves the right ``LLMConfiguration`` (project default first,
then global default), delegates to :class:`LLMService` and makes sure usage is
recorded with ``agent_name`` / ``task_type`` / ``task_id`` context.
"""

from __future__ import annotations

import logging

from django.db import DatabaseError

from apps.ai_core.services.llm_service import LLMResult, LLMService

logger = logging.getLogger(__name__)


class ModelManager:
    """Resolve and call the configured text / vision model."""

    def _queryset(self, model_type: str):
        from apps.ai_core.models import LLMConfiguration

        return LLMConfiguration.objects.filter(is_active=True, model_type=model_type)

    def _pick(self, project, model_type: str):
        try:
            queryset = self._queryset(model_type)
        except (DatabaseError, Exception) as exc:  # pragma: no cover - defensive
            logger.warning("cannot load LLMConfiguration: %s", exc)
            return None

        ordering = ("-updated_at", "-id")
        if project is not None:
            config = queryset.filter(project=project, is_default=True).order_by(*ordering).first()
            if config is not None:
                return config
        config = (
            queryset.filter(project__isnull=True, is_default=True).order_by(*ordering).first()
        )
        if config is not None:
            return config
        if project is not None:
            config = queryset.filter(project=project).order_by(*ordering).first()
            if config is not None:
                return config
        return queryset.filter(project__isnull=True).order_by(*ordering).first()

    def get_text_model(self, project=None):
        return self._pick(project, "text")

    def get_vision_model(self, project=None):
        return self._pick(project, "vision")

    # ------------------------------------------------------------------
    # chat
    # ------------------------------------------------------------------
    def chat(
        self,
        messages,
        project=None,
        agent_name: str = "",
        task_type: str = "",
        task_id=None,
        **kwargs,
    ) -> LLMResult:
        """Select a model, call it and record token usage.

        ``kwargs`` accepts ``temperature`` / ``max_tokens`` / ``response_format``.
        Missing configuration degrades to the deterministic Mock provider.
        """
        config = self.get_text_model(project)
        service = LLMService(config=config, project=project)
        service.agent_name = agent_name or ""
        service.task_type = task_type or (agent_name or "")
        service.task_id = task_id
        allowed = {}
        for key in ("temperature", "max_tokens", "response_format"):
            if key in kwargs and kwargs[key] is not None:
                allowed[key] = kwargs[key]
        return service.chat(messages, **allowed)

    def chat_with_config(
        self,
        config,
        messages,
        project=None,
        agent_name: str = "",
        task_type: str = "",
        task_id=None,
        **kwargs,
    ) -> LLMResult:
        """Call one explicit configuration (used by ``/llm-configs/{id}/test/``)."""
        service = LLMService(config=config, project=project if project is not None
                             else getattr(config, "project", None))
        service.agent_name = agent_name or "config_test"
        service.task_type = task_type or "connectivity"
        service.task_id = task_id
        allowed = {
            key: kwargs[key]
            for key in ("temperature", "max_tokens", "response_format")
            if kwargs.get(key) is not None
        }
        return service.chat(messages, **allowed)


_MANAGER: ModelManager | None = None


def get_model_manager() -> ModelManager:
    """Module level singleton."""
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = ModelManager()
    return _MANAGER
