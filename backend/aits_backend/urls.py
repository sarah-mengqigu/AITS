"""Root URL configuration.

Each business app owns its own ``urls.py``; this file only fixes the public API
prefixes. Module developers MUST NOT edit this file - extend your app router
instead (see ``docs/ARCHITECTURE.md``).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # auth & users
    path("api/auth/", include("apps.users.urls_auth")),
    path("api/users/", include("apps.users.urls")),
    # business modules
    path("api/projects/", include("apps.projects.urls")),
    path("api/api-testing/", include("apps.api_testing.urls")),
    path("api/web-testing/", include("apps.web_testing.urls")),
    path("api/app-testing/", include("apps.app_testing.urls")),
    path("api/performance/", include("apps.performance.urls")),
    path("api/ai/", include("apps.ai_core.urls")),
    path("api/scheduled-tasks/", include("apps.scheduled_tasks.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
    # observability
    path("api/monitoring/", include("apps.common.urls_monitoring")),
    path("", include("apps.common.urls_monitoring")),
    # OpenAPI schema / docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
