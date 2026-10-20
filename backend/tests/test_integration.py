"""Cross-module end-to-end integration test.

This exercises the real URL routing, authentication, permissions and the whole
business chain a QA engineer goes through:

    register -> login -> project -> environment
    -> import OpenAPI spec -> generate cases -> run API suite
    -> Web UI case + suite -> run
    -> App case + suite -> run (Sonic not configured => simulated)
    -> Performance scenario -> run (simulated Locust)
    -> AI model config -> agent run
    -> notification receiver -> scheduled task -> run -> log + notification
    -> health / metrics

Every external dependency is either mocked or runs in simulated mode, so the
test is deterministic and offline.
"""

import io
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()

OPENAPI_SPEC = """openapi: 3.0.3
info:
  title: Pet Store
  version: 1.0.0
servers:
  - url: https://petstore.example.com
paths:
  /pets:
    get:
      operationId: listPets
      summary: List pets
      parameters:
        - name: limit
          in: query
          required: false
          schema:
            type: integer
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: integer
                    name:
                      type: string
    post:
      operationId: createPet
      summary: Create pet
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                name:
                  type: string
              required: [name]
      responses:
        '201':
          description: created
  /pets/{petId}:
    get:
      operationId: getPet
      summary: Get one pet
      parameters:
        - name: petId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: ok
"""

LOOPBACK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=integration"


