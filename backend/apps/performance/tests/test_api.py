"""HTTP API tests for ``/api/performance/`` (roles, CRUD, dashboard, webhook)."""

from __future__ import annotations

from django.test import override_settings

from apps.performance.models import AiDiagnosisRecord, PerformanceExecution
from apps.performance.services.execution import create_execution, execute_scenario
from apps.performance.tests.base import PerformanceFixture, grafana_payload

CONFIGS_URL = "/api/performance/configs/"
SCENARIOS_URL = "/api/performance/scenarios/"
EXECUTIONS_URL = "/api/performance/executions/"
DIAGNOSES_URL = "/api/performance/diagnoses/"
DASHBOARD_URL = "/api/performance/dashboard/"
WEBHOOK_URL = "/api/performance/grafana/webhook/"


class ConfigApiTests(PerformanceFixture):
    def test_config_crud(self):
        response = self.client.post(
            CONFIGS_URL,
            {
                "project": self.project.id,
                "name": "双十一压测",
                "users": 100,
                "spawn_rate": 10,
                "duration_seconds": 600,
                "host": "https://api.example.com",
                "config": {"error_rate": 0.0},
                "description": "大促压测配置",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        config_id = response.data["id"]
        self.assertEqual(response.data["users"], 100)
        self.assertEqual(response.data["project_name"], self.project.name)

        listed = self.client.get(CONFIGS_URL, {"project": self.project.id})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["count"], 1)
        self.assertEqual(listed.data["results"][0]["id"], config_id)

        patched = self.client.patch(
            f"{CONFIGS_URL}{config_id}/", {"users": 50}, format="json"
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.data["users"], 50)

        deleted = self.client.delete(f"{CONFIGS_URL}{config_id}/")
        self.assertEqual(deleted.status_code, 204)

    def test_config_validation_rejects_zero_users(self):
        response = self.client.post(
            CONFIGS_URL,
            {"project": self.project.id, "name": "非法配置", "users": 0},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.data)

    def test_viewer_cannot_write_configs(self):
        self.as_user(self.viewer)
        response = self.client.post(
            CONFIGS_URL,
            {"project": self.project.id, "name": "只读用户", "users": 10},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "permission_denied")

    def test_editor_delete_requires_admin(self):
        config = self.create_config()
        self.as_user(self.editor)
        response = self.client.delete(f"{CONFIGS_URL}{config.id}/")
        self.assertEqual(response.status_code, 403)
        self.as_user(self.owner)
        response = self.client.delete(f"{CONFIGS_URL}{config.id}/")
        self.assertEqual(response.status_code, 204)

    def test_outsider_only_sees_own_projects(self):
        self.create_config(name="内部配置")
        self.as_user(self.outsider)
        response = self.client.get(CONFIGS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)


class ScenarioApiTests(PerformanceFixture):
    def test_scenario_crud_computes_endpoint_count(self):
        cases = [self.create_api_case(name=f"用例{index}") for index in range(2)]
        suite = self.create_api_suite(cases)
        config = self.create_config()

        response = self.client.post(
            SCENARIOS_URL,
            {
                "project": self.project.id,
                "name": "订单链路压测",
                "source_type": "api_suite",
                "source_suite": suite.id,
                "config": config.id,
                "variables": {"version": "v1"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["endpoint_count"], 2)
        scenario_id = response.data["id"]

        listed = self.client.get(SCENARIOS_URL, {"source_type": "api_suite"})
        self.assertEqual(listed.data["count"], 1)

        patched = self.client.patch(
            f"{SCENARIOS_URL}{scenario_id}/", {"description": "更新后的描述"}, format="json"
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.data["description"], "更新后的描述")

        deleted = self.client.delete(f"{SCENARIOS_URL}{scenario_id}/")
        self.assertEqual(deleted.status_code, 204)

    def test_scenario_validation_requires_source(self):
        response = self.client.post(
            SCENARIOS_URL,
            {"project": self.project.id, "name": "缺来源", "source_type": "api_suite"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.data)

    def test_scenario_rejects_foreign_source_project(self):
        foreign_case = self.create_api_case(project=self.outsider_project)
        response = self.client.post(
            SCENARIOS_URL,
            {
                "project": self.project.id,
                "name": "越权来源",
                "source_type": "api_case",
                "source_case": foreign_case.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_viewer_cannot_run_scenario(self):
        scenario = self.create_scenario(source_type="api_case")
        self.as_user(self.viewer)
        response = self.client.post(f"{SCENARIOS_URL}{scenario.id}/run/", {}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_generate_script_endpoint_returns_compilable_script(self):
        case = self.create_api_case()
        suite = self.create_api_suite([case])
        scenario = self.create_scenario(source_type="api_suite", suite=suite)

        response = self.client.post(
            f"{SCENARIOS_URL}{scenario.id}/generate_script/", {}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("HttpUser", response.data["script"])
        self.assertEqual(response.data["endpoint_count"], 1)
        compile(response.data["script"], "<locustfile>", "exec")

    def test_invalid_custom_script_returns_400(self):
        scenario = self.create_scenario(
            source_type="custom_script", custom_script="def broken(:\n    pass\n"
        )
        response = self.client.post(
            f"{SCENARIOS_URL}{scenario.id}/generate_script/", {}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_locust_script")

    def test_run_scenario_returns_202_and_executes(self):
        scenario = self.create_scenario(source_type="api_case")
        config = self.create_config(users=5, duration_seconds=10)

        response = self.client.post(
            f"{SCENARIOS_URL}{scenario.id}/run/", {"config_id": config.id}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(set(response.data), {"task_id", "status", "execution_id"})
        self.assertEqual(response.data["status"], "pending")

        execution = PerformanceExecution.objects.get(pk=response.data["execution_id"])
        self.assertEqual(execution.config_id, config.id)
        self.assertEqual(execution.status, "passed")

        report = self.client.get(f"{EXECUTIONS_URL}{execution.id}/report/")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.data["execution"]["id"], execution.id)
        self.assertGreater(report.data["summary"]["total_requests"], 0)


class ExecutionApiTests(PerformanceFixture):
    def test_execution_list_is_project_scoped(self):
        scenario = self.create_scenario(source_type="api_case")
        execution = execute_scenario(scenario.id)
        foreign_scenario = self.create_scenario(
            source_type="api_case", project=self.outsider_project
        )
        execute_scenario(foreign_scenario.id)

        listed = self.client.get(EXECUTIONS_URL)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["count"], 1)
        self.assertEqual(listed.data["results"][0]["id"], execution)

        detail = self.client.get(f"{EXECUTIONS_URL}{execution}/")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("scenario_name", detail.data)

    def test_cancel_is_idempotent(self):
        scenario = self.create_scenario(source_type="api_case")
        execution = create_execution(scenario)

        first = self.client.post(f"{EXECUTIONS_URL}{execution.id}/cancel/", {}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["status"], "cancelled")

        second = self.client.post(f"{EXECUTIONS_URL}{execution.id}/cancel/", {}, format="json")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["status"], "cancelled")
        execution.refresh_from_db()
        self.assertEqual(execution.status, "cancelled")

    def test_cancel_finished_execution_rejected(self):
        scenario = self.create_scenario(source_type="api_case")
        execution = self.create_execution(scenario=scenario, status="passed")
        response = self.client.post(
            f"{EXECUTIONS_URL}{execution.id}/cancel/", {}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "execution_finished")

    def test_viewer_can_read_executions(self):
        scenario = self.create_scenario(source_type="api_case")
        execution = self.create_execution(scenario=scenario, status="passed")
        self.as_user(self.viewer)
        response = self.client.get(f"{EXECUTIONS_URL}{execution.id}/")
        self.assertEqual(response.status_code, 200)

    def test_outsider_cannot_read_foreign_execution(self):
        scenario = self.create_scenario(source_type="api_case")
        execution = self.create_execution(scenario=scenario)
        self.as_user(self.outsider)
        response = self.client.get(f"{EXECUTIONS_URL}{execution.id}/")
        self.assertEqual(response.status_code, 404)


class DashboardApiTests(PerformanceFixture):
    def test_dashboard_zero_structure_without_data(self):
        self.as_user(self.outsider)
        response = self.client.get(DASHBOARD_URL, {"days": 7})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["days"], 7)
        summary = response.data["summary"]
        for key in ("executions", "passed", "failed", "error", "avg_tps",
                    "avg_p95", "avg_error_rate", "total_requests"):
            self.assertEqual(summary[key], 0)
        self.assertEqual(len(response.data["trend"]), 7)
        self.assertTrue(all(item["executions"] == 0 for item in response.data["trend"]))
        self.assertEqual(response.data["recent_executions"], [])
        self.assertEqual(response.data["diagnosis"]["total"], 0)

    def test_dashboard_aggregates_execution_and_diagnosis(self):
        scenario = self.create_scenario(source_type="api_case")
        execution_id = execute_scenario(scenario.id)
        self.create_diagnosis(execution_id=execution_id, status="pending")

        response = self.client.get(DASHBOARD_URL, {"days": 7})
        self.assertEqual(response.status_code, 200)
        summary = response.data["summary"]
        self.assertEqual(summary["executions"], 1)
        self.assertEqual(summary["passed"] + summary["failed"] + summary["error"], 1)
        self.assertGreater(summary["avg_tps"], 0)
        self.assertGreater(summary["avg_p95"], 0)
        self.assertEqual(len(response.data["trend"]), 7)
        self.assertEqual(response.data["trend"][-1]["executions"], 1)
        self.assertEqual(len(response.data["recent_executions"]), 1)
        self.assertEqual(response.data["recent_executions"][0]["id"], execution_id)
        self.assertEqual(response.data["diagnosis"]["total"], 1)
        self.assertEqual(response.data["diagnosis"]["pending"], 1)

    def test_dashboard_is_project_scoped(self):
        foreign_scenario = self.create_scenario(
            source_type="api_case", project=self.outsider_project
        )
        execute_scenario(foreign_scenario.id)
        response = self.client.get(DASHBOARD_URL)
        self.assertEqual(response.data["summary"]["executions"], 0)


class DiagnosisApiTests(PerformanceFixture):
    def test_manual_diagnosis_creation(self):
        scenario = self.create_scenario(source_type="api_case")
        execution_id = execute_scenario(scenario.id)

        response = self.client.post(
            DIAGNOSES_URL,
            {"execution": execution_id, "alert_name": "手动诊断", "severity": "warning"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        record = AiDiagnosisRecord.objects.get(pk=response.data["id"])
        self.assertEqual(record.source, "manual")
        self.assertTrue(record.diagnosis_content.strip())
        self.assertEqual(record.project_id, self.project.id)

    def test_manual_diagnosis_requires_execution_or_project(self):
        response = self.client.post(DIAGNOSES_URL, {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_patch_diagnosis_status(self):
        record = self.create_diagnosis()
        response = self.client.patch(
            f"{DIAGNOSES_URL}{record.id}/", {"status": "resolved"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "resolved")
        record.refresh_from_db()
        self.assertIsNotNone(record.resolved_at)

        invalid = self.client.patch(
            f"{DIAGNOSES_URL}{record.id}/", {"status": "unknown"}, format="json"
        )
        self.assertEqual(invalid.status_code, 400)

    def test_list_diagnoses(self):
        self.create_diagnosis()
        response = self.client.get(DIAGNOSES_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)


class GrafanaWebhookApiTests(PerformanceFixture):
    def test_webhook_is_public_and_creates_diagnosis(self):
        self.as_anonymous()
        response = self.client.post(
            WEBHOOK_URL,
            grafana_payload(project_id=self.project.id),
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "processed")
        record = AiDiagnosisRecord.objects.get(pk=response.data["record_id"])
        self.assertEqual(record.source, "grafana")
        self.assertEqual(record.alert_name, "AITSHighErrorRate")
        self.assertEqual(record.severity, "critical")
        self.assertTrue(record.diagnosis_content.strip())
        self.assertEqual(record.project_id, self.project.id)

    def test_webhook_links_execution_from_labels(self):
        self.as_anonymous()
        scenario = self.create_scenario(source_type="api_case")
        execution_id = execute_scenario(scenario.id)
        response = self.client.post(
            WEBHOOK_URL,
            grafana_payload(execution_id=execution_id),
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        record = AiDiagnosisRecord.objects.get(pk=response.data["record_id"])
        self.assertEqual(record.execution_id, execution_id)
        self.assertEqual(record.project_id, self.project.id)

    def test_webhook_invalid_payload_returns_400(self):
        self.as_anonymous()
        response = self.client.post(WEBHOOK_URL, {"foo": "bar"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_payload")

        empty_alerts = self.client.post(
            WEBHOOK_URL, {"alerts": [], "status": "firing"}, format="json"
        )
        self.assertEqual(empty_alerts.status_code, 400)

    def test_webhook_resolved_alert_marks_record_resolved(self):
        self.as_anonymous()
        response = self.client.post(
            WEBHOOK_URL,
            grafana_payload(project_id=self.project.id, status="resolved"),
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        record = AiDiagnosisRecord.objects.get(pk=response.data["record_id"])
        self.assertEqual(record.status, "resolved")
        self.assertIsNotNone(record.resolved_at)

    def test_webhook_without_project_still_records_alert(self):
        self.as_anonymous()
        response = self.client.post(WEBHOOK_URL, grafana_payload(), format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "processed")
        record = AiDiagnosisRecord.objects.get(pk=response.data["record_id"])
        self.assertEqual(record.source, "grafana")
        self.assertIsNone(record.project_id)
        self.assertTrue(record.diagnosis_content.strip())

    def test_webhook_optional_token_validation(self):
        self.as_anonymous()
        payload = grafana_payload(project_id=self.project.id)
        with override_settings(GRAFANA_WEBHOOK_TOKEN="aits-secret"):
            rejected = self.client.post(WEBHOOK_URL, payload, format="json")
            self.assertEqual(rejected.status_code, 403)
            self.assertEqual(rejected.data["code"], "invalid_token")

            accepted = self.client.post(
                WEBHOOK_URL, payload, format="json",
                HTTP_X_GRAFANA_TOKEN="aits-secret",
            )
            self.assertEqual(accepted.status_code, 200)
            self.assertEqual(accepted.data["status"], "processed")
