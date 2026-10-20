"""Unit tests for parsing, script building, runners and generators."""

from __future__ import annotations

import json
import unittest

import yaml

from apps.api_testing.services.generator import generate_endpoint_cases, generate_scenario
from apps.api_testing.services.runner import SimulatedRunner, get_runner
from apps.api_testing.services.script_builder import (
    build_case_from_endpoint,
    build_httprunner_yaml,
)
from apps.api_testing.services.spec_parser import parse_openapi, parse_postman
from apps.api_testing.tests.base import APITestFixture
from apps.api_testing.tests.samples import (
    OPENAPI3_SPEC,
    POSTMAN_COLLECTION,
    SWAGGER2_SPEC,
)
from apps.common.api.api_exception_handler import BusinessError


class FakeLLM:
    """Minimal LLMService stand-in for generator tests."""

    def __init__(self, reply="", error: Exception | None = None):
        self.reply = reply
        self.error = error
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.reply


class SpecParserTests(APITestFixture):
    def test_parse_openapi3_metadata_and_endpoints(self):
        parsed = parse_openapi(json.dumps(OPENAPI3_SPEC, ensure_ascii=False))
        self.assertEqual(parsed["source_type"], "openapi")
        self.assertEqual(parsed["format"], "openapi3")
        self.assertEqual(parsed["title"], "Pet API")
        self.assertEqual(parsed["version"], "1.0.0")
        self.assertEqual(parsed["base_url"], "https://api.example.com/v1")
        self.assertEqual(parsed["endpoint_count"], 3)

        by_key = {(item["method"], item["path"]): item for item in parsed["endpoints"]}
        self.assertIn(("get", "/pets"), by_key)
        self.assertIn(("post", "/pets"), by_key)
        self.assertIn(("get", "/pets/{petId}"), by_key)

        get_item = by_key[("get", "/pets")]
        self.assertEqual(get_item["summary"], "宠物列表")
        self.assertEqual(get_item["operation_id"], "listPets")
        self.assertEqual(get_item["tags"], ["pets"])
        self.assertEqual(get_item["parameters"][0]["name"], "limit")
        self.assertEqual(get_item["parameters"][0]["example"], 10)
        self.assertIn("200", get_item["responses"])

        post_item = by_key[("post", "/pets")]
        self.assertEqual(post_item["request_body"]["content_type"], "application/json")
        self.assertEqual(
            post_item["request_body"]["example"],
            {"id": 1, "name": "string", "tags": ["string"]},
        )
        self.assertEqual(post_item["headers"]["Content-Type"], "application/json")

    def test_parse_swagger2_body_and_headers(self):
        parsed = parse_openapi(json.dumps(SWAGGER2_SPEC))
        self.assertEqual(parsed["source_type"], "swagger")
        self.assertEqual(parsed["format"], "swagger2")
        self.assertEqual(parsed["base_url"], "/api/v2")
        endpoint = parsed["endpoints"][0]
        self.assertEqual(endpoint["method"], "post")
        self.assertEqual(endpoint["path"], "/login")
        self.assertEqual(
            endpoint["request_body"]["example"],
            {"username": "string", "password": "string"},
        )
        self.assertEqual(endpoint["headers"]["X-Token"], "abc")
        self.assertEqual(endpoint["headers"]["Content-Type"], "application/json")
        self.assertIn("token", endpoint["responses"]["200"]["properties"])

    def test_parse_postman_collection_nested_and_assertions(self):
        requests = parse_postman(POSTMAN_COLLECTION)
        self.assertEqual(len(requests), 2)
        login = requests[0]
        self.assertEqual(login["name"], "Login")
        self.assertEqual(login["folder"], ["Auth"])
        self.assertEqual(login["method"], "post")
        self.assertEqual(login["path"], "/api/login")
        self.assertEqual(login["url"], "https://postman.example.com/api/login?remember=true")
        self.assertEqual(login["parameters"][0]["name"], "remember")
        self.assertEqual(login["parameters"][0]["example"], "true")
        self.assertEqual(login["headers"]["Content-Type"], "application/json")
        self.assertEqual(login["body"]["json"]["username"], "alice")
        self.assertEqual(login["auth"]["type"], "bearer")

        by_type = {}
        for assertion in login["assertions"]:
            by_type.setdefault(assertion["type"], []).append(assertion)
        self.assertEqual(by_type["status_code"][0]["expected"], 200)
        json_assertions = {(item["path"], item["expected"]) for item in by_type["json_path"]}
        self.assertIn(("data.token", "abc123"), json_assertions)
        self.assertIn(("data.user.id", 7), json_assertions)

        health = requests[1]
        self.assertEqual(health["path"], "/health")
        self.assertEqual(health["assertions"], [])

    def test_parse_invalid_documents_raise_business_error(self):
        with self.assertRaises(BusinessError) as ctx:
            parse_openapi("not: [a: valid: spec")
        self.assertIn(ctx.exception.biz_code, {"invalid_spec", "unknown_spec"})

        with self.assertRaises(BusinessError):
            parse_postman({"foo": "bar"})

        with self.assertRaises(BusinessError):
            parse_postman({"info": {"name": "empty"}, "item": []})


