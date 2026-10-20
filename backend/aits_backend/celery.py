"""Celery application for AITS.

Broker/result backend default to Redis in production. In test / offline mode
Celery runs eagerly against an in-memory broker so the whole platform stays
verifiable without Redis.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aits_backend.settings")

app = Celery("aits")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):  # pragma: no cover - operational helper
    print(f"Request: {self.request!r}")
