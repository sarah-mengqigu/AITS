"""Shared helpers for the ai_core test suite."""

from __future__ import annotations

import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.projects.models import Project, ProjectMember


def create_user(username="tester", *, staff=False, superuser=False, password="Passw0rd!"):
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username=username, email=f"{username}@example.com", password=password
    )
    if staff or superuser:
        user.is_staff = True
        user.is_superuser = superuser
        user.save(update_fields=["is_staff", "is_superuser"])
    return user


def create_project(owner, name="测试项目", project_type="api"):
    project = Project.objects.create(name=name, project_type=project_type, owner=owner)
    ProjectMember.objects.get_or_create(
        project=project, user=owner, defaults={"role": "owner"}
    )
    return project


def add_member(project, user, role="editor"):
    return ProjectMember.objects.update_or_create(
        project=project, user=user, defaults={"role": role}
    )[0]


class TempMediaMixin:
    """Point ``settings.MEDIA_ROOT`` at a throw-away directory for RAG tests."""

    def setUp(self):
        super().setUp()
        self._media_dir = tempfile.mkdtemp(prefix="aits-ai-media-")
        self._media_override = override_settings(MEDIA_ROOT=self._media_dir)
        self._media_override.enable()
        self.addCleanup(self._media_override.disable)
        self.addCleanup(shutil.rmtree, self._media_dir, True)
