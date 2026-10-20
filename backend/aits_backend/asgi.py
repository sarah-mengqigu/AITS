"""ASGI entrypoint with HTTP + WebSocket routing."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aits_backend.settings")

# The HTTP application must be created before importing anything that touches
# the app registry.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.urls import path  # noqa: E402

from apps.common.websocket.consumers import (  # noqa: E402
    MidsceneScriptStreamConsumer,
    ScenarioGenerationStreamConsumer,
    TaskStatusConsumer,
    WebUIAutoTestStreamConsumer,
    WebUITestGenerationStreamConsumer,
)
from apps.common.websocket.core import (  # noqa: E402
    WebSocketJWTAuthMiddlewareStack,
    websocket_urlpatterns,
)

# Streaming channels declared in the design document (v2 §3.3).
stream_urlpatterns = [
    path(
        "ws/scenario_generation-streaming/",
        ScenarioGenerationStreamConsumer.as_asgi(),
    ),
    path(
        "ws/midscene_script_generation-streaming/",
        MidsceneScriptStreamConsumer.as_asgi(),
    ),
    path(
        "ws/webui_test_generation-streaming/",
        WebUITestGenerationStreamConsumer.as_asgi(),
    ),
    path(
        "ws/webui_auto_test-streaming/",
        WebUIAutoTestStreamConsumer.as_asgi(),
    ),
]

task_urlpatterns = [
    path("ws/task-status/<str:task_id>/", TaskStatusConsumer.as_asgi()),
]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": WebSocketJWTAuthMiddlewareStack(
            URLRouter(list(websocket_urlpatterns) + stream_urlpatterns + task_urlpatterns)
        ),
    }
)
