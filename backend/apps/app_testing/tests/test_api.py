"""API tests for ``/api/app-testing/`` (routing, permissions, runs, proxies)."""

from __future__ import annotations

import json
from pathlib import Path

from django.test import override_settings
from unittest.mock import patch

from apps.app_testing.models import (
    AppTestApplication,
    AppTestCase,
    AppTestModule,
    AppTestRun,
    AppTestSuite,
)
from apps.app_testing.tests.base import API, AppTestingBaseTestCase, step


class ModuleApiTests(AppTestingBaseTestCase):
    def test_module_tree_is_nested_and_counts_cases(self):
        root = self.create_module("登录模块")
        child = self.create_module("短信登录", parent=root)
        self.create_case(name="短信登录成功", module=child)

        response = self.viewer_client.get(f"{API}/modules/tree/", {"project": self.project.id})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], root.id)
        self.assertEqual(len(response.data[0]["children"]), 1)
        self.assertEqual(response.data[0]["children"][0]["name"], "短信登录")
        self.assertEqual(response.data[0]["children"][0]["case_count"], 1)

    def test_module_create_permissions(self):
        payload = {"project": self.project.id, "name": "支付模块", "order": 1}
        self.assertEqual(
            self.viewer_client.post(f"{API}/modules/", payload, format="json").status_code,
            403,
        )
        self.assertEqual(
            self.anonymous_client.get(f"{API}/modules/").status_code, 401
        )
        response = self.editor_client.post(f"{API}/modules/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(AppTestModule.objects.count(), 1)

    def test_module_rejects_parent_from_other_project(self):
        other_project = type(self.project).objects.create(
            name="另一个项目", project_type="app", owner=self.owner
        )
        other_module = AppTestModule.objects.create(project=other_project, name="外部模块")
        response = self.editor_client.post(
            f"{API}/modules/",
            {"project": self.project.id, "name": "子模块", "parent": other_module.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "validation_error")


class ApplicationApiTests(AppTestingBaseTestCase):
    def test_application_crud_and_permissions(self):
        payload = {
            "project": self.project.id,
            "name": "Demo App",
            "platform": "android",
            "package_name": "com.demo.app",
            "app_version": "2.0.0",
        }
        self.assertEqual(
            self.viewer_client.post(f"{API}/applications/", payload, format="json").status_code,
            403,
        )
        created = self.editor_client.post(f"{API}/applications/", payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["app_identifier"], "com.demo.app")

        listed = self.viewer_client.get(f"{API}/applications/", {"project": self.project.id})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["count"], 1)

        app = AppTestApplication.objects.get()
        patched = self.editor_client.patch(
            f"{API}/applications/{app.id}/", {"app_version": "2.1.0"}, format="json"
        )
        self.assertEqual(patched.status_code, 200, patched.data)
        self.assertEqual(patched.data["app_version"], "2.1.0")

    def test_android_application_requires_package_name(self):
        response = self.editor_client.post(
            f"{API}/applications/",
            {"project": self.project.id, "name": "无包名", "platform": "android"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("package_name", response.data["errors"])


class CaseApiTests(AppTestingBaseTestCase):
    def test_case_crud_and_sonic_snapshot_sync(self):
        payload = {
            "project": self.project.id,
            "name": "登录用例",
            "steps": [
                step("start_app", target="com.demo.app"),
                step("tap", target="登录按钮"),
                step("assert", target="首页", expect="首页展示"),
            ],
        }
        created = self.editor_client.post(f"{API}/cases/", payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["step_count"], 3)
        sonic_steps = created.data["sonic_steps"]
        self.assertEqual(len(sonic_steps), 3)
        self.assertEqual(sonic_steps[1]["content"]["action"], "点击")
        self.assertEqual(sonic_steps[2]["type"], 1)

        # viewer can read but not write
        self.assertEqual(
            self.viewer_client.patch(
                f"{API}/cases/{created.data['id']}/", {"name": "改名"}, format="json"
            ).status_code,
            403,
        )
        patched = self.editor_client.patch(
            f"{API}/cases/{created.data['id']}/",
            {"steps": [step("tap", target="设置"), step("wait", value="2")]},
            format="json",
        )
        self.assertEqual(patched.status_code, 200, patched.data)
        self.assertEqual(patched.data["sonic_steps"][0]["type"], 0)
        self.assertEqual(patched.data["sonic_steps"][1]["type"], 2)

        deleted = self.owner_client.delete(f"{API}/cases/{created.data['id']}/")
        self.assertEqual(deleted.status_code, 204)

    def test_case_invalid_action_is_rejected(self):
        response = self.editor_client.post(
            f"{API}/cases/",
            {
                "project": self.project.id,
                "name": "非法步骤",
                "steps": [{"action": "goto", "target": "x"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "validation_error")

    def test_case_list_is_project_scoped(self):
        self.create_case()
        mine = self.viewer_client.get(f"{API}/cases/")
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(mine.data["count"], 1)
        other = self.outsider_client.get(f"{API}/cases/")
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.data["count"], 0)
        self.assertEqual(self.anonymous_client.get(f"{API}/cases/").status_code, 401)

    def test_generate_steps_rule_fallback(self):
        application = self.create_application()
        test_case = self.create_case(name="待生成", steps=[], application=application)
        response = self.editor_client.post(
            f"{API}/cases/{test_case.id}/generate_steps/",
            {"requirement": "启动应用，点击登录，输入账号，校验首页"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["generated_by"], "rule")
        steps = response.data["steps"]
        self.assertEqual(steps[0]["action"], "start_app")
        self.assertEqual(steps[-1]["action"], "stop_app")
        self.assertGreaterEqual(len(steps), 4)
        self.assertEqual(len(response.data["sonic_steps"]), len(steps))

        test_case.refresh_from_db()
        self.assertEqual(test_case.steps, steps)
        self.assertEqual(test_case.source, "ai")
        self.assertEqual(test_case.sonic_steps, response.data["sonic_steps"])

    def test_generate_steps_requires_requirement(self):
        test_case = self.create_case()
        response = self.editor_client.post(
            f"{API}/cases/{test_case.id}/generate_steps/", {}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "missing_requirement")
        self.assertEqual(
            self.viewer_client.post(
                f"{API}/cases/{test_case.id}/generate_steps/",
                {"requirement": "点击登录"},
                format="json",
            ).status_code,
            403,
        )


class SuiteRunApiTests(AppTestingBaseTestCase):
    def _suite_with_cases(self):
        passing = self.create_case(name="登录成功")
        failing = self.create_case(name="支付失败")
        return self.create_suite(case_ids=[passing.id, failing.id])

    def test_suite_run_simulated_is_deterministic_and_reports(self):
        suite = self._suite_with_cases()
        response = self.editor_client.post(f"{API}/suites/{suite.id}/run/", {}, format="json")
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(str(response.data["run_id"]), response.data["task_id"])
        self.assertTrue(response.data["run_id"])

        run = AppTestRun.objects.get(pk=response.data["run_id"])
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.total, 2)
        self.assertEqual(run.passed, 1)
        self.assertEqual(run.failed, 1)
        self.assertAlmostEqual(run.pass_rate, 50.0)
        self.assertIsNotNone(run.started_at)
        self.assertIsNotNone(run.finished_at)
        self.assertGreaterEqual(run.duration_ms, 1)
        self.assertEqual(run.device_udid, "emulator-5554")
        self.assertEqual(run.device_id, "d-1")
        self.assertEqual(len(run.summary["cases"]), 2)

        report_file = Path(run.report_path)
        self.assertTrue(report_file.exists())
        report = json.loads(report_file.read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["total"], 2)
        self.assertEqual(report["summary"]["mode"], "simulated")

        detail = self.viewer_client.get(f"{API}/runs/{run.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["summary"]["total"], 2)
        self.assertEqual(len(detail.data["summary"]["cases"]), 2)

    def test_suite_run_requires_editor(self):
        suite = self._suite_with_cases()
        response = self.viewer_client.post(f"{API}/suites/{suite.id}/run/", {}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_suite_run_rejects_inactive_suite(self):
        suite = self._suite_with_cases()
        suite.is_active = False
        suite.save(update_fields=["is_active"])
        response = self.editor_client.post(f"{API}/suites/{suite.id}/run/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "suite_inactive")

    def test_report_endpoint_returns_summary_and_payload(self):
        suite = self._suite_with_cases()
        run_id = self.editor_client.post(
            f"{API}/suites/{suite.id}/run/", {}, format="json"
        ).data["run_id"]
        response = self.viewer_client.get(f"{API}/runs/{run_id}/report/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["run_id"], run_id)
        self.assertEqual(response.data["total"], 2)
        self.assertTrue(response.data["report_available"])
        self.assertTrue(response.data["report_url"])
        self.assertEqual(len(response.data["report"]["cases"]), 2)
        download = self.viewer_client.get(f"{API}/runs/{run_id}/report/", {"download": "1"})
        self.assertEqual(download.status_code, 200)
        download.close()

    def test_run_cancel_and_conflict(self):
        suite = self.create_suite()
        run = AppTestRun.objects.create(
            project=self.project, suite=suite, name="运行中的执行", status="running"
        )
        response = self.editor_client.post(f"{API}/runs/{run.id}/cancel/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "cancelled")
        run.refresh_from_db()
        self.assertIsNotNone(run.finished_at)
        again = self.editor_client.post(f"{API}/runs/{run.id}/cancel/", {}, format="json")
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.data["code"], "invalid_status")
        self.assertEqual(
            self.viewer_client.post(f"{API}/runs/{run.id}/cancel/", {}).status_code, 403
        )

    def test_delete_requires_admin(self):
        suite = self.create_suite()
        self.assertEqual(
            self.viewer_client.delete(f"{API}/suites/{suite.id}/").status_code, 403
        )
        self.assertEqual(
            self.editor_client.delete(f"{API}/suites/{suite.id}/").status_code, 403
        )
        self.assertEqual(
            self.owner_client.delete(f"{API}/suites/{suite.id}/").status_code, 204
        )
        self.assertFalse(AppTestSuite.objects.filter(pk=suite.id).exists())


class SonicProxyApiTests(AppTestingBaseTestCase):
    def test_devices_empty_when_sonic_not_configured(self):
        response = self.viewer_client.get(f"{API}/devices/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])
        detail = self.viewer_client.get(f"{API}/devices/emulator-5554/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["detail"], "sonic_not_configured")
        remote = self.viewer_client.post(f"{API}/devices/emulator-5554/remote/")
        self.assertEqual(remote.status_code, 200)
        self.assertEqual(remote.data["detail"], "sonic_not_configured")

    def test_element_pages_empty_when_sonic_not_configured(self):
        response = self.viewer_client.get(f"{API}/element-pages/",
                                          {"project": self.project.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    @override_settings(SONIC_BASE_URL="http://sonic.test")
    def test_devices_proxy_mocked(self):
        devices = [{"id": "d-1", "udid": "emulator-5554", "name": "Pixel 7"}]
        remote = {"ws_url": "ws://sonic.test/ws?udid=emulator-5554",
                  "jmuxer": {"ws_url": "ws://sonic.test/ws?udid=emulator-5554"}}
        with patch(
            "apps.app_testing.services.sonic_client.SonicClient.list_devices",
            return_value=devices,
        ), patch(
            "apps.app_testing.services.sonic_client.SonicClient.get_device",
            return_value=devices[0],
        ), patch(
            "apps.app_testing.services.sonic_client.SonicClient.device_remote_info",
            return_value=remote,
        ):
            listed = self.viewer_client.get(f"{API}/devices/")
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(listed.data, devices)

            detail = self.viewer_client.get(f"{API}/devices/emulator-5554/")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.data["device"]["udid"], "emulator-5554")

            remote_response = self.editor_client.post(
                f"{API}/devices/emulator-5554/remote/"
            )
            self.assertEqual(remote_response.status_code, 200, remote_response.data)
            self.assertEqual(remote_response.data["ws_url"], remote["ws_url"])
            self.assertEqual(
                self.viewer_client.post(f"{API}/devices/emulator-5554/remote/").status_code,
                200,  # no project -> no project role check
            )
