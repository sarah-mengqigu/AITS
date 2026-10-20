"""Service layer tests: locustfile generation and statistics parsing."""

from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.common.api.api_exception_handler import BusinessError
from apps.performance.services.script_generator import (
    build_plan,
    estimate_endpoint_count,
    generate_locust_script,
    normalize_custom_script,
)
from apps.performance.services.stats import (
    compute_summary,
    parse_locust_csv,
    parse_stats_csv_text,
)
from apps.performance.tests.base import PerformanceFixture

STATS_CSV = (
    "Type,Name,Request Count,Failure Count,Median Response Time,"
    "Average Response Time,Min Response Time,Max Response Time,"
    "Average Content Size,Requests/s,Failures/s,50%,66%,75%,80%,90%,95%,98%,99%,"
    "99.9%,99.99%,100%\n"
    ',"Aggregated",1000,10,120,150,50,900,0,25.5,0.25,'
    "120,130,140,145,150,320,400,480,600,700,900\n"
    "GET,/api/users,600,0,110,130,50,400,0,15.0,0.0,"
    "110,115,120,125,130,200,220,240,300,350,400\n"
    "POST,/api/users,400,10,140,170,60,900,0,10.5,0.25,"
    "140,150,160,170,180,420,500,600,700,800,900\n"
)

HISTORY_CSV = (
    "Timestamp,User Count,Type,Name,Requests/s,Failures/s,"
    "Median Response Time,Average Response Time,Min Response Time,"
    "Max Response Time,Average Content Size,Requests,Failures\n"
    "1,10,,Aggregated,10.0,0.0,100,110,50,200,0,100,0\n"
    "2,10,,Aggregated,20.0,1.0,120,130,50,300,0,300,2\n"
    "3,10,,Aggregated,22.0,1.0,130,140,50,320,0,520,3\n"
)


class ScriptGeneratorTests(PerformanceFixture):
    def test_api_suite_script_contains_httpuser_and_compiles(self):
        first = self.create_api_case(name="用户列表", request_config={
            "method": "GET",
            "url": "/api/users",
            "params": {"limit": 10},
            "headers": {"Accept": "application/json"},
        })
        second = self.create_api_case(name="创建用户", request_config={
            "method": "POST",
            "url": "/api/users",
            "body": {"name": "demo"},
        }, assertions=[{"type": "status_code", "expected": 201}])
        suite = self.create_api_suite([first, second])
        scenario = self.create_scenario(source_type="api_suite", suite=suite)

        script = generate_locust_script(scenario)

        self.assertIn("from locust import HttpUser, task, between", script)
        self.assertIn("class AITSPerformanceUser(HttpUser)", script)
        self.assertGreaterEqual(script.count("@task"), 2)
        self.assertIn("catch_response=True", script)
        self.assertIn("response.failure", script)
        # The contract requires a real compile check.
        compile(script, "<locustfile>", "exec")
        self.assertEqual(estimate_endpoint_count(scenario), 2)

    def test_api_case_source_generates_single_task(self):
        case = self.create_api_case(name="健康检查", request_config={
            "method": "GET", "url": "/health",
        })
        scenario = self.create_scenario(source_type="api_case", case=case)

        script = generate_locust_script(scenario)

        self.assertIn("HttpUser", script)
        self.assertEqual(script.count("@task"), 1)
        compile(script, "<locustfile>", "exec")

    def test_custom_script_normalisation_adds_import_and_compiles(self):
        source = (
            "class MyUser(HttpUser):\n"
            "    @task\n"
            "    def index(self):\n"
            "        self.client.get('/')\n"
        )
        scenario = self.create_scenario(source_type="custom_script", custom_script=source)

        script = generate_locust_script(scenario)

        self.assertIn("from locust import HttpUser, task, between", script)
        self.assertIn("class MyUser(HttpUser)", script)
        compile(script, "<locustfile>", "exec")

    def test_custom_script_without_user_class_gets_default_user(self):
        scenario = self.create_scenario(
            source_type="custom_script", custom_script="VALUE = 1\n"
        )
        script = generate_locust_script(scenario)
        self.assertIn("HttpUser", script)
        self.assertIn("class AITSPerformanceUser", script)
        compile(script, "<locustfile>", "exec")

    def test_empty_custom_script_falls_back_to_default_user(self):
        script = normalize_custom_script(
            "", {"host": "https://x.test", "users": 5,
                 "spawn_rate": 5, "duration_seconds": 5}
        )
        self.assertIn("class AITSPerformanceUser(HttpUser)", script)
        compile(script, "<locustfile>", "exec")

    def test_invalid_custom_script_raises_business_error(self):
        scenario = self.create_scenario(
            source_type="custom_script", custom_script="def broken(:\n    pass\n"
        )
        with self.assertRaises(BusinessError) as ctx:
            generate_locust_script(scenario)
        self.assertEqual(ctx.exception.biz_code, "invalid_locust_script")

    def test_variables_and_config_are_injected(self):
        case = self.create_api_case(request_config={
            "method": "GET",
            "url": "/api/${version}/users",
            "headers": {"X-Token": "${token}"},
        })
        suite = self.create_api_suite([case])
        config = self.create_config(
            users=25, spawn_rate=5, duration_seconds=10, host="https://perf.example.com",
            config={"error_rate": 0.05, "custom_key": "kept"},
        )
        scenario = self.create_scenario(
            source_type="api_suite", suite=suite, config=config,
            variables={"version": "v2", "token": "abc"},
        )

        script = generate_locust_script(scenario)
        self.assertIn("/api/v2/users", script)
        self.assertIn("abc", script)
        self.assertIn("https://perf.example.com", script)
        compile(script, "<locustfile>", "exec")

        plan = build_plan(scenario, config)
        self.assertEqual(plan["users"], 25)
        self.assertEqual(plan["spawn_rate"], 5.0)
        self.assertEqual(plan["duration_seconds"], 10)
        self.assertEqual(plan["host"], "https://perf.example.com")
        self.assertEqual(plan["options"], {"error_rate": 0.05, "custom_key": "kept"})
        self.assertEqual(plan["scenario_id"], scenario.id)
        self.assertIn("HttpUser", plan["script"])

    def test_default_load_settings_without_config(self):
        scenario = self.create_scenario(source_type="api_case")
        plan = build_plan(scenario, None)
        self.assertGreaterEqual(plan["users"], 1)
        self.assertGreaterEqual(plan["duration_seconds"], 1)
        self.assertTrue(plan["host"].startswith("http"))


