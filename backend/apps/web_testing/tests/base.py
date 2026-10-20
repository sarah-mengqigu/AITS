"""Shared fixtures for the web_testing test suite."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.projects.models import Project, ProjectMember
from apps.web_testing.models import (
    WebElement,
    WebPage,
    WebUITestCase,
    WebUITestModule,
    WebUITestSuite,
)

User = get_user_model()

API = "/api/web-testing"


def step(action, **kwargs):
    data = {"action": action}
    data.update(kwargs)
    return data


class WebTestingBaseTestCase(TestCase):
    """Base class with an isolated artefact root and the usual cast of users."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="aits-web-testing-")
        tmp = Path(cls._tmpdir)
        cls._settings_override = override_settings(
            ALLURE_RESULTS_ROOT=tmp / "allure-results",
            REPORT_ROOT=tmp / "reports",
            AITS_EXECUTION_MODE="simulated",
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
            name="Web 项目", project_type="web", owner=self.owner
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
        return WebUITestModule.objects.create(
            project=self.project, parent=parent, name=name, order=order
        )

    def create_case(self, name="登录用例", steps=None, module=None, **kwargs):
        return WebUITestCase.objects.create(
            project=self.project,
            module=module,
            name=name,
            steps=steps if steps is not None else [
                step("goto", target="https://example.com/login"),
                step("click", target="登录按钮"),
            ],
            **kwargs,
        )

    def create_suite(self, name="冒烟套件", case_ids=None, **kwargs):
        return WebUITestSuite.objects.create(
            project=self.project,
            name=name,
            case_ids=case_ids if case_ids is not None else [],
            **kwargs,
        )

    def create_page(self, name="登录页", url="https://example.com/login"):
        return WebPage.objects.create(project=self.project, name=name, url=url)

    def create_element(self, page, name="登录按钮", locator_type="testid",
                       locator_value="login-btn", alternatives=None):
        return WebElement.objects.create(
            page=page,
            name=name,
            locator_type=locator_type,
            locator_value=locator_value,
            alternatives=alternatives or [],
        )
