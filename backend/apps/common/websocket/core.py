"""WebSocket service layer shared by all AITS modules.

Design goals
------------
* JWT authentication from ``?token=<access>`` (browsers cannot set headers on WS).
* A reusable consumer base with groups, heartbeat, auth and JSON envelopes.
* A single push entrypoint (``WebSocketMessageService``) so business code never
  manipulates channel layers directly.
* A registry (``WebSocketConsumerFactory``) + ``websocket_urlpatterns`` list that
  app ``routing.py`` modules can append to.
"""

from __future__ import annotations

import json
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

logger = logging.getLogger(__name__)

# Populated by apps/common/apps.py at startup from every app's routing module.
websocket_urlpatterns: list = []


@database_sync_to_async
def _user_from_token(raw_token: str):
    from apps.users.models import User

    try:
        token = AccessToken(raw_token)
        user_id = token[token.get("user_id_claim", "user_id")]
        return User.objects.get(id=user_id, is_active=True)
    except (InvalidToken, TokenError, KeyError, User.DoesNotExist, TypeError):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """Resolve ``?token=`` (or ``Authorization``) into ``scope['user']``."""

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        token = self._extract_token(scope)
        scope["user"] = await _user_from_token(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)

    @staticmethod
    def _extract_token(scope) -> str | None:
        query = parse_qs((scope.get("query_string") or b"").decode("latin-1"))
        if query.get("token"):
            return query["token"][0]
        for header, value in scope.get("headers", []):
            if header == b"authorization":
                parts = value.decode("latin-1").split()
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    return parts[1]
        return None


def WebSocketJWTAuthMiddlewareStack(inner):  # noqa: N802 - public API name
    return JWTAuthMiddleware(inner)


class BaseWebSocketConsumer(AsyncJsonWebsocketConsumer):
    """Common consumer behaviour: auth guard, groups, heartbeat, envelopes."""

    group_name: str | None = None
    require_auth: bool = True

    async def connect(self):
        user = self.scope.get("user")
        if self.require_auth and (user is None or not getattr(user, "is_authenticated", False)):
            await self.accept()
            await self.send_json({"type": "error", "code": "unauthorized",
                                  "message": "WebSocket 鉴权失败，请提供有效 token"})
            await self.close(code=4001)
            return

        if self.group_name:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"type": "connected", "channel": self.group_name or ""})

    async def disconnect(self, code):
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = content.get("action") if isinstance(content, dict) else None
        if action == "ping":
            await self.send_json({"type": "pong"})
            return
        try:
            await self.handle_message(content)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("WS message failed: %s", exc)
            await self.send_json({"type": "error", "message": str(exc)})

    async def handle_message(self, content):
        """Override in subclasses to react to client messages."""
        await self.send_json({"type": "info", "message": "no handler registered"})

    async def send_event(self, event):
        """Handler name used by ``group_send``: ``{"type": "send.event"}``."""
        payload = event.get("payload", {})
        await self.send_json(payload)


class StreamingConsumerMixin:
    """Helpers to stream incremental agent output to a task group."""

    async def stream_start(self, task_id: str, title: str = ""):
        await self.send_json({"type": "stream_start", "task_id": task_id, "title": title})

    async def stream_chunk(self, task_id: str, chunk: str, node: str = ""):
        await self.send_json({"type": "stream_chunk", "task_id": task_id,
                              "node": node, "chunk": chunk})

    async def stream_node(self, task_id: str, node: str, status: str = "running",
                          detail: str = ""):
        await self.send_json({"type": "node", "task_id": task_id, "node": node,
                              "status": status, "detail": detail})

    async def stream_end(self, task_id: str, result=None):
        await self.send_json({"type": "stream_end", "task_id": task_id,
                              "result": result or {}})


class TaskStatusMixin:
    """Standard task status frames."""

    async def task_update(self, task_id: str, status: str, progress: int = 0,
                          message: str = "", extra: dict | None = None):
        await self.send_json(
            {
                "type": "task_status",
                "task_id": task_id,
                "status": status,
                "progress": progress,
                "message": message,
                "extra": extra or {},
            }
        )


class WebSocketMessageService:
    """Single push entrypoint used by synchronous business code."""

    @staticmethod
    def group_for_task(task_id: str) -> str:
        return f"task_{task_id}"

    @staticmethod
    def group_for_stream(channel: str, task_id: str) -> str:
        return f"stream_{channel}_{task_id}"

    @classmethod
    def push_to_group(cls, group_name: str, payload: dict) -> None:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            logger.debug("no channel layer configured, dropping ws payload")
            return
        try:
            async_to_sync(layer.group_send)(
                group_name, {"type": "send.event", "payload": payload}
            )
        except Exception as exc:  # pragma: no cover - broker failures are non fatal
            logger.warning("ws push to %s failed: %s", group_name, exc)

    @classmethod
    def push_task_status(cls, task_id, status, progress=0, message="", extra=None):
        cls.push_to_group(
            cls.group_for_task(task_id),
            {
                "type": "task_status",
                "task_id": str(task_id),
                "status": status,
                "progress": progress,
                "message": message,
                "extra": extra or {},
            },
        )

    @classmethod
    def push_stream(cls, stream_channel, task_id, payload):
        """Fan out a stream frame to the task-scoped and channel-wide groups."""
        cls.push_to_group(cls.group_for_stream(stream_channel, task_id), payload)
        cls.push_to_group(f"stream_{stream_channel}", payload)


class WebSocketConsumerFactory:
    """Registry helping modules expose stream-specific consumers."""

    _registry: dict[str, type] = {}

    @classmethod
    def register(cls, name: str, consumer_cls: type):
        cls._registry[name] = consumer_cls
        return consumer_cls

    @classmethod
    def get(cls, name: str):
        return cls._registry.get(name)

    @classmethod
    def all(cls):
        return dict(cls._registry)


def dumps(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)
