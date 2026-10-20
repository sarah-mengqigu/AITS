from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.notifications.views import (
    EmailConfigView,
    NotificationChannelViewSet,
    NotificationLogViewSet,
    NotificationReceiverViewSet,
    NotificationTestView,
)

router = DefaultRouter()
router.register("channels", NotificationChannelViewSet, basename="notification-channel")
router.register("receivers", NotificationReceiverViewSet, basename="notification-receiver")
router.register("logs", NotificationLogViewSet, basename="notification-log")

urlpatterns = [
    path("email-config/", EmailConfigView.as_view(), name="email-config"),
    path("test/", NotificationTestView.as_view(), name="notification-test"),
    path("", include(router.urls)),
]