class IntegrationFlowTests(TestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="qa_lead", email="qa_lead@example.com", password="Passw0rd!",
            nickname="QA Lead",
        )

    def setUp(self):
        self.client = APIClient()
        resp = self.client.post(
            "/api/auth/login/",
            {"username": "qa_lead", "password": "Passw0rd!"},
            format="json",
        )
        assert resp.status_code == 200, resp.data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
        self.project = self._create_project("E2E API Project", "api")
        self.env = self._create_environment(self.project)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _create_project(self, name, project_type, **extra):
        payload = {"name": name, "project_type": project_type, "description": "e2e"}
        payload.update(extra)
        resp = self.client.post("/api/projects/", payload, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        return resp.data

    def _create_environment(self, project):
        resp = self.client.post(
            "/api/projects/environments/",
            {
                "project": project["id"],
                "name": "e2e-test",
                "env_type": "test",
                "base_url": "https://petstore.example.com",
                "variables": {"tenant": "demo"},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        return resp.data

    def _import_spec(self, project):
        upload = io.BytesIO(OPENAPI_SPEC.encode())
        upload.name = "petstore.yaml"
        resp = self.client.post(
            "/api/api-testing/specs/import/",
            {"project": project["id"], "file": upload, "base_url": "https://petstore.example.com"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        return resp.data

    def _gen_cases(self, project):
        endpoints = self.client.get(
            f"/api/api-testing/endpoints/?project={project['id']}"
        )
        self.assertEqual(endpoints.status_code, 200)
        results = endpoints.data["results"]
        self.assertGreaterEqual(len(results), 3)
        created = 0
        for endpoint in results:
            resp = self.client.post(
                f"/api/api-testing/endpoints/{endpoint['id']}/generate_cases/",
                {},
                format="json",
            )
            self.assertIn(resp.status_code, (200, 201), resp.data)
            created += int(resp.data.get("created", 0) or 0)
        self.assertGreater(created, 0)
        cases = self.client.get(f"/api/api-testing/cases/?project={project['id']}")
        return cases.data["results"]

    # ------------------------------------------------------------------
    # 1. auth + project + environment
    # ------------------------------------------------------------------
    def test_01_auth_project_environment(self):
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["username"], "qa_lead")

        self.assertEqual(self.project["project_type"], "api")
        self.assertTrue(self.env["is_default"])
        stats = self.client.get(f"/api/projects/{self.project['id']}/stats/")
        self.assertEqual(stats.status_code, 200)

    # ------------------------------------------------------------------
    # 2. OpenAPI import + case generation
    # ------------------------------------------------------------------
    def test_02_spec_import_and_case_generation(self):
        spec = self._import_spec(self.project)
        self.assertGreaterEqual(spec.get("endpoint_count", 0), 3)

        endpoints = self.client.get(
            f"/api/api-testing/endpoints/?project={self.project['id']}"
        ).data["results"]
        methods = {item["method"].lower() for item in endpoints}
        self.assertIn("get", methods)
        self.assertIn("post", methods)

        cases = self._gen_cases(self.project)
        test_types = {case["test_type"] for case in cases}
        self.assertIn("positive", test_types)
        self.assertTrue(len(cases) >= 4)

        # generated script is a valid HttpRunner YAML document
        case = cases[0]
        script = self.client.post(f"/api/api-testing/cases/{case['id']}/generate_script/")
        self.assertEqual(script.status_code, 200, script.data)
        yaml_text = script.data.get("script_yaml") or script.data.get("script") or ""
        self.assertIn("teststeps", yaml_text)
        import yaml

        parsed = yaml.safe_load(yaml_text)
        self.assertIn("config", parsed)

    # ------------------------------------------------------------------
    # 3. API suite execution
    # ------------------------------------------------------------------
    def test_03_api_suite_execution(self):
        self._import_spec(self.project)
        cases = self._gen_cases(self.project)
        resp = self.client.post(
            "/api/api-testing/suites/",
            {
                "project": self.project["id"],
                "name": "smoke suite",
                "case_ids": [case["id"] for case in cases[:4]],
                "environment": self.env["id"],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        suite_id = resp.data["id"]

        run = self.client.post(f"/api/api-testing/suites/{suite_id}/run/", {}, format="json")
        self.assertEqual(run.status_code, 202, run.data)

        execution_id = run.data.get("execution_id") or run.data.get("task_id")
        detail = self.client.get(f"/api/api-testing/executions/{execution_id}/")
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertIn(detail.data["status"], {"passed", "failed"})
        self.assertNotEqual(detail.data["status"], "running")
        self.assertEqual(detail.data["total"], 4)
        self.assertGreaterEqual(len(detail.data.get("details") or detail.data.get("case_details") or []), 1)

        report = self.client.get(f"/api/api-testing/executions/{execution_id}/report/")
        self.assertEqual(report.status_code, 200, report.data)

    # ------------------------------------------------------------------
    # 4. Web UI suite execution (simulated, Allure artefacts)
    # ------------------------------------------------------------------
    def test_04_web_suite_execution(self):
        project = self._create_project("E2E Web Project", "web")
        env = self._create_environment(project)

        case_resp = self.client.post(
            "/api/web-testing/cases/",
            {
                "project": project["id"],
                "name": "登录流程",
                "description": "打开首页并登录",
                "steps": [
                    {"action": "goto", "target": "/login", "value": "", "expect": ""},
                    {"action": "fill", "target": "#username", "value": "demo"},
                    {"action": "click", "target": "#submit", "expect": "welcome"},
                ],
            },
            format="json",
        )
        self.assertEqual(case_resp.status_code, 201, case_resp.data)
        case_id = case_resp.data["id"]

        script = self.client.post(
            f"/api/web-testing/cases/{case_id}/generate_script/", {}, format="json"
        )
        self.assertEqual(script.status_code, 200, script.data)
        script_text = script.data.get("script") or script.data.get("content") or ""
        self.assertIn("playwright", script_text.lower())

        suite_resp = self.client.post(
            "/api/web-testing/suites/",
            {
                "project": project["id"],
                "name": "web smoke",
                "case_ids": [case_id],
                "environment": env["id"],
            },
            format="json",
        )
        self.assertEqual(suite_resp.status_code, 201, suite_resp.data)
        run = self.client.post(
            f"/api/web-testing/suites/{suite_resp.data['id']}/run/", {}, format="json"
        )
        self.assertEqual(run.status_code, 202, run.data)
        execution_id = run.data.get("execution_id") or run.data.get("task_id")
        detail = self.client.get(f"/api/web-testing/executions/{execution_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertIn(detail.data["status"], {"passed", "failed"})
        self.assertEqual(detail.data["total"], 1)

    # ------------------------------------------------------------------
    # 5. App suite execution (Sonic unconfigured => simulated)
    # ------------------------------------------------------------------
    def test_05_app_suite_execution_without_sonic(self):
        project = self._create_project("E2E App Project", "app")
        app_resp = self.client.post(
            "/api/app-testing/applications/",
            {
                "project": project["id"],
                "name": "Demo App",
                "platform": "android",
                "package_name": "com.example.demo",
                "app_version": "1.0.0",
            },
            format="json",
        )
        self.assertEqual(app_resp.status_code, 201, app_resp.data)

        case_resp = self.client.post(
            "/api/app-testing/cases/",
            {
                "project": project["id"],
                "application": app_resp.data["id"],
                "name": "启动并登录",
                "steps": [
                    {"action": "start_app", "target": "com.example.demo", "value": ""},
                    {"action": "tap", "target": "登录按钮", "value": ""},
                    {"action": "input", "target": "用户名", "value": "demo"},
                ],
            },
            format="json",
        )
        self.assertEqual(case_resp.status_code, 201, case_resp.data)
        self.assertTrue(case_resp.data.get("sonic_steps"))

        suite_resp = self.client.post(
            "/api/app-testing/suites/",
            {
                "project": project["id"],
                "name": "app smoke",
                "case_ids": [case_resp.data["id"]],
                "application": app_resp.data["id"],
            },
            format="json",
        )
        self.assertEqual(suite_resp.status_code, 201, suite_resp.data)
        run = self.client.post(
            f"/api/app-testing/suites/{suite_resp.data['id']}/run/", {}, format="json"
        )
        self.assertEqual(run.status_code, 202, run.data)
        run_id = run.data.get("run_id") or run.data.get("task_id")
        detail = self.client.get(f"/api/app-testing/runs/{run_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertIn(detail.data["status"], {"passed", "failed"})
        self.assertEqual(detail.data["total"], 1)

        # Sonic devices degrade gracefully
        devices = self.client.get(f"/api/app-testing/devices/?project={project['id']}")
        self.assertEqual(devices.status_code, 200)

    # ------------------------------------------------------------------
    # 6. Performance scenario execution
    # ------------------------------------------------------------------
    def test_06_performance_execution(self):
        from apps.performance.models import LoadConfiguration, PerformanceScenario

        project = self._create_project("E2E Perf Project", "perf")
        project_obj = self.client.get(f"/api/projects/{project['id']}/").data

        config_resp = self.client.post(
            "/api/performance/configs/",
            {
                "project": project["id"],
                "name": "10 users / 10s",
                "users": 10,
                "spawn_rate": 2,
                "duration_seconds": 10,
                "host": "https://petstore.example.com",
            },
            format="json",
        )
        self.assertEqual(config_resp.status_code, 201, config_resp.data)

        locust_script = (
            "from locust import HttpUser, task, between\n\n"
            "class WebsiteUser(HttpUser):\n"
            "    wait_time = between(1, 2)\n\n"
            "    @task\n"
            "    def index(self):\n"
            "        self.client.get('/pets')\n"
        )
        scenario_resp = self.client.post(
            "/api/performance/scenarios/",
            {
                "project": project["id"],
                "name": "custom load",
                "source_type": "custom_script",
                "custom_script": locust_script,
                "config": config_resp.data["id"],
                "endpoint_count": 1,
            },
            format="json",
        )
        self.assertEqual(scenario_resp.status_code, 201, scenario_resp.data)

        run = self.client.post(
            f"/api/performance/scenarios/{scenario_resp.data['id']}/run/",
            {},
            format="json",
        )
        self.assertEqual(run.status_code, 202, run.data)
        execution_id = run.data.get("execution_id") or run.data.get("task_id")
        detail = self.client.get(f"/api/performance/executions/{execution_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertIn(detail.data["status"], {"passed", "failed"})
        self.assertNotEqual(detail.data["status"], "running")
        self.assertGreater(detail.data["total_requests"], 0)

        dashboard = self.client.get(f"/api/performance/dashboard/?project={project['id']}")
        self.assertEqual(dashboard.status_code, 200)

        # model layer sanity (keeps DB constraints honest)
        self.assertTrue(LoadConfiguration.objects.filter(project_id=project["id"]).exists())
        self.assertTrue(
            PerformanceScenario.objects.filter(project_id=project["id"]).exists()
        )

    # ------------------------------------------------------------------
    # 7. AI model config + agent run
    # ------------------------------------------------------------------
    def test_07_ai_agent_run(self):
        config = self.client.post(
            "/api/ai/llm-configs/",
            {
                "project": self.project["id"],
                "name": "mock text model",
                "provider": "mock",
                "model_name": "mock-1",
                "model_type": "text",
                "is_default": True,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(config.status_code, 201, config.data)
        self.assertNotIn("sk-", json.dumps(config.data))
        stored_key = config.data.get("api_key") or ""
        self.assertTrue(stored_key == "" or "****" in stored_key)

        agents = self.client.get("/api/ai/agents/")
        self.assertEqual(agents.status_code, 200)
        names = {item["name"] for item in agents.data.get("results", agents.data)}
        self.assertIn("api_testcase", names)
        self.assertEqual(len(names), 7)

        run = self.client.post(
            "/api/ai/agents/api_testcase/run/",
            {
                "payload": {
                    "endpoint": {
                        "method": "POST",
                        "path": "/pets",
                        "summary": "Create pet",
                        "parameters": [],
                        "request_body": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                        },
                    },
                    "project_id": self.project["id"],
                }
            },
            format="json",
        )
        self.assertEqual(run.status_code, 200, run.data)
        self.assertIn(run.data.get("status"), {"success", "ok"})
        self.assertTrue(run.data.get("result"))

        usage = self.client.get("/api/ai/usage-logs/")
        self.assertEqual(usage.status_code, 200)
        stats = self.client.get("/api/ai/usage-stats/")
        self.assertEqual(stats.status_code, 200)

    # ------------------------------------------------------------------
    # 8. Notification + scheduled task full loop
    # ------------------------------------------------------------------
    def test_08_scheduled_task_notifies(self):
        from apps.notifications.models import NotificationChannel, NotificationLog

        channel = NotificationChannel.objects.get(channel_code="dingtalk")
        receiver = self.client.post(
            "/api/notifications/receivers/",
            {
                "project": self.project["id"],
                "name": "QA 群",
                "channel": channel.id,
                "webhook_url": LOOPBACK_WEBHOOK,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(receiver.status_code, 201, receiver.data)

        # prepare an executable API suite
        self._import_spec(self.project)
        cases = self._gen_cases(self.project)
        suite = self.client.post(
            "/api/api-testing/suites/",
            {
                "project": self.project["id"],
                "name": "scheduled suite",
                "case_ids": [case["id"] for case in cases[:2]],
            },
            format="json",
        )
        self.assertEqual(suite.status_code, 201, suite.data)

        task = self.client.post(
            "/api/scheduled-tasks/tasks/",
            {
                "project": self.project["id"],
                "name": "每日回归",
                "suite_type": "api",
                "suite_ids": [suite.data["id"]],
                "cron_expression": "0 9 * * 1-5",
                "trigger_condition": "always",
                "notice_targets": [receiver.data["id"]],
                "is_enabled": True,
            },
            format="json",
        )
        self.assertEqual(task.status_code, 201, task.data)
        self.assertIsNotNone(task.data.get("periodic_task_name"))

        preview = self.client.get(
            "/api/scheduled-tasks/cron/preview/?expr=0%209%20*%20*%201-5"
        )
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertTrue(preview.data.get("valid"))
        self.assertEqual(len(preview.data.get("next_runs", [])), 5)

        fake_response = mock.Mock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"errcode": 0, "errmsg": "ok"}
        fake_response.text = '{"errcode": 0}'

        with mock.patch("apps.notifications.services.requests") as requests_mock:
            requests_mock.post.return_value = fake_response
            run = self.client.post(
                f"/api/scheduled-tasks/tasks/{task.data['id']}/run/", {}, format="json"
            )
            self.assertEqual(run.status_code, 202, run.data)
            log_id = run.data.get("log_id") or run.data.get("task_id")

        log = self.client.get(f"/api/scheduled-tasks/logs/{log_id}/")
        self.assertEqual(log.status_code, 200, log.data)
        self.assertIn(log.data["status"], {"passed", "failed", "error"})
        self.assertNotEqual(log.data["status"], "pending")
        self.assertEqual(log.data["suite_type"], "api")
        self.assertGreater(log.data.get("total", 0), 0)

        self.assertTrue(
            NotificationLog.objects.filter(
                project_id=self.project["id"], channel_code="dingtalk"
            ).exists()
        )

        logs = self.client.get("/api/notifications/logs/")
        self.assertEqual(logs.status_code, 200)

    # ------------------------------------------------------------------
    # 9. health + metrics + docs
    # ------------------------------------------------------------------
    def test_09_observability_endpoints(self):
        health = self.client.get("/health/")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

        metrics = self.client.get("/metrics/")
        self.assertEqual(metrics.status_code, 200)
        self.assertIn(b"aits_test_executions_total", metrics.content)

        schema = self.client.get("/api/schema/")
        self.assertEqual(schema.status_code, 200)
