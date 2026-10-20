"""Concrete WebSocket consumers shared by all modules."""

import logging

from .core import BaseWebSocketConsumer, StreamingConsumerMixin, TaskStatusMixin

logger = logging.getLogger(__name__)


class TaskStatusConsumer(TaskStatusMixin, BaseWebSocketConsumer):
    """``ws/task-status/<task_id>/`` - generic task progress channel."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_id = None

    async def connect(self):
        self.task_id = self.scope["url_route"]["kwargs"].get("task_id")
        self.group_name = f"task_{self.task_id}"
        await super().connect()

    async def handle_message(self, content):
        action = content.get("action") if isinstance(content, dict) else None
        if action == "subscribe":
            await self.send_json({"type": "subscribed", "task_id": self.task_id})
        elif action == "current":
            await self.send_json({"type": "task_status", "task_id": self.task_id,
                                  "status": "unknown", "progress": 0})
        else:
            await super().handle_message(content)


class StreamConsumer(StreamingConsumerMixin, TaskStatusMixin, BaseWebSocketConsumer):
    """Base class for ``ws/<name>-streaming/`` agent output channels.

    Clients may scope the subscription with ``?task_id=<id>`` (only events of
    that task are delivered) or omit it to receive every event of the channel.
    """

    stream_channel = "generic"

    async def connect(self):
        from urllib.parse import parse_qs

        query = parse_qs((self.scope.get("query_string") or b"").decode("latin-1"))
        task_id = (query.get("task_id") or [""])[0]
        self.stream_task_id = task_id
        self.group_name = (
            f"stream_{self.stream_channel}_{task_id}"
            if task_id
            else f"stream_{self.stream_channel}"
        )
        await super().connect()

    async def handle_message(self, content):
        if isinstance(content, dict) and content.get("action") == "cancel":
            await self.send_json({"type": "cancelled", "channel": self.stream_channel})
            return
        await super().handle_message(content)


class ScenarioGenerationStreamConsumer(StreamConsumer):
    stream_channel = "scenario_generation"


class MidsceneScriptStreamConsumer(StreamConsumer):
    stream_channel = "midscene_script_generation"


class WebUITestGenerationStreamConsumer(StreamConsumer):
    stream_channel = "webui_test_generation"


class WebUIAutoTestStreamConsumer(StreamConsumer):
    stream_channel = "webui_auto_test"
