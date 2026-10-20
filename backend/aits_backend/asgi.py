"""ASGI entrypoint with HTTP + WebSocket routing."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aits_backend.settings")

# The HTTP application must be created before importing anything that touches
# the app registry.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.urls import path  # noqa: E402

from apps.common.websocket.consumers import TaskStatusConsumer  # noqa: E402
from apps.common.websocket.core import (  # noqa: E402
    WebSocketJWTAuthMiddlewareStack,
    websocket_urlpatterns,
)

# Each module may register additional websocket routes in its own
# ``routing.py``; they are collected into ``websocket_urlpatterns`` during app
# startup (see apps/common/websocket/core.py).
extra_patterns = [
    path("ws/task-status/<str:task_id>/", TaskStatusConsumer.as_asgi()),
]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": WebSocketJWTAuthMiddlewareStack(
            URLRouter(list(websocket_urlpatterns) + extra_patterns)
        ),
    }
)
