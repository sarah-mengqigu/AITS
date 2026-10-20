"""Shared fixtures for the app_testing test suite (no network access)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.app_testing.models import (
    AppTestApplication,
    AppTestCase,
    AppTestModule,
    AppTestSuite,
)
from apps.projects.models import Project, ProjectMember

User = get_user_model()

API = "/api/app-testing"


def step(action, **kwargs):
    data = {"action": action, "target": "", "value": "", "expect": "",
            "description": ""}
    data.update(kwargs)
    return data


class AppTestingBaseTestCase(TestCase):
    """Base class with an isolated artefact root and the usual cast of users."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="aits-app-testing-")
        tmp = Path(cls._tmpdir)
        cls._settings_override = override_settings(
            REPORT_ROOT=tmp / "reports",
            AITS_EXECUTION_MODE="simulated",
            SONIC_BASE_URL="",
            SONIC_PROJECT_ID="",
            SONIC_USERNAME="",
            SONIC_PASSWORD="",
            SONIC_TOKEN="",
        )
        cls._settings_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._settings_override.disable()
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@x.com", "Passw0rd!")
        self.editor = User.objects.create_user("editor", "editor@x.com", "Passw0rd!")
        self.viewer = User.objects.create_user("viewer", "viewer@x.com", "Passw0rd!")
        self.outsider = User.objects.create_user("outsider", "out@x.com", "Passw0rd!")

        self.project = Project.objects.create(
            name="App 项目", project_type="app", owner=self.owner
        )
        ProjectMember.objects.create(project=self.project, user=self.editor, role="editor")
        ProjectMember.objects.create(project=self.project, user=self.viewer, role="viewer")

        self.owner_client = self._authenticated(self.owner)
        self.editor_client = self._authenticated(self.editor)
        self.viewer_client = self._authenticated(self.viewer)
        self.outsider_client = self._authenticated(self.outsider)
        self.anonymous_client = APIClient()

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _authenticated(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def create_module(self, name, parent=None, order=0):
        return AppTestModule.objects.create(
            project=self.project, parent=parent, name=name, order=order
        )

    def create_application(self, name="Demo App", platform="android",
                           package_name="com.demo.app", bundle_id="",
                           app_version="1.0.0"):
        return AppTestApplication.objects.create(
            project=self.project, name=name, platform=platform,
            package_name=package_name, bundle_id=bundle_id, app_version=app_version,
        )

    def create_case(self, name="登录成功", steps=None, module=None, application=None,
                    **kwargs):
        return AppTestCase.objects.create(
            project=self.project,
            module=module,
            application=application,
            name=name,
            steps=steps if steps is not None else [
                step("start_app", target="com.demo.app", expect="应用启动成功"),
                step("tap", target="登录按钮"),
                step("input", target="账号输入框", value="demo"),
                step("assert", target="首页标题", expect="首页展示"),
                step("stop_app", target="com.demo.app"),
            ],
            **kwargs,
        )

    def create_suite(self, name="冒烟套件", case_ids=None, **kwargs):
        return AppTestSuite.objects.create(
            project=self.project,
            name=name,
            case_ids=case_ids if case_ids is not None else [],
            device_config=kwargs.pop("device_config", {"udid": "emulator-5554",
                                                       "device_id": "d-1",
                                                       "platform": "android"}),
            **kwargs,
        )