class ScriptBuilderTests(APITestFixture):
    def test_build_httprunner_yaml_endpoint(self):
        case = self.create_case(
            name="宠物列表正向",
            assertions=[
                {"type": "status_code", "expected": 200},
                {"type": "json_path", "path": "data.id", "expected": 1},
                {"type": "contains", "path": "data.name", "expected": "tom"},
                {"type": "len_gte", "path": "data.items", "expected": 2},
            ],
            extract={"token": "data.token"},
            request_config={
                "base_url": "https://api.example.com",
                "variables": {"limit": 10},
                "verify": False,
                "method": "GET",
                "url": "/pets",
                "params": {"limit": 10},
                "headers": {"Accept": "application/json"},
            },
        )
        document = yaml.safe_load(build_httprunner_yaml(case))
        config = document["config"]
        for key in ("name", "base_url", "variables", "verify", "stage"):
            self.assertIn(key, config)
        self.assertEqual(config["name"], case.name)
        self.assertEqual(config["base_url"], "https://api.example.com")
        self.assertFalse(config["verify"])

        steps = document["teststeps"]
        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertEqual(step["request"]["method"], "GET")
        self.assertEqual(step["request"]["url"], "/pets")
        validates = step["validate"]
        self.assertIn({"eq": ["status_code", 200]}, validates)
        self.assertIn({"eq": ["content.data.id", 1]}, validates)
        self.assertIn({"contains": ["content.data.name", "tom"]}, validates)
        self.assertIn({"len_gte": ["content.data.items", 2]}, validates)
        self.assertEqual(step["extract"]["token"], "content.data.token")

    def test_build_httprunner_yaml_scenario_multistep(self):
        case = self.create_case(
            name="下单场景",
            case_type="scenario",
            assertions=[],
            request_config={
                "variables": {"user": "alice"},
                "base_url": "https://shop.example.com",
                "steps": [
                    {
                        "name": "登录",
                        "request_config": {"method": "POST", "url": "/login",
                                           "body": {"mode": "raw",
                                                    "json": {"user": "${user}"}}},
                        "assertions": [{"type": "status_code", "expected": 200}],
                        "extract": {"token": "data.token"},
                    },
                    {
                        "name": "查询订单",
                        "request_config": {
                            "method": "GET",
                            "url": "/orders",
                            "headers": {"Authorization": "Bearer ${token}"},
                        },
                        "assertions": [{"type": "status_code", "expected": 200},
                                       {"type": "json_path", "path": "total",
                                        "expected": 1}],
                    },
                ],
            },
        )
        document = yaml.safe_load(build_httprunner_yaml(case))
        steps = document["teststeps"]
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]["name"], "登录")
        self.assertEqual(steps[0]["request"]["json"], {"user": "${user}"})
        self.assertEqual(steps[0]["extract"]["token"], "content.data.token")
        self.assertEqual(steps[1]["request"]["headers"]["Authorization"],
                         "Bearer ${token}")
        self.assertIn({"eq": ["content.total", 1]}, steps[1]["validate"])

    def test_build_case_from_endpoint(self):
        endpoint = self.create_endpoint(
            path="/pets/{petId}",
            method="post",
            parameters=[
                {"name": "petId", "in": "path", "required": True, "example": "p1"},
                {"name": "notify", "in": "query", "required": False, "example": True},
            ],
            request_body={"content_type": "application/json",
                          "example": {"name": "tom"}},
            responses={"201": {}},
        )
        payload = build_case_from_endpoint(endpoint)
        self.assertEqual(payload["request_config"]["method"], "POST")
        self.assertEqual(payload["request_config"]["url"], "/pets/p1")
        self.assertEqual(payload["request_config"]["params"], {"notify": True})
        self.assertEqual(payload["request_config"]["body"]["json"], {"name": "tom"})
        self.assertEqual(payload["assertions"][0]["expected"], 201)


