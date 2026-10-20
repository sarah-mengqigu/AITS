"""AITS backend project package.

The Celery application is imported here so that shared_task decorators bind to
the same app as soon as Django loads.
"""

from .celery import app as celery_app  # noqa: F401

__all__ = ("celery_app",)
