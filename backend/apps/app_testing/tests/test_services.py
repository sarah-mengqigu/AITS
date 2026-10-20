"""Service level tests: step conversion, Sonic client auth & error mapping.

No test performs real network access: ``apps.app_testing.services.sonic_client.
requests`` is always patched.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import override_settings

from apps.app_testing.services.case_converter import (
    ACTION_TO_LABEL,
    aits_steps_to_sonic,
    build_suite_payload,
    sonic_steps_to_aits,
)
from apps.app_testing.services.sonic_client import (
    BIZ_CODE_MESSAGES,
    SonicAPIError,
    SonicClient,
    get_sonic_client,
)
from apps.app_testing.tests.base import AppTestingBaseTestCase, step
from apps.common.api.api_exception_handler import BusinessError


class FakeResponse:
    """Minimal requests.Response stand-in."""

    def __init__(self, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _sonic_ok(data):
    return {"code": 2000, "message": "成功", "data": data}


class CaseConverterTests(AppTestingBaseTestCase):
    REVERSIBLE_STEPS = [
        step("start_app", target="com.demo.app", expect="启动成功", description="启动"),
        step("tap", target="登录按钮", description="点击登录"),
        step("input", target="账号输入框", value="demo", expect="输入成功"),
        step("swipe", target="屏幕", value="up", description="上滑"),
        step("wait", value="2", description="等待 2 秒"),
        step("back", description="返回上一页"),
        step("assert", target="首页标题", value="首页", expect="首页展示"),
        step("stop_app", target="com.demo.app"),
    ]

    def test_aits_to_sonic_maps_actions_and_step_types(self):
        sonic = aits_steps_to_sonic(self.REVERSIBLE_STEPS)
        self.assertEqual(len(sonic), len(self.REVERSIBLE_STEPS))
        self.assertEqual(sonic[1]["content"]["action"], "点击")
        self.assertEqual(sonic[1]["type"], 0)
        self.assertEqual(sonic[6]["type"], 1)  # assert
        self.assertEqual(sonic[4]["type"], 2)  # wait
        for item in sonic:
            self.assertEqual(set(item), {"type", "content"})
            self.assertIn("action", item["content"])

    def test_alias_actions_are_normalised(self):
        sonic = aits_steps_to_sonic([
            step("click", target="a"),
            step("fill", target="b", value="x"),
            step("assert_text", target="c", expect="ok"),
        ])
        self.assertEqual(sonic[0]["content"]["action"], ACTION_TO_LABEL["click"])
        self.assertEqual(sonic[1]["content"]["action"], "输入")
        self.assertEqual(sonic[2]["type"], 1)

    def test_roundtrip_is_idempotent(self):
        sonic = aits_steps_to_sonic(self.REVERSIBLE_STEPS)
        self.assertEqual(sonic_steps_to_aits(sonic), self.REVERSIBLE_STEPS)
        # double round trip stays stable
        self.assertEqual(
            sonic_steps_to_aits(aits_steps_to_sonic(sonic_steps_to_aits(sonic))),
            self.REVERSIBLE_STEPS,
        )

    def test_empty_and_invalid_inputs(self):
        self.assertEqual(aits_steps_to_sonic([]), [])
        self.assertEqual(sonic_steps_to_aits([]), [])
        self.assertEqual(sonic_steps_to_aits([None, "x"]), [])

    def test_build_suite_payload(self):
        application = self.create_application(platform="android",
                                             package_name="com.demo.app")
        first = self.create_case(name="登录成功", application=application)
        second = self.create_case(name="下单成功", application=application)
        self.project.sonic_project_id = "sonic-p-1"
        self.project.save(update_fields=["sonic_project_id"])
        suite = self.create_suite(
            name="冒烟套件", case_ids=[first.id, second.id], application=application,
            device_config={"udid": "emulator-5554", "device_id": "d-1",
                           "platform": "android"},
        )

        payload = build_suite_payload(suite, [first, second], self.project)
        self.assertEqual(payload["sonicProjectId"], "sonic-p-1")
        self.assertEqual(payload["projectId"], "sonic-p-1")
        self.assertEqual(payload["suiteName"], "冒烟套件")
        self.assertEqual(payload["udid"], "emulator-5554")
        self.assertEqual(payload["deviceId"], "d-1")
        self.assertEqual(payload["platform"], "android")
        self.assertEqual(payload["appPackage"], "com.demo.app")
        self.assertEqual(payload["caseIds"], [first.id, second.id])
        self.assertEqual(len(payload["cases"]), 2)
        self.assertEqual(payload["cases"][0]["steps"][1]["content"]["action"], "点击")


class SonicClientTests(AppTestingBaseTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_read_apis_return_empty_when_not_configured(self):
        client = SonicClient(base_url="")
        self.assertFalse(client.configured)
        self.assertEqual(client.list_devices(), [])
        self.assertEqual(client.list_projects(), [])
        self.assertEqual(client.list_element_pages("1"), [])
        self.assertEqual(client.list_test_suites("1"), [])
        self.assertEqual(client.get_device("u"), {})
        self.assertEqual(client.suite_result("s"), {})
        self.assertEqual(client.device_remote_info("u"), {})

    def test_write_apis_raise_friendly_error_when_not_configured(self):
        client = SonicClient(base_url="")
        with self.assertRaises(BusinessError) as ctx:
            client.run_suite("s-1")
        self.assertEqual(ctx.exception.biz_code, "sonic_not_configured")
        self.assertIn("SONIC_BASE_URL", ctx.exception.message)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_get_sonic_client_prefers_project_sonic_id(self):
        self.project.sonic_project_id = "sonic-project-9"
        client = get_sonic_client(self.project)
        self.assertEqual(client.project_id, "sonic-project-9")
        self.assertEqual(get_sonic_client().project_id, "")

    @override_settings(SONIC_BASE_URL="http://sonic.test", SONIC_USERNAME="u",
                       SONIC_PASSWORD="p")
    def test_login_token_is_cached_and_reused(self):
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url))
            if url.endswith("/auth/login"):
                return FakeResponse(_sonic_ok({"token": "tok-1"}))
            return FakeResponse(_sonic_ok({"records": [{"udid": "u-1"}]}))

        fake_requests = MagicMock()
        fake_requests.request.side_effect = fake_request
        with patch("apps.app_testing.services.sonic_client.requests", fake_requests):
            client = SonicClient()
            self.assertEqual(client.list_devices(), [{"udid": "u-1"}])
            self.assertEqual(client.list_devices(), [{"udid": "u-1"}])

        login_calls = [call for call in calls if call[1].endswith("/auth/login")]
        self.assertEqual(len(login_calls), 1)
        self.assertEqual(cache.get("sonic:token:http://sonic.test"), "tok-1")
        self.assertEqual(
            [call[1] for call in calls][0], "http://sonic.test/server/api/auth/login"
        )

    @override_settings(SONIC_BASE_URL="http://sonic.test", SONIC_USERNAME="u",
                       SONIC_PASSWORD="p")
    def test_401_triggers_one_relogin(self):
        state = {"logins": 0, "device_calls": 0}

        def fake_request(method, url, **kwargs):
            if url.endswith("/auth/login"):
                state["logins"] += 1
                return FakeResponse(_sonic_ok({"token": f"tok-{state['logins']}"}))
            state["device_calls"] += 1
            if state["device_calls"] == 1:
                return FakeResponse({"code": 401, "message": "token expired"},
                                    status_code=401)
            return FakeResponse(_sonic_ok([{"udid": "u-1"}]))

        fake_requests = MagicMock()
        fake_requests.request.side_effect = fake_request
        with patch("apps.app_testing.services.sonic_client.requests", fake_requests):
            client = SonicClient()
            devices = client.list_devices()

        self.assertEqual(devices, [{"udid": "u-1"}])
        self.assertEqual(state["logins"], 2)
        self.assertEqual(cache.get("sonic:token:http://sonic.test"), "tok-2")

    @override_settings(SONIC_BASE_URL="http://sonic.test")
    def test_http_401_after_relogin_is_reported(self):
        def fake_request(method, url, **kwargs):
            if url.endswith("/auth/login"):
                return FakeResponse(_sonic_ok({"token": "tok"}))
            return FakeResponse({"message": "unauthorized"}, status_code=401)

        fake_requests = MagicMock()
        fake_requests.request.side_effect = fake_request
        with patch("apps.app_testing.services.sonic_client.requests", fake_requests):
            with self.assertRaises(SonicAPIError) as ctx:
                SonicClient().device_remote_info("u-1")
        self.assertEqual(ctx.exception.code, 401)
        self.assertIn("鉴权", ctx.exception.message)

    @override_settings(SONIC_BASE_URL="http://sonic.test")
    def test_business_codes_are_mapped_to_chinese_messages(self):
        for biz_code, expected in BIZ_CODE_MESSAGES.items():
            def fake_request(method, url, **kwargs):
                if url.endswith("/auth/login"):
                    return FakeResponse(_sonic_ok({"token": "tok"}))
                return FakeResponse({"code": biz_code, "message": "raw-message",
                                     "data": None})

            fake_requests = MagicMock()
            fake_requests.request.side_effect = fake_request
            with patch("apps.app_testing.services.sonic_client.requests", fake_requests):
                with self.assertRaises(SonicAPIError) as ctx:
                    SonicClient().run_suite("suite-1")
            self.assertEqual(ctx.exception.biz_code, biz_code)
            self.assertEqual(ctx.exception.message, expected)

    @override_settings(SONIC_BASE_URL="http://sonic.test")
    def test_unknown_business_code_keeps_server_message(self):
        def fake_request(method, url, **kwargs):
            if url.endswith("/auth/login"):
                return FakeResponse(_sonic_ok({"token": "tok"}))
            return FakeResponse({"code": 9999, "message": "服务器内部异常", "data": None})

        fake_requests = MagicMock()
        fake_requests.request.side_effect = fake_request
        with patch("apps.app_testing.services.sonic_client.requests", fake_requests):
            with self.assertRaises(SonicAPIError) as ctx:
                SonicClient().run_suite("suite-1")
        self.assertEqual(ctx.exception.message, "服务器内部异常")
        self.assertEqual(ctx.exception.biz_code, 9999)

    @override_settings(SONIC_BASE_URL="http://sonic.test")
    def test_network_error_becomes_sonic_unavailable(self):
        fake_requests = MagicMock()
        fake_requests.request.side_effect = ConnectionError("connection refused")
        with patch("apps.app_testing.services.sonic_client.requests", fake_requests):
            with self.assertRaises(BusinessError) as ctx:
                SonicClient().run_suite("suite-1")
        self.assertEqual(ctx.exception.biz_code, "sonic_unavailable")
        self.assertEqual(ctx.exception.status_code, 503)

    @override_settings(SONIC_BASE_URL="http://sonic.test")
    def test_login_supports_both_body_conventions(self):
        bodies = []

        def fake_request(method, url, **kwargs):
            if url.endswith("/auth/login"):
                bodies.append(kwargs.get("json"))
                if len(bodies) == 1:  # userName rejected by this Sonic version
                    return FakeResponse({"code": 401, "message": "bad body"},
                                        status_code=401)
                return FakeResponse(_sonic_ok({"token": "tok-2"}))
            return FakeResponse(_sonic_ok([]))

        fake_requests = MagicMock()
        fake_requests.request.side_effect = fake_request
        with patch("apps.app_testing.services.sonic_client.requests", fake_requests):
            client = SonicClient(username="u", password="p")
            self.assertEqual(client.get_token(), "tok-2")

        self.assertEqual(bodies[0], {"userName": "u", "password": "p"})
        self.assertEqual(bodies[1], {"username": "u", "password": "p"})

    @override_settings(SONIC_BASE_URL="http://sonic.test")
    def test_run_suite_posts_payload(self):
        captured = {}

        def fake_request(method, url, **kwargs):
            if url.endswith("/auth/login"):
                return FakeResponse(_sonic_ok({"token": "tok"}))
            captured["url"] = url
            captured["json"] = kwargs.get("json")
            captured["headers"] = kwargs.get("headers")
            return FakeResponse(_sonic_ok({"suiteId": "sonic-suite-1"}))

        fake_requests = MagicMock()
        fake_requests.request.side_effect = fake_request
        with patch("apps.app_testing.services.sonic_client.requests", fake_requests):
            result = SonicClient().run_suite(
                "s-1", device_udid="u-1", device_id="d-1", project_id="p-1"
            )
        self.assertEqual(result["suiteId"], "sonic-suite-1")
        self.assertTrue(captured["url"].endswith("/server/api/remote/runSuite"))
        self.assertEqual(captured["json"]["suiteId"], "s-1")
        self.assertEqual(captured["json"]["udid"], "u-1")
        self.assertEqual(captured["json"]["deviceId"], "d-1")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer tok")
        json.dumps(captured["json"])  # payload is JSON serialisable
