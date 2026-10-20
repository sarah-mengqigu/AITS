"""Seed a complete, demo-ready AITS workspace.

The command drives the platform through its **public HTTP API** (Django test
client + session auth), so it doubles as a real end-to-end smoke test:

    python manage.py seed_demo            # idempotent create
    python manage.py seed_demo --reset    # drop the demo user's data first

After running you can log in with `admin` / `Admin@12345` and every module has
data: API specs/endpoints/cases/suites/executions, Web + App suites, a load
test scenario, AI model/RAG/MCP configs, a notification receiver and a
scheduled task with execution logs.
"""

from __future__ import annotations

import io
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.test import Client

User = get_user_model()

DEMO_USERNAME = "admin"
DEMO_EMAIL = "admin@aits.local"
DEMO_PASSWORD = "Admin@12345"

OPENAPI_SPEC = """openapi: 3.0.3
info:
  title: AITS 演示商城 API
  version: 1.0.0
servers:
  - url: https://demo.aits.local
paths:
  /api/v1/products:
    get:
      operationId: listProducts
      summary: 商品列表
      parameters:
        - name: page
          in: query
          schema: { type: integer, example: 1 }
        - name: keyword
          in: query
          schema: { type: string }
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema:
                type: object
                properties:
                  total: { type: integer }
                  items:
                    type: array
                    items:
                      type: object
                      properties:
                        id: { type: integer }
                        name: { type: string }
                        price: { type: number }
    post:
      operationId: createProduct
      summary: 创建商品
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                name: { type: string, example: 演示商品 }
                price: { type: number, example: 9.9 }
              required: [name]
      responses:
        '201': { description: created }
  /api/v1/orders:
    post:
      operationId: createOrder
      summary: 下单
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                product_id: { type: integer, example: 1 }
                quantity: { type: integer, example: 2 }
      responses:
        '201': { description: created }
  /api/v1/users/{userId}:
    get:
      operationId: getUser
      summary: 用户详情
      parameters:
        - name: userId
          in: path
          required: true
          schema: { type: string }
      responses:
        '200': { description: ok }
"""

LOCUST_SCRIPT = """from locust import HttpUser, task, between


class DemoShopUser(HttpUser):
    wait_time = between(1, 2)

    @task(3)
    def list_products(self):
        self.client.get("/api/v1/products?page=1")

    @task(1)
    def create_order(self):
        self.client.post("/api/v1/orders", json={"product_id": 1, "quantity": 1})
"""


