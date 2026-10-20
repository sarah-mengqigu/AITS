"""Shared fixtures for the API 测试 test suite."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.api_testing.models import (
    APIEndpoint,
    APIModule,
    APISpecification,
    APITestCase,
    APITestSuite,
)
from apps.projects.models import Environment, Project, ProjectMember

User = get_user_model()


class APITestFixture(TestCase):
    """Base fixture: project roles, isolated report/media directories."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="aits-api-testing-")
        self.addCleanup(shutil.rmtree, self._tmpdir, True)
        overrides = override_settings(
            REPORT_ROOT=Path(self._tmpdir) / "reports",
            MEDIA_ROOT=Path(self._tmpdir) / "media",
            AITS_EXECUTION_MODE="simulated",
        )
        overrides.enable()
        self.addCleanup(overrides.disable)

        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="owner", email="owner@aits.test", password="Passw0rd!"
        )
        self.editor = User.objects.create_user(
            username="editor", email="editor@aits.test", password="Passw0rd!"
        )
        self.viewer = User.objects.create_user(
            username="viewer", email="viewer@aits.test", password="Passw0rd!"
        )
        self.outsider = User.objects.create_user(
            username="outsider", email="outsider@aits.test", password="Passw0rd!"
        )
        self.project = Project.objects.create(
            name="API Project", project_type="api", owner=self.owner
        )
        ProjectMember.objects.create(project=self.project, user=self.owner, role="owner")
        ProjectMember.objects.create(project=self.project, user=self.editor, role="editor")
        ProjectMember.objects.create(project=self.project, user=self.viewer, role="viewer")
        self.environment = Environment.objects.create(
            project=self.project,
            name="测试环境",
            env_type="test",
            base_url="https://env.example.com",
            variables={"stage": "dev"},
            is_default=True,
        )
        self.client.force_authenticate(self.owner)

    # -- factories ---------------------------------------------------------
    def create_spec(self, name="Demo Spec", source_type="openapi", **kwargs):
        return APISpecification.objects.create(
            project=self.project,
            name=name,
            source_type=source_type,
            version=kwargs.pop("version", "1.0.0"),
            base_url=kwargs.pop("base_url", "https://api.example.com"),
            spec_data=kwargs.pop("spec_data", {"format": "openapi3"}),
            **kwargs,
        )

    def create_module(self, name="用户模块", parent=None, spec=None, order=0):
        return APIModule.objects.create(
            project=self.project,
            spec=spec,
            parent=parent,
            name=name,
            order=order,
        )

    def create_endpoint(self, path="/pets", method="get", summary="宠物列表", **kwargs):
        return APIEndpoint.objects.create(
            project=self.project,
            spec=kwargs.pop("spec", None),
            module=kwargs.pop("module", None),
            path=path,
            method=method,
            summary=summary,
            parameters=kwargs.pop(
                "parameters",
                [{"name": "limit", "in": "query", "required": False, "type": "integer",
                  "example": 10}],
            ),
            request_body=kwargs.pop("request_body", {}),
            responses=kwargs.pop("responses", {"200": {"type": "object"}}),
            headers=kwargs.pop("headers", {"Accept": "application/json"}),
            **kwargs,
        )

    def create_case(self, name="用例", **kwargs):
        request_config = kwargs.pop(
            "request_config",
            {
                "method": "GET",
                "url": "/pets",
                "params": {"limit": 10},
                "headers": {"Accept": "application/json"},
                "mock_response": {"status_code": 200, "json": {"data": [{"id": 1}]}},
            },
        )
        assertions = kwargs.pop(
            "assertions",
            [{"type": "status_code", "expected": 200}],
        )
        return APITestCase.objects.create(
            project=self.project,
            name=name,
            case_type=kwargs.pop("case_type", "endpoint"),
            test_type=kwargs.pop("test_type", "positive"),
            request_config=request_config,
            assertions=assertions,
            extract=kwargs.pop("extract", {}),
            **kwargs,
        )

    def create_suite(self, cases=None, name="回归套件", **kwargs):
        cases = cases or []
        return APITestSuite.objects.create(
            project=self.project,
            name=name,
            description=kwargs.pop("description", "回归测试"),
            environment=kwargs.pop("environment", self.environment),
            case_ids=[case.id for case in cases],
            config=kwargs.pop("config", {}),
            **kwargs,
        )
