"""WebSocket routing + JWT authentication tests (in-memory channel layer)."""

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from rest_framework_simplejwt.tokens import RefreshToken

from channels.layers import get_channel_layer

from aits_backend.asgi import application
from apps.common.websocket.core import WebSocketMessageService

User = get_user_model()


class WebSocketTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ws_user", email="ws@example.com", password="Passw0rd!"
        )
        self.token = str(RefreshToken.for_user(self.user).access_token)

    def _connect(self, url, token=None):
        async def run():
            communicator = WebsocketCommunicator(application, url)
            connected, _ = await communicator.connect()
            first = await communicator.receive_json_from() if connected else None
            return connected, first, communicator

        return async_to_sync(run)()

    def test_task_status_channel_receives_pushes(self):
        async def scenario():
            communicator = WebsocketCommunicator(
                application, f"/ws/task-status/42/?token={self.token}"
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            hello = await communicator.receive_json_from()
            self.assertEqual(hello["type"], "connected")

            # push through the channel layer (same path used by business code)
            layer = get_channel_layer()
            await layer.group_send(
                "task_42",
                {
                    "type": "send.event",
                    "payload": {
                        "type": "task_status",
                        "task_id": "42",
                        "status": "running",
                        "progress": 40,
                        "message": "执行中",
                        "extra": {},
                    },
                },
            )
            frame = await communicator.receive_json_from()
            self.assertEqual(frame["type"], "task_status")
            self.assertEqual(frame["task_id"], "42")
            self.assertEqual(frame["progress"], 40)
            await communicator.disconnect()

        async_to_sync(scenario)()

    @staticmethod
    def _push(task_id):
        WebSocketMessageService.push_task_status(task_id, "running", 40, "执行中")

    def test_stream_channel_broadcasts_agent_frames(self):
        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/scenario_generation-streaming/?token={self.token}&task_id=77",
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from()  # connected frame

            layer = get_channel_layer()
            await layer.group_send(
                "stream_scenario_generation_77",
                {
                    "type": "send.event",
                    "payload": {
                        "type": "stream_chunk",
                        "task_id": "77",
                        "chunk": "hello",
                    },
                },
            )
            frame = await communicator.receive_json_from()
            self.assertEqual(frame["type"], "stream_chunk")
            self.assertEqual(frame["chunk"], "hello")
            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_all_stream_channels_route(self):
        channels = [
            "scenario_generation",
            "midscene_script_generation",
            "webui_test_generation",
            "webui_auto_test",
        ]

        async def scenario():
            for channel in channels:
                communicator = WebsocketCommunicator(
                    application, f"/ws/{channel}-streaming/?token={self.token}"
                )
                connected, _ = await communicator.connect()
                self.assertTrue(connected, f"{channel} should connect")
                hello = await communicator.receive_json_from()
                self.assertEqual(hello["type"], "connected")
                await communicator.disconnect()

        async_to_sync(scenario)()

    def test_anonymous_connection_is_rejected(self):
        async def scenario():
            communicator = WebsocketCommunicator(
                application, "/ws/task-status/1/?token=invalid"
            )
            connected, _ = await communicator.connect()
            # The consumer accepts then closes with 4001 after an error frame.
            frame = await communicator.receive_json_from()
            self.assertEqual(frame["type"], "error")
            self.assertEqual(frame["code"], "unauthorized")
            await communicator.disconnect()

        async_to_sync(scenario)()
