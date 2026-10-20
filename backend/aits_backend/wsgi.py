"""WSGI entrypoint (used by gunicorn / simple deployments)."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aits_backend.settings")

application = get_wsgi_application()