class RunnerTests(APITestFixture):
    def test_simulated_runner_pass_fail_and_extract(self):
        progress: list[int] = []
        plan = {
            "variables": {"env": "dev"},
            "cases": [
                {
                    "id": 1,
                    "name": "通过用例",
                    "request_config": {
                        "method": "GET",
                        "url": "/a",
                        "headers": {"X-Env": "${env}"},
                        "mock_response": {
                            "status_code": 200,
                            "json": {"data": {"token": "t1", "id": 1}},
                        },
                    },
                    "assertions": [
                        {"type": "status_code", "expected": 200},
                        {"type": "json_path", "path": "data.token", "expected": "t1"},
                        {"type": "response_time_lt", "expected": 500},
                    ],
                    "extract": {"token": "data.token"},
                },
                {
                    "id": 2,
                    "name": "断言失败用例",
                    "request_config": {
                        "mock_response": {"status_code": 500, "json": {"error": "boom"}}
                    },
                    "assertions": [{"type": "status_code", "expected": 200}],
                },
                {
                    "id": 3,
                    "name": "变量传递用例",
                    "request_config": {
                        "method": "GET",
                        "url": "/b",
                        "headers": {"Authorization": "Bearer ${token}"},
                        "mock_response": {"status_code": 200, "json": {"ok": True}},
                    },
                    "assertions": [{"type": "status_code", "expected": 200}],
                },
            ],
        }
        result = SimulatedRunner().run(plan, on_progress=lambda p, m: progress.append(p))
        self.assertEqual(result["status"], "failed")
        summary = result["summary"]
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["passed"], 2)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["mode"], "simulated")
        self.assertEqual(result["cases"][1]["status"], "failed")
        self.assertTrue(result["cases"][1]["error_message"])
        self.assertEqual(
            result["cases"][2]["request"]["headers"]["Authorization"], "Bearer t1"
        )
        self.assertEqual(progress[-1], 100)
        self.assertIsInstance(get_runner(), SimulatedRunner)

    def test_simulated_runner_scenario_multistep(self):
        plan = {
            "cases": [
                {
                    "id": 9,
                    "name": "登录后查询",
                    "case_type": "scenario",
                    "request_config": {
                        "steps": [
                            {
                                "name": "登录",
                                "request_config": {
                                    "method": "POST",
                                    "url": "/login",
                                    "mock_response": {
                                        "status_code": 200,
                                        "json": {"data": {"token": "abc"}},
                                    },
                                },
                                "assertions": [{"type": "status_code", "expected": 200}],
                                "extract": {"token": "data.token"},
                            },
                            {
                                "name": "查询",
                                "request_config": {
                                    "method": "GET",
                                    "url": "/me",
                                    "headers": {"Authorization": "Bearer ${token}"},
                                    "mock_response": {"status_code": 200,
                                                      "json": {"ok": True}},
                                },
                                "assertions": [{"type": "status_code", "expected": 200}],
                            },
                        ]
                    },
                    "assertions": [],
                }
            ]
        }
        result = SimulatedRunner().run(plan)
        case = result["cases"][0]
        self.assertEqual(result["status"], "passed")
        self.assertEqual(case["status"], "passed")
        self.assertEqual(len(case["request"]["steps"]), 2)
        self.assertEqual(
            case["request"]["steps"][1]["headers"]["Authorization"], "Bearer abc"
        )
        self.assertEqual(len(case["step_log"]), 2)


class GeneratorTests(APITestFixture):
    def _endpoint(self):
        return self.create_endpoint(
            path="/pets",
            method="post",
            summary="创建宠物",
            request_body={
                "content_type": "application/json",
                "example": {"id": 1, "name": "tom", "tags": ["cat"]},
            },
            responses={"200": {}, "400": {}},
            parameters=[
                {"name": "traceId", "in": "query", "required": True, "example": "t-1"}
            ],
        )

    def test_rule_generation_produces_four_test_types(self):
        llm = FakeLLM(error=RuntimeError("llm down"))
        cases = generate_endpoint_cases(self._endpoint(), llm_service=llm)
        self.assertEqual(llm.calls, 1)
        self.assertEqual(len(cases), 4)
        types = {case["test_type"] for case in cases}
        self.assertEqual(types, {"positive", "negative", "boundary", "security"})
        for case in cases:
            self.assertTrue(case["name"])
            self.assertIn("request_config", case)
            self.assertTrue(case["assertions"])
        positive = next(case for case in cases if case["test_type"] == "positive")
        self.assertEqual(positive["assertions"][0]["expected"], 200)
        security = next(case for case in cases if case["test_type"] == "security")
        self.assertNotIn("Authorization", security["request_config"]["headers"])
        negative = next(case for case in cases if case["test_type"] == "negative")
        self.assertNotIn("id", negative["request_config"]["body"]["json"])

    def test_llm_generation_is_validated(self):
        payload = {
            "cases": [
                {
                    "name": "AI 正向用例",
                    "test_type": "positive",
                    "description": "llm generated",
                    "request_config": {"method": "GET", "url": "/pets"},
                    "assertions": [{"type": "status_code", "expected": 200}],
                    "priority": 1,
                },
                {"name": "", "test_type": "bad"},
            ]
        }
        llm = FakeLLM(reply=json.dumps(payload))
        cases = generate_endpoint_cases(self._endpoint(), llm_service=llm)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["name"], "AI 正向用例")
        self.assertEqual(cases[0]["source"], "ai")

    def test_llm_garbage_falls_back_to_rules(self):
        llm = FakeLLM(reply="这不是 JSON")
        cases = generate_endpoint_cases(self._endpoint(), llm_service=llm)
        self.assertEqual(len(cases), 4)

    def test_generate_scenario_degrades_to_rules(self):
        self.create_endpoint(path="/pets", method="get", summary="宠物列表")
        llm = FakeLLM(error=RuntimeError("no ai_core"))
        result = generate_scenario("请测试 /pets 接口的返回结果", self.project, llm_service=llm)
        self.assertEqual(result["source"], "rule")
        self.assertEqual(len(result["cases"]), 1)
        case = result["cases"][0]
        self.assertEqual(case["case_type"], "scenario")
        steps = case["request_config"]["steps"]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["request_config"]["url"], "/pets")
        self.assertTrue(steps[0]["assertions"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