class Command(BaseCommand):
    help = "Seed a demo AITS workspace through the public HTTP API."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="delete the demo user's projects before seeding")

    def handle(self, *args, **options):
        client = Client()
        user, created = User.objects.get_or_create(
            username=DEMO_USERNAME,
            defaults={"email": DEMO_EMAIL, "nickname": "演示管理员",
                      "is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"created demo user {DEMO_USERNAME}"))
        else:
            self.stdout.write(f"demo user exists: {DEMO_USERNAME}")

        if options["reset"]:
            from apps.projects.models import Project

            deleted, _ = Project.objects.filter(owner=user).delete()
            self.stdout.write(f"reset removed {deleted} objects")

        client.force_login(user)

        api_project = self._project(client, "演示商城 · 接口测试", "api")
        api_env = self._environment(client, api_project, "测试环境",
                                    "https://demo.aits.local")
        spec = self._import_spec(client, api_project)
        cases = self._generate_cases(client, api_project)
        api_suite = self._suite(client, api_project, "商品核心链路回归",
                                [c["id"] for c in cases[:6]], api_env)
        api_execution = self._run_api_suite(client, api_suite)
        self._api_category(client, api_project)

        web_project = self._project(client, "演示商城 · Web 测试", "web")
        web_env = self._environment(client, web_project, "预发布", "https://demo.aits.local")
        web_case = self._web_case(client, web_project)
        self._web_pom(client, web_project)
        web_suite = self._suite(client, web_project, "登录与下单 E2E", [web_case["id"]], web_env)
        web_execution = self._run(client, "web-testing", web_suite["id"])

        app_project = self._project(client, "演示商城 · App 测试", "app")
        app_case = self._app_case(client, app_project)
        app_suite = self._suite(client, app_project, "App 冒烟", [app_case["id"]], None,
                                extra={"application": app_case["application"]})
        app_run = self._run(client, "app-testing", app_suite["id"])

        perf_project = self._project(client, "演示商城 · 性能压测", "perf",
                                     linked_api_projects=[api_project["id"]])
        perf_config = self._post(client, "/api/performance/configs/", {
            "project": perf_project["id"], "name": "基线 50 并发",
            "users": 50, "spawn_rate": 5, "duration_seconds": 60,
            "host": "https://demo.aits.local",
        })
        perf_scenario = self._post(client, "/api/performance/scenarios/", {
            "project": perf_project["id"], "name": "商品列表压测",
            "source_type": "api_suite", "source_suite": api_suite["id"],
            "endpoint_count": len(cases), "config": perf_config["id"],
        })
        perf_execution = self._run_scenario(client, perf_scenario["id"])

        self._ai_configs(client, api_project)
        receiver = self._receiver(client, api_project)
        scheduled = self._scheduled_task(client, api_project, api_suite, receiver)
        scheduled_status = self._run_scheduled_task(client, scheduled)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("═" * 62))
        self.stdout.write(self.style.SUCCESS("  AITS 演示数据已就绪"))
        self.stdout.write(self.style.SUCCESS("═" * 62))
        self.stdout.write(f"  登录账号：{DEMO_USERNAME} / {DEMO_PASSWORD}")
        self.stdout.write(f"  接口测试：{api_project['name']}（{spec.get('endpoint_count')} 端点 / "
                          f"{len(cases)} 用例 / 套件执行 {api_execution.get('status')}）")
        self.stdout.write(f"  Web 测试：{web_project['name']}（执行 {web_execution.get('status')}）")
        self.stdout.write(f"  App 测试：{app_project['name']}（执行 {app_run.get('status')}）")
        self.stdout.write(f"  性能测试：{perf_project['name']}（执行 {perf_execution.get('status')}）")
        self.stdout.write(f"  定时任务：{scheduled['name']}（{scheduled['cron_expression']}）"
                          f"最近一次：{scheduled_status}")
        self.stdout.write("")

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------
    def _post(self, client, url, payload):
        resp = client.post(url, data=json.dumps(payload), content_type="application/json")
        if resp.status_code not in (200, 201, 202):
            raise RuntimeError(f"POST {url} -> {resp.status_code}: {resp.content[:400]}")
        return resp.json()

    def _patch(self, client, url, payload):
        resp = client.patch(url, data=json.dumps(payload), content_type="application/json")
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"PATCH {url} -> {resp.status_code}: {resp.content[:400]}")
        return resp.json()

    def _get(self, client, url):
        resp = client.get(url)
        if resp.status_code != 200:
            raise RuntimeError(f"GET {url} -> {resp.status_code}: {resp.content[:400]}")
        return resp.json()

    def _project(self, client, name, project_type, **extra):
        from apps.projects.models import Project

        existing = Project.objects.filter(name=name, owner__username=DEMO_USERNAME).first()
        if existing:
            return {"id": existing.id, "name": existing.name,
                    "project_type": existing.project_type}
        payload = {"name": name, "project_type": project_type,
                   "description": f"{name}（演示数据）"}
        payload.update(extra)
        created_project = self._post(client, "/api/projects/", payload)
        created_project.setdefault("project_type", project_type)
        return created_project

    def _environment(self, client, project, name, base_url):
        from apps.projects.models import Environment

        existing = Environment.objects.filter(project_id=project["id"], name=name).first()
        if existing:
            return {"id": existing.id}
        return self._post(client, "/api/projects/environments/", {
            "project": project["id"], "name": name, "env_type": "test",
            "base_url": base_url, "variables": {"tenant": "demo"},
            "headers": {"Accept": "application/json"}, "is_default": True,
        })

    def _import_spec(self, client, project):
        from apps.api_testing.models import APISpecification

        existing = APISpecification.objects.filter(project_id=project["id"]).first()
        if existing:
            return {"id": existing.id, "endpoint_count": existing.endpoint_count}
        upload = io.BytesIO(OPENAPI_SPEC.encode())
        upload.name = "demo-shop.yaml"
        resp = client.post(
            "/api/api-testing/specs/import/",
            {"project": project["id"], "file": upload, "base_url": "https://demo.aits.local"},
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"spec import -> {resp.status_code}: {resp.content[:400]}")
        return resp.json()

    def _generate_cases(self, client, project):
        from apps.api_testing.models import APITestCase
        from apps.api_testing.models import APIEndpoint

        existing = list(APITestCase.objects.filter(project_id=project["id"]))
        if existing:
            return self._get(client, f"/api/api-testing/cases/?project={project['id']}&page_size=100")["results"]
        endpoints = self._get(
            client, f"/api/api-testing/endpoints/?project={project['id']}&page_size=100"
        )["results"]
        for endpoint in endpoints:
            client.post(f"/api/api-testing/endpoints/{endpoint['id']}/generate_cases/",
                        data="{}", content_type="application/json")
        return self._get(
            client, f"/api/api-testing/cases/?project={project['id']}&page_size=100"
        )["results"]

    def _suite(self, client, project, name, case_ids, env, extra=None):
        payload = {"project": project["id"], "name": name,
                   "description": f"{name}（演示）", "case_ids": case_ids}
        if env:
            payload["environment"] = env["id"]
        payload.update(extra or {})
        return self._post(client, f"/api/{self._module(project)}/suites/", payload)

    @staticmethod
    def _module(project):
        return {"api": "api-testing", "web": "web-testing", "app": "app-testing",
                "perf": "performance"}[project.get("project_type", "api")]

    def _run(self, client, module, suite_id):
        resp = client.post(f"/api/{module}/suites/{suite_id}/run/",
                           data="{}", content_type="application/json")
        if resp.status_code not in (200, 202):
            raise RuntimeError(f"run {module}/{suite_id} -> {resp.status_code}: {resp.content[:300]}")
        data = resp.json()
        module_model = {
            "api-testing": ("api_testing", "APITestExecution"),
            "web-testing": ("web_testing", "WebUITestExecution"),
            "app-testing": ("app_testing", "AppTestRun"),
        }[module]
        execution_id = (data.get("execution_id") or data.get("run_id")
                        or data.get("task_id"))
        return self._execution_status(module_model, execution_id)

    @staticmethod
    def _execution_status(model_path, execution_id):
        import importlib

        app_name, model_name = model_path
        module = importlib.import_module(f"apps.{app_name}.models")
        model = getattr(module, model_name)
        instance = model.objects.filter(pk=execution_id).first()
        if instance is None:
            return {"status": "unknown"}
        return {"status": instance.status, "id": instance.id,
                "total": getattr(instance, "total", 0),
                "passed": getattr(instance, "passed", 0)}

    def _run_api_suite(self, client, suite):
        return self._run(client, "api-testing", suite["id"])

    def _run_scenario(self, client, scenario_id):
        resp = client.post(f"/api/performance/scenarios/{scenario_id}/run/",
                           data="{}", content_type="application/json")
        if resp.status_code not in (200, 202):
            raise RuntimeError(f"perf run -> {resp.status_code}: {resp.content[:300]}")
        data = resp.json()
        execution_id = data.get("execution_id") or data.get("task_id")
        return self._execution_status(("performance", "PerformanceExecution"), execution_id)

    # ------------------------------------------------------------------
    # module specific demo data
    # ------------------------------------------------------------------
    def _api_category(self, client, project):
        from apps.api_testing.models import APIModule

        if not APIModule.objects.filter(project_id=project["id"]).exists():
            self._post(client, "/api/api-testing/modules/", {
                "project": project["id"], "name": "商品中心",
                "description": "商品相关接口",
            })

    def _web_case(self, client, project):
        from apps.web_testing.models import WebUITestCase

        existing = WebUITestCase.objects.filter(project_id=project["id"]).first()
        if existing:
            return {"id": existing.id}
        return self._post(client, "/api/web-testing/cases/", {
            "project": project["id"],
            "name": "登录 → 搜索商品 → 下单",
            "description": "核心购买链路",
            "steps": [
                {"action": "goto", "target": "/login", "value": ""},
                {"action": "fill", "target": "#username", "value": "demo"},
                {"action": "fill", "target": "#password", "value": "demo123"},
                {"action": "click", "target": "#login-submit",
                 "expect": "商品列表", "actual": "商品列表"},
                {"action": "fill", "target": "[data-testid=search]", "value": "耳机"},
                {"action": "click", "target": "[data-testid=search-submit]",
                 "expect": "耳机", "actual": "耳机"},
                {"action": "click", "target": "[data-testid=buy-now]",
                 "expect": "订单", "actual": "订单"},
            ],
            "priority": "high",
        })

    def _web_pom(self, client, project):
        from apps.web_testing.models import WebPage

        existing = WebPage.objects.filter(project_id=project["id"]).first()
        if existing:
            return {"id": existing.id}
        page = self._post(client, "/api/web-testing/pages/", {
            "project": project["id"], "name": "登录页", "url": "/login",
            "description": "商城登录页",
        })
        self._post(client, "/api/web-testing/elements/", {
            "page": page["id"], "name": "用户名输入框", "locator_type": "css",
            "locator_value": "#username", "description": "账号输入",
        })
        self._post(client, "/api/web-testing/elements/", {
            "page": page["id"], "name": "登录按钮", "locator_type": "testid",
            "locator_value": "login-submit",
            "alternatives": [{"type": "text", "value": "登录"}],
        })
        return page

    def _app_case(self, client, project):
        from apps.app_testing.models import AppTestCase

        existing = AppTestCase.objects.filter(project_id=project["id"]).first()
        if existing:
            return {"id": existing.id, "application": existing.application_id}
        application = self._post(client, "/api/app-testing/applications/", {
            "project": project["id"], "name": "演示商城 App", "platform": "android",
            "package_name": "com.aits.demo", "app_version": "1.0.0",
        })
        case = self._post(client, "/api/app-testing/cases/", {
            "project": project["id"], "application": application["id"],
            "name": "启动 App → 登录 → 下单",
            "description": "移动端核心链路",
            "steps": [
                {"action": "start_app", "target": "com.aits.demo", "value": ""},
                {"action": "tap", "target": "我的", "value": ""},
                {"action": "tap", "target": "登录", "value": ""},
                {"action": "input", "target": "手机号", "value": "13800000000"},
                {"action": "input", "target": "验证码", "value": "123456"},
                {"action": "tap", "target": "确认", "expect": "首页"},
                {"action": "tap", "target": "立即购买", "expect": "订单确认"},
            ],
            "priority": "high",
        })
        case["application"] = application["id"]
        return case

    def _ai_configs(self, client, project):
        from apps.ai_core.models import LLMConfiguration, MCPConfiguration, RAGConfiguration

        if not LLMConfiguration.objects.filter(name="演示 Mock 模型").exists():
            self._post(client, "/api/ai/llm-configs/", {
                "project": project["id"], "name": "演示 Mock 模型",
                "provider": "mock", "model_name": "mock-gpt", "model_type": "text",
                "temperature": 0.2, "max_tokens": 2048, "is_default": True,
                "is_active": True,
            })
        if not RAGConfiguration.objects.filter(name="演示知识库").exists():
            self._post(client, "/api/ai/rag-configs/", {
                "project": project["id"], "name": "演示知识库",
                "vector_store": "chroma", "embedding_mode": "local",
                "embedding_model": "BAAI/bge-large-zh-v1.5",
                "chunk_size": 1000, "chunk_overlap": 200,
                "collection_name": "demo_knowledge", "is_default": True,
            })
        if not MCPConfiguration.objects.filter(name="演示 MCP 文件系统").exists():
            self._post(client, "/api/ai/mcp-configs/", {
                "project": project["id"], "name": "演示 MCP 文件系统",
                "transport": "stdio",
                "server_config": {"command": "npx",
                                  "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]},
                "is_active": True,
            })

    def _receiver(self, client, project):
        from apps.notifications.models import NotificationChannel, NotificationReceiver

        channel = NotificationChannel.objects.filter(channel_code="dingtalk").first()
        if channel is None:
            channel = NotificationChannel.objects.create(
                channel_code="dingtalk", name="钉钉", is_active=True
            )
        existing = NotificationReceiver.objects.filter(
            project_id=project["id"], name="QA 演示群"
        ).first()
        if existing:
            return {"id": existing.id}
        return self._post(client, "/api/notifications/receivers/", {
            "project": project["id"], "name": "QA 演示群", "channel": channel.id,
            "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=demo",
            "is_active": False,
            "description": "演示接收人（未启用，避免真实发送）",
        })

    def _run_scheduled_task(self, client, task):
        from apps.scheduled_tasks.models import TaskExecutionLog

        if TaskExecutionLog.objects.filter(task_id=task["id"]).exists():
            latest = TaskExecutionLog.objects.filter(task_id=task["id"]).first()
            return latest.status
        resp = client.post(f"/api/scheduled-tasks/tasks/{task['id']}/run/",
                           data="{}", content_type="application/json")
        if resp.status_code not in (200, 202):
            return f"run failed ({resp.status_code})"
        log_id = resp.json().get("log_id") or resp.json().get("task_id")
        log = TaskExecutionLog.objects.filter(pk=log_id).first()
        return log.status if log else "unknown"

    def _scheduled_task(self, client, project, suite, receiver):
        from apps.scheduled_tasks.models import ScheduledTask

        existing = ScheduledTask.objects.filter(
            project_id=project["id"], name="每日 9 点接口回归"
        ).first()
        if existing:
            return {"id": existing.id, "name": existing.name,
                    "cron_expression": existing.cron_expression}
        return self._post(client, "/api/scheduled-tasks/tasks/", {
            "project": project["id"], "name": "每日 9 点接口回归",
            "suite_type": "api", "suite_ids": [suite["id"]],
            "cron_expression": "0 9 * * 1-5", "trigger_condition": "fail",
            "notice_targets": [receiver["id"]], "is_enabled": True,
            "description": "工作日每天 9 点执行接口回归，仅在失败时通知",
        })
