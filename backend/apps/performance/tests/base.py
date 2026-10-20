"""Shared fixtures for the 性能测试 test suite.

All tests run against ``AITS_EXECUTION_MODE=simulated`` with isolated report
directories, so no locust subprocess / network access is ever required.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.api_testing.models import APITestCase, APITestSuite
from apps.performance.models import (
    AiDiagnosisRecord,
    LoadConfiguration,
    PerformanceExecution,
    PerformanceScenario,
)
from apps.projects.models import Project, ProjectMember

User = get_user_model()


class PerformanceFixture(TestCase):
    """Users, projects (perf + linked API) and model factories."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="aits-performance-")
        self.addCleanup(shutil.rmtree, self._tmpdir, True)
        overrides = override_settings(
            REPORT_ROOT=Path(self._tmpdir) / "reports",
            MEDIA_ROOT=Path(self._tmpdir) / "media",
            AITS_EXECUTION_MODE="simulated",
            PROMETHEUS_SD_AUTO_UPDATE=True,
            PROMETHEUS_TARGETS_FILE=Path(self._tmpdir) / "targets.json",
            GRAFANA_AI_NOTIFY_RECEIVER_ID="",
            GRAFANA_AI_NOTIFY_RECEIVER_NAME_KEYWORD="AI测试部门群",
        )
        overrides.enable()
        self.addCleanup(overrides.disable)
        cache.clear()
        self.addCleanup(cache.clear)

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
            name="性能测试项目", project_type="perf", owner=self.owner
        )
        ProjectMember.objects.create(project=self.project, user=self.owner, role="owner")
        ProjectMember.objects.create(project=self.project, user=self.editor, role="editor")
        ProjectMember.objects.create(project=self.project, user=self.viewer, role="viewer")
        self.api_project = Project.objects.create(
            name="关联 API 项目", project_type="api", owner=self.owner
        )
        self.project.linked_api_projects.add(self.api_project)
        self.outsider_project = Project.objects.create(
            name="外部性能项目", project_type="perf", owner=self.outsider
        )
        self.client.force_authenticate(self.owner)

    # -- factories ---------------------------------------------------------
    def create_config(self, name="标准压测配置", **kwargs):
        return LoadConfiguration.objects.create(
            project=kwargs.pop("project", self.project),
            name=name,
            users=kwargs.pop("users", 10),
            spawn_rate=kwargs.pop("spawn_rate", 10.0),
            duration_seconds=kwargs.pop("duration_seconds", 30),
            host=kwargs.pop("host", "https://api.example.com"),
            config=kwargs.pop("config", {}),
            description=kwargs.pop("description", "压测配置"),
            **kwargs,
        )

    def create_api_case(self, name="用户列表", **kwargs):
        request_config = kwargs.pop(
            "request_config",
            {
                "method": "GET",
                "url": "/api/users",
                "params": {"limit": 10},
                "headers": {"Accept": "application/json"},
            },
        )
        return APITestCase.objects.create(
            project=kwargs.pop("project", self.api_project),
            name=name,
            request_config=request_config,
            assertions=kwargs.pop("assertions", [{"type": "status_code", "expected": 200}]),
            **kwargs,
        )

    def create_api_suite(self, cases=None, name="API 回归套件", **kwargs):
        cases = cases if cases is not None else [self.create_api_case()]
        return APITestSuite.objects.create(
            project=kwargs.pop("project", self.api_project),
            name=name,
            description=kwargs.pop("description", "性能场景来源套件"),
            case_ids=[case.id for case in cases],
            **kwargs,
        )

    def create_scenario(self, source_type="api_suite", **kwargs):
        suite = kwargs.pop("suite", None)
        case = kwargs.pop("case", None)
        if source_type == "api_suite" and suite is None:
            suite = self.create_api_suite()
        if source_type == "api_case" and case is None:
            case = self.create_api_case()
        return PerformanceScenario.objects.create(
            project=kwargs.pop("project", self.project),
            name=kwargs.pop("name", "首页压测场景"),
            description=kwargs.pop("description", "场景描述"),
            source_type=source_type,
            source_suite=suite,
            source_case=case,
            custom_script=kwargs.pop("custom_script", ""),
            config=kwargs.pop("config", None),
            variables=kwargs.pop("variables", {}),
            endpoint_count=kwargs.pop("endpoint_count", 0),
            **kwargs,
        )

    def create_execution(self, scenario=None, **kwargs):
        scenario = scenario or self.create_scenario()
        return PerformanceExecution.objects.create(
            project=scenario.project,
            scenario=scenario,
            config=kwargs.pop("config", None),
            name=kwargs.pop("name", "历史执行"),
            status=kwargs.pop("status", "passed"),
            trigger_type=kwargs.pop("trigger_type", "manual"),
            total_requests=kwargs.pop("total_requests", 0),
            avg_tps=kwargs.pop("avg_tps", 0.0),
            p50_response_time=kwargs.pop("p50_response_time", 0),
            p95_response_time=kwargs.pop("p95_response_time", 0),
            p99_response_time=kwargs.pop("p99_response_time", 0),
            error_rate=kwargs.pop("error_rate", 0.0),
            status_code_dist=kwargs.pop("status_code_dist", {}),
            summary=kwargs.pop("summary", {}),
            **kwargs,
        )

    def create_diagnosis(self, execution=None, **kwargs):
        return AiDiagnosisRecord.objects.create(
            project=kwargs.pop("project", self.project),
            execution=execution,
            source=kwargs.pop("source", "manual"),
            alert_name=kwargs.pop("alert_name", "错误率告警"),
            severity=kwargs.pop("severity", "warning"),
            diagnosis_content=kwargs.pop("diagnosis_content", "诊断内容"),
            status=kwargs.pop("status", "pending"),
            raw_payload=kwargs.pop("raw_payload", {}),
            **kwargs,
        )

    # -- auth helpers ------------------------------------------------------
    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def as_anonymous(self):
        self.client.force_authenticate(None)
        return self.client


def grafana_payload(alert_name="AITSHighErrorRate", severity="critical",
                    project_id=None, execution_id=None, status="firing"):
    """Build a realistic Grafana alerting webhook body."""
    labels = {"alertname": alert_name, "severity": severity, "job": "aits-backend"}
    if project_id is not None:
        labels["project_id"] = str(project_id)
    if execution_id is not None:
        labels["execution_id"] = str(execution_id)
    return {
        "receiver": "aits-ai-diagnosis",
        "status": status,
        "alerts": [
            {
                "status": status,
                "labels": labels,
                "annotations": {
                    "summary": "错误率超过阈值",
                    "description": "最近 5 分钟错误率超过 30%",
                },
                "startsAt": "2025-01-01T00:00:00Z",
                "generatorURL": "http://grafana.local/alerting/1",
            }
        ],
        "externalURL": "http://grafana.local",
        "title": "[FIRING:1] AITS 性能告警",
    }
