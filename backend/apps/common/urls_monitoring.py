from django.urls import path

from apps.common.views_metrics import health, metrics

urlpatterns = [
    path("health/", health, name="health"),
    path("metrics/", metrics, name="metrics"),
]