class StatsTests(SimpleTestCase):
    def test_compute_summary_percentiles_error_rate_and_status_codes(self):
        samples = [
            {"elapsed": 1, "requests": 100, "failures": 5,
             "response_time_ms": 100, "status_code": 200},
            {"elapsed": 2, "requests": 50, "failures": 0,
             "response_time_ms": 500, "status_code": 500},
            {"elapsed": 3, "requests": 50, "failures": 0,
             "response_time_ms": 300, "status_code": 200},
        ]
        summary = compute_summary(samples)

        self.assertEqual(summary["total_requests"], 200)
        self.assertEqual(summary["failures"], 5)
        self.assertAlmostEqual(summary["error_rate"], 0.025)
        self.assertEqual(summary["status_code_dist"], {"200": 150, "500": 50})
        self.assertGreater(summary["avg_tps"], 0)
        self.assertLessEqual(summary["p50_response_time"], summary["p95_response_time"])
        self.assertLessEqual(summary["p95_response_time"], summary["p99_response_time"])
        self.assertEqual(summary["p95_response_time"], 500)
        self.assertEqual(summary["p99_response_time"], 500)

    def test_compute_summary_empty_input_returns_zeros(self):
        for value in ([], None, [{}], "not-a-list"):
            summary = compute_summary(value)
            self.assertEqual(summary["total_requests"], 0)
            self.assertEqual(summary["failures"], 0)
            self.assertEqual(summary["avg_tps"], 0.0)
            self.assertEqual(summary["p95_response_time"], 0)
            self.assertEqual(summary["error_rate"], 0.0)
            self.assertEqual(summary["status_code_dist"], {})

    def test_parse_stats_csv_text_uses_aggregated_row(self):
        parsed = parse_stats_csv_text(STATS_CSV)

        self.assertEqual(parsed["total_requests"], 1000)
        self.assertEqual(parsed["failures"], 10)
        self.assertAlmostEqual(parsed["error_rate"], 0.01)
        self.assertEqual(parsed["avg_tps"], 25.5)
        self.assertEqual(parsed["p50_response_time"], 120)
        self.assertEqual(parsed["p95_response_time"], 320)
        self.assertEqual(parsed["p99_response_time"], 480)
        self.assertEqual(len(parsed["aggregated"]), 2)
        self.assertEqual(parsed["aggregated"][0]["name"], "/api/users")

    def test_parse_stats_history_uses_last_cumulative_snapshot(self):
        parsed = parse_stats_csv_text(HISTORY_CSV)

        self.assertEqual(parsed["total_requests"], 520)
        self.assertEqual(parsed["failures"], 3)
        self.assertAlmostEqual(parsed["error_rate"], round(3 / 520, 6))
        self.assertAlmostEqual(parsed["avg_tps"], 17.33, places=2)
        self.assertEqual(parsed["p50_response_time"], 130)

    def test_parse_stats_history_prefers_aggregated_rows(self):
        interleaved = HISTORY_CSV + (
            "4,10,GET,/api/users,5.0,0.0,90,100,40,150,0,999,0\n"
        )
        parsed = parse_stats_csv_text(interleaved)
        self.assertEqual(parsed["total_requests"], 520)
        self.assertEqual(parsed["failures"], 3)

    def test_parse_stats_csv_text_empty_and_invalid(self):
        for text in ("", "   ", "Name\n", "not,csv,at,all"):
            parsed = parse_stats_csv_text(text)
            self.assertEqual(parsed["total_requests"], 0)
            self.assertEqual(parsed["status_code_dist"], {})

    def test_parse_locust_csv_from_directory_and_missing_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "locust_stats.csv").write_text(STATS_CSV, encoding="utf-8")
            (directory / "locust_stats_history.csv").write_text(
                HISTORY_CSV, encoding="utf-8"
            )
            parsed = parse_locust_csv(directory)
            self.assertEqual(parsed["total_requests"], 1000)
            self.assertEqual(parsed["p95_response_time"], 320)
            self.assertEqual(len(parsed["source_files"]), 2)

            parsed_file = parse_locust_csv(directory / "locust_stats.csv")
            self.assertEqual(parsed_file["total_requests"], 1000)

            empty = parse_locust_csv(directory / "missing")
            self.assertEqual(empty["total_requests"], 0)

    def test_parse_locust_csv_fills_tps_from_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "locust_stats.csv").write_text(
                "Type,Name,Request Count,Failure Count,Median Response Time\n",
                encoding="utf-8",
            )
            (directory / "locust_stats_history.csv").write_text(
                HISTORY_CSV, encoding="utf-8"
            )
            parsed = parse_locust_csv(directory)
            self.assertEqual(parsed["total_requests"], 520)
            self.assertGreater(parsed["avg_tps"], 0)
