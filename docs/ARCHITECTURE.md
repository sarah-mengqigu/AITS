# AITS v2 架构与模块契约（ARCHITECTURE）

> 本文件是并行开发的**唯一契约**。所有模块开发者必须遵守；如需变更契约，先改本文件并在 PR 说明中标注。
> 代码根：`/Users/gumengqi/Projects/AITS`，后端根：`backend/`，前端根：`frontend/`。
> Python 解释器：`backend/.venv/bin/python`（已装 Django 4.2.25 / DRF / Celery / Channels / simplejwt 等）。

---

## 1. 全局约定

### 1.1 应用与目录
- 9 个业务 app：`apps/{users,projects,api_testing,web_testing,app_testing,performance,ai_core,scheduled_tasks,notifications}` + 公共层 `apps/common`。
- 每个 app 的标准结构：
  ```
  apps/<app>/
    apps.py models.py serializers.py views.py urls.py admin.py
    services/            # 业务服务（纯函数优先，便于单测）
    tasks.py             # Celery 任务（@shared_task）
    tests/test_*.py      # 必须 >= 8 个用例
    migrations/
  ```
- **文件所有权**：并行开发时只能修改自己负责的 app 目录（含其 `migrations/`）。禁止修改 `aits_backend/settings.py`、`aits_backend/urls.py`、`aits_backend/asgi.py`、`apps/common/*`、`apps/users/*`、`apps/projects/*`。确有共享改动需求 → 在交付说明中列出，由集成阶段统一处理。

### 1.2 URL 前缀（已在根 urls 固定，模块内用 DRF Router 注册相对路径）
| 前缀 | app |
|---|---|
| `/api/auth/` | users（`urls_auth.py`） |
| `/api/users/` | users |
| `/api/projects/` | projects |
| `/api/api-testing/` | api_testing |
| `/api/web-testing/` | web_testing |
| `/api/app-testing/` | app_testing |
| `/api/performance/` | performance |
| `/api/ai/` | ai_core |
| `/api/scheduled-tasks/` | scheduled_tasks |
| `/api/notifications/` | notifications |
| `/api/monitoring/` + `/health/` + `/metrics/` | common |

### 1.3 模型基类
```python
from apps.common.models import TimeStampedModel   # created_at / updated_at
```
- 主键默认 `BigAutoField`。
- 业务对象必须挂 `project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="...")`，且**每个 app 对 Project 使用唯一 related_name**（见 §2 分配表），避免反向名冲突。
- JSON 字段统一 `models.JSONField(default=list/dict, blank=True)`。
- 状态字段用 `choices` + 字符串常量，禁止魔法数字。

### 1.4 权限
```python
from apps.common.permissions import ProjectRolePermission, get_user_role, require_project_role
```
- 角色层级：`viewer(10) < editor(20) < admin(30) < owner(40)`。
- 列表/详情：`viewer` 可读；写用例/套件/执行：`editor`；成员/配置/删除：`admin`/`owner`。
- 项目作用域查询统一：非 superuser 仅返回 `owner=user` 或 `members__user=user` 的项目数据（参考 `apps/projects/views.py:projects_for`）。
- 复用 `apps.projects.views.ProjectScopedViewSet`（`project_field` 可覆盖）作为基类。

### 1.5 错误与响应
- 异常统一由 `apps.common.api.api_exception_handler.custom_exception_handler` 包装为
  `{"code": "...", "message": "...", "errors": {...}, "status_code": N}`。
- 业务错误抛 `BusinessError(message=..., code=..., status_code=...)`。
- 成功响应使用 DRF 原生结构；列表使用 `apps.common.pagination.StandardResultsSetPagination`
  → `{count, page, page_size, total_pages, next, previous, results}`。
- 长任务（执行/生成）返回 `202 + {"task_id": "...", "status": "pending"}`，进度走 WebSocket。

### 1.6 WebSocket
```python
from apps.common.websocket.core import WebSocketMessageService
WebSocketMessageService.push_task_status(task_id, status="running", progress=30, message="执行中")
WebSocketMessageService.push_stream("scenario_generation", task_id, {"type": "stream_chunk", "chunk": "..."})
```
已注册的 WebSocket 路由（`aits_backend/asgi.py`，均有测试覆盖）：
- `ws/task-status/<task_id>/?token=<access>` —— 任务状态帧 `{"type":"task_status",...}`
- `ws/scenario_generation-streaming/?token=<access>[&task_id=<id>]`
- `ws/midscene_script_generation-streaming/?token=<access>[&task_id=<id>]`
- `ws/webui_test_generation-streaming/?token=<access>[&task_id=<id>]`
- `ws/webui_auto_test-streaming/?token=<access>[&task_id=<id>]`

流通道带 `task_id` 时只接收该任务的帧；省略则接收该通道全部帧（帧内自带 `task_id`）。
业务侧统一用 `WebSocketMessageService.push_stream(channel, task_id, payload)`，
它会同时投递到任务级组与通道级组。

### 1.7 异步任务
```python
from celery import shared_task
from apps.common.task.utils import submit, push_progress

@shared_task(bind=True, name="api_testing.run_suite")
def run_suite(self, execution_id): ...

submit(run_suite, execution.id)   # 测试环境自动 eager 执行
```
- `settings.CELERY_TASK_ALWAYS_EAGER = True`（`AITS_ENV=test`），因此测试中 `submit()` 同步执行完毕，可直接断言 DB 状态。
- 任务必须**幂等**、捕获异常并写回执行记录状态，绝不能让异常穿透导致记录停留在 running。

### 1.8 执行引擎降级
`settings.AITS_EXECUTION_MODE ∈ {simulated, real}`，默认 `simulated`。
- `simulated`：不启动子进程/浏览器/压测机，用确定性规则产生真实结构的报告与统计（用于测试、演示、CI）。
- `real`：调用 Playwright / Locust / HttpRunner / Sonic。
- 每个执行器必须是 `BaseRunner` 子类（定义在各 app `services/runners.py`），对外统一：
  ```python
  class BaseRunner:
      def run(self, plan: dict, on_progress: Callable[[int, str], None] | None = None) -> dict
      # 返回 {"status": "passed|failed|error", "cases": [{...}], "summary": {...}, "artifacts": {...}}
  ```

### 1.9 测试要求（每个模块验收门槛）
- `cd backend && AITS_ENV=test .venv/bin/python manage.py test apps.<app> -v 1` 全绿。
- ≥ 8 个测试用例，覆盖：CRUD 正常路径、权限拒绝、参数校验失败、服务层纯逻辑、降级路径。
- 用 `rest_framework.test.APIClient` + `force_authenticate`；工厂数据直接 `Model.objects.create`。
- **不要**在测试里访问外网、真实 Redis、真实 Sonic/Grafana/LLM。
- 迁移：`AITS_ENV=test .venv/bin/python manage.py makemigrations <app>`（只迁移自己的 app）。

### 1.10 共享 Project 反向名分配（禁止冲突）
| app | related_name 前缀 |
|---|---|
| api_testing | `api_specifications`, `api_modules`, `api_cases`, `api_suites`, `api_executions` |
| web_testing | `web_modules`, `web_cases`, `web_suites`, `web_executions`, `web_pages`, `midscene_scripts` |
| app_testing | `app_modules`, `app_applications`, `app_cases`, `app_runs`, `app_suites` |
| performance | `load_configs`, `performance_scenarios`, `performance_executions`, `ai_diagnosis_records` |
| ai_core | `llm_configs`, `rag_configs`, `mcp_configs`, `llm_usage_logs` |
| scheduled_tasks | `scheduled_tasks` |
| notifications | `notification_receivers`, `notification_logs` |

---

## 2. 模块契约

### 2.1 users（已完成，勿改）
`/api/auth/{register,login,refresh,verify,logout,me,change-password}/`；`/api/users/`（目录 + `brief/`）。

### 2.2 projects（已完成，勿改）
主要接口：
- `GET/POST /api/projects/`，`GET/PATCH/DELETE /api/projects/{id}/`
- `GET /api/projects/{id}/members/`，`POST /api/projects/{id}/members/add/`，`DELETE /api/projects/{id}/members/{member_id}/`
- `GET/PUT/PATCH /api/projects/{id}/third-party-config/`，`GET /api/projects/{id}/stats/`
- `GET/POST /api/projects/environments/`，`POST /api/projects/environments/{id}/set-default/`
- `GET/POST /api/projects/files/`（multipart，字段 `project`/`file`/`purpose`），`GET /api/projects/files/{id}/download/`
- `GET/POST /api/projects/knowledge/`，`POST /api/projects/knowledge/{id}/reindex/`

### 2.3 api_testing
模型（`apps/api_testing/models.py`）：
- `APISpecification(project, name, source_type∈{openapi,swagger,postman}, version, spec_data JSON, file FK UploadedFile null, base_url, status, endpoint_count)`
- `APIModule(project, spec FK, parent self null, name, description, order)`（树）
- `APIEndpoint(project, spec FK, module FK null, path, method, operation_id, summary, description, parameters JSON, request_body JSON, responses JSON, headers JSON, is_active)`
- `APITestCase(project, endpoint FK null, module FK null, name, case_type∈{endpoint,scenario}, test_type∈{positive,negative,boundary,security,performance}, description, request_config JSON, assertions JSON, extract JSON, hooks JSON, script_yaml Text, source∈{manual,ai,postman}, priority, is_active)`
- `APITestSuite(project, name, description, environment FK projects.Environment null, case_ids JSON, config JSON(Hook/重试/失败策略), source∈{manual,ai,postman}, is_active)`
- `APITestExecution(project, suite FK null, name, environment FK null, status∈{pending,running,passed,failed,error,cancelled}, trigger_type∈{manual,scheduled,api}, triggered_by FK User null, started_at, finished_at, duration_ms, total/passed/failed/skipped, pass_rate, report_path, summary JSON, error_message)`
- `APITestCaseExecutionDetail(execution, test_case FK null, case_name, status, duration_ms, request JSON, response JSON, assertions JSON, error_message, step_log JSON)`
- `APITestSuiteExecutionDetail(execution, suite FK null, suite_name, status, total/passed/failed, duration_ms, detail JSON)`

接口：
- `POST /api/api-testing/specs/import/`（multipart：`project`,`file` 或 body:`content`+`format`；可选 `base_url`）→ 解析并落库 endpoints；返回 spec + 统计
- `GET/POST /api/api-testing/specs/`，`GET/PATCH/DELETE /api/api-testing/specs/{id}/`，`POST .../{id}/reparse/`
- `GET/POST /api/api-testing/modules/`（`?project=`、`?spec=`、`tree/` action 返回树）
- `GET/POST /api/api-testing/endpoints/`（`?project=&module=&method=&search=`），`GET .../{id}/generate_cases/` 另提供 `POST .../{id}/generate_cases/`（AI/规则生成用例）
- `GET/POST /api/api-testing/cases/`，`POST .../{id}/generate_script/`（生成 HttpRunner YAML），`POST .../{id}/run/`（单用例执行）
- `GET/POST /api/api-testing/suites/`，`POST .../{id}/run/` → 202 `{task_id}`
- `GET /api/api-testing/executions/`，`GET .../{id}/`（含 details），`POST .../{id}/cancel/`，`GET .../{id}/report/`
- `POST /api/api-testing/postman/import/`（multipart collection + project）→ 解析 Collection v2.1（含 `pm.test` 规则转换）
- WebSocket：执行进度 `task_id` = execution.id

服务：
- `services/spec_parser.py`：`parse_openapi(content, base_url="") -> ParsedSpec`；`parse_postman(collection_json) -> list[ParsedRequest]`
- `services/script_builder.py`：`build_httprunner_yaml(case) -> str`、`build_case_from_endpoint(endpoint) -> dict`
- `services/runner.py`：`HttpRunnerRunner(BaseRunner)` + `SimulatedRunner`；执行 `request_config`（method/url/params/headers/body/assertions/extract），支持变量替换 `${var}` 与 extract 传递
- `services/execution.py`：`execute_suite(suite_id, environment_id=None, triggered_by=None, trigger_type="manual") -> execution_id`，供 scheduled_tasks 调用（**必须存在且可测试**）
- `services/generator.py`：`generate_endpoint_cases(endpoint, llm_service=None)` 规则生成正/负/边界/安全用例；`generate_scenario(natural_language, project, llm_service=None)` 调 ai_core `AIService`（失败时降级规则生成）

任务：`tasks.py::execute_suite_task(execution_id)`、`execute_case_task(execution_id)`。

### 2.4 web_testing
模型：
- `WebUITestModule(project, parent self, name, description, order)`（树）
- `WebUITestCase(project, module FK null, name, description, case_type∈{ui,api_mixed}, steps JSON, script Text, script_type∈{playwright,midscene}, pom_refs JSON, assertions JSON, source, priority, is_active)`
- `WebUITestSuite(project, name, description, case_ids JSON, environment FK null, browser, headless, config JSON, is_active)`
- `WebUITestExecution(project, suite FK null, name, status, trigger_type, triggered_by, browser, started_at, finished_at, duration_ms, total/passed/failed/skipped, pass_rate, report_path, allure_results_path, summary JSON, error_message)`
- `WebUITestCaseExecutionDetail(execution, test_case, case_name, status, duration_ms, steps JSON, screenshots JSON, error_message, step_log JSON)`
- `WebPage(project, name, url, description)` + `WebElement(page, name, locator_type, locator_value, description, alternatives JSON)`（POM）
- `MidSceneScript(project, name, description, script_type∈{yaml,python}, content, case FK null, status)`

接口：
- `GET/POST /api/web-testing/modules/`，`GET .../tree/`
- `GET/POST /api/web-testing/cases/`，`POST .../{id}/generate_script/`（AI→Playwright；降级模板），`POST .../{id}/run/`
- `GET/POST /api/web-testing/suites/`，`POST .../{id}/run/`
- `GET /api/web-testing/executions/`，`GET .../{id}/`，`POST .../{id}/cancel/`，`GET .../{id}/report/`
- `GET/POST /api/web-testing/pages/`、`/api/web-testing/elements/`（按页面过滤用 `?page_id=`；`?page=` 保留给分页器，避免参数冲突）
- `GET/POST /api/web-testing/midscene-scripts/`，`POST .../{id}/generate/`
- 服务：`services/runner.py`（`PlaywrightRunner` real / `SimulatedRunner` simulated，产出 Allure 兼容 `*-result.json` 到 `settings.ALLURE_RESULTS_ROOT`）、`services/execution.py::execute_suite(...)`、`services/generator.py`

### 2.5 app_testing
模型：
- `AppTestModule(project, parent self, name, order)`
- `AppTestApplication(project, name, platform∈{android,ios}, package_name, bundle_id, app_version, description)`
- `AppTestCase(project, module FK null, application FK null, name, description, steps JSON（AITS 内部步骤）, sonic_steps JSON（Sonic 兼容快照）, source, priority, is_active)`
- `AppTestSuite(project, name, description, case_ids JSON, app FK null, device_config JSON, is_active)`
- `AppTestRun(project, suite FK null, name, status, trigger_type, device_udid/device_id/device_name/platform, started_at/finished_at/duration_ms, total/passed/failed, pass_rate, sonic_suite_id, report_path, summary JSON, error_message)`

接口：
- modules / applications / cases / suites / runs CRUD（同上惯例）
- `GET /api/app-testing/devices/`（Sonic 设备列表代理，未配置返回空数组 + warning）
- `GET /api/app-testing/devices/{udid}/`，`POST /api/app-testing/devices/{udid}/remote/`（远控信息：jmuxer ws 地址）
- `GET /api/app-testing/element-pages/`（Sonic ElementPages 代理）
- `POST /api/app-testing/suites/{id}/run/`，`GET /api/app-testing/runs/{id}/`
- `POST /api/app-testing/cases/{id}/generate_steps/`（自然语言→步骤，调用 ai_core，降级规则）
- 服务：`services/sonic_client.py`（token 自动登录续期、`SonicAPIError` 映射 3001/3002/3003 中文文案）、`services/case_converter.py`（AITS steps ↔ Sonic steps）、`services/execution.py::execute_suite(...)`（simulated 用确定性结果）
- **无 Sonic 时必须优雅降级**：`SONIC_BASE_URL` 为空 → 抛 `BusinessError("未配置 Sonic 服务", code="sonic_not_configured")` 或返回空列表（读接口），不得 500。

### 2.6 performance
模型：
- `LoadConfiguration(project, name, users, spawn_rate, duration_seconds, host, config JSON, description)`
- `PerformanceScenario(project, name, description, source_type∈{api_suite,api_case,custom_script}, source_suite FK api_testing.APITestSuite null, source_case FK api_testing.APITestCase null, custom_script Text, endpoint_count, config FK LoadConfiguration null, variables JSON, is_active)`
- `PerformanceExecution(project, scenario FK, config FK null, name, status, trigger_type, started_at/finished_at/duration_ms, total_requests, avg_tps, p50/p95/p99_response_time, error_rate, status_code_dist JSON, csv_path, report_path, summary JSON, celery_task_id, error_message)`
- `AiDiagnosisRecord(project, execution FK null, source∈{grafana,manual}, alert_name, severity, grafana_url, diagnosis_content, status∈{pending,resolved,ignored}, notified_at, resolved_at, raw_payload JSON)`

接口：
- `GET/POST /api/performance/configs/`
- `GET/POST /api/performance/scenarios/`，`POST .../{id}/generate_script/`（locustfile）
- `GET/POST /api/performance/executions/`，`POST /api/performance/scenarios/{id}/run/`，`GET .../executions/{id}/`、`POST .../{id}/cancel/`、`GET .../{id}/report/`
- `POST /api/performance/grafana/webhook/`（无需 JWT，接收 Grafana alert → AiDiagnosisRecord + LLM 诊断 + 通知）
- `GET/POST /api/performance/diagnoses/`，`PATCH .../{id}/`（status 处理）
- `GET /api/performance/dashboard/`（聚合指标，供前端大盘）
- 服务：`services/script_generator.py::generate_locust_script(scenario, config)`、`services/stats.py::parse_locust_csv(path)` 与 `parse_stats_csv_text(text)`（聚合 + P50/P95/P99 + 错误率 + 状态码分布）、`services/runner.py`（real=locust 子进程；simulated=确定性负载模型）、`services/execution.py::execute_scenario(...)`
- `utils/prometheus_sd.py::update_windows_exporter_target(ip=None, port=None) -> dict`：探测本机出口 IP，写 `settings.PROMETHEUS_TARGETS_FILE`，受 `PROMETHEUS_SD_AUTO_UPDATE` 控制；返回写入内容。
- `services/diagnosis.py::diagnose_execution(...)`：调 ai_core（LLM），失败降级规则诊断；写 AiDiagnosisRecord 并通过 notifications 推送。

### 2.7 ai_core
模型：
- `LLMConfiguration(project null（空=全局）, name, provider∈{openai,deepseek,qwen,huggingface,azure,mock}, model_name, api_key（加密/掩码输出）, base_url, model_type∈{text,vision}, temperature, max_tokens, is_default, is_active, extra JSON)`
- `RAGConfiguration(project null, name, vector_store∈{chroma,milvus}, embedding_mode∈{local,remote}, embedding_model, embedding_path, chunk_size=1000, chunk_overlap=200, collection_name, connection JSON, is_default)`
- `MCPConfiguration(project null, name, transport∈{stdio,sse,streamable_http}, server_config JSON, is_active, last_status)` + `MCPTool(config FK, name, description, input_schema JSON, is_enabled)`
- `LLMUsageLog(project null, config FK null, agent_name, task_type, task_id, prompt_tokens, completion_tokens, total_tokens, response_time_ms, success, error_message, request_preview, response_preview)`

接口：
- `GET/POST /api/ai/llm-configs/`，`POST .../{id}/test/`（真实/模拟连通性），`POST .../{id}/set-default/`（同 type 唯一）
- `GET/POST /api/ai/rag-configs/`，`POST .../{id}/set-default/`，`POST /api/ai/rag/index/`（body: document_id）与 `POST /api/ai/rag/search/`（query, project, top_k）
- `GET/POST /api/ai/mcp-configs/`，`POST .../{id}/refresh_tools/`，`GET /api/ai/mcp-tools/`
- `GET /api/ai/usage-logs/`，`GET /api/ai/usage-stats/`（按天/模型/agent 聚合）
- `POST /api/ai/agents/{agent_name}/run/`（agent_name ∈ api_testcase / api_scenario / postman_translator / webui_testcase / webui_playwright / midscene / midscene_script）
- 服务（**其它模块只依赖这些入口**）：
  - `services/llm_service.py`：`LLMService(config=None)`，`chat(messages, **kw) -> LLMResult(text, prompt_tokens, completion_tokens, raw)`；`is_mock` 属性；provider=mock 或 settings.AI_MOCK_MODE 时返回确定性 JSON（依据 prompt 关键词）。
  - `services/model_manager.py`：`ModelManager.get_text_model(project=None)`、`.get_vision_model()`、`.chat(...)`，无配置时返回 mock。
  - `services/rag_service.py`：`RAGService.index_document(doc) -> chunk_count`、`.search(query, project, top_k=5) -> list[{text, score, source}]`、`.stats()`；向量检索用**确定性本地哈希嵌入**实现（无 chromadb 也工作），chromadb 可用时优先。
  - `services/agents/base.py`：`BaseAgent`（状态 TypedDict、`run(payload, stream_task_id=None) -> dict`、节点回调推送 WS、token 计量、结构化输出解析、失败重试）。
  - 7 个 Agent：`api_testcase_agent.py`、`api_scenario_agent.py`、`postman_script_translator.py`、`webui_testcase_agent.py`、`webui_playwright_agent.py`、`midscene_agent.py`、`midscene_script_agent.py`。
  - `services/agents/registry.py`：`AGENTS: dict[str, type[BaseAgent]]`、`get_agent(name)`、`run_agent(name, payload)`。
- **LangGraph 可选**：若 `import langgraph` 成功则用 `StateGraph`，否则用内置 `apps/ai_core/services/graph.py` 的兼容实现（同样的 `StateGraph/START/END/compile().invoke()` 语义）。禁止硬依赖。

### 2.8 scheduled_tasks
模型：
- `ScheduledTask(project, name, suite_type∈{web,app,api}, suite_ids JSON, cron_expression, timezone, trigger_condition∈{always,fail}, environment FK projects.Environment null, app_run_config JSON, notice_targets M2M notifications.NotificationReceiver, is_enabled, last_run_at, next_run_at, created_by)`
- `TaskExecutionLog(task FK, scheduled_task_name, suite_type, status∈{pending,running,passed,failed,error}, started_at, finished_at, duration_ms, total/passed/failed/skipped, pass_rate, report_urls JSON, step_log JSON, error_message, celery_task_id)`

接口：
- `GET/POST /api/scheduled-tasks/tasks/`，`GET/PATCH/DELETE .../{id}/`，`POST .../{id}/run/`（立即执行）、`POST .../{id}/toggle/`、`GET .../{id}/logs/`
- `GET /api/scheduled-tasks/logs/`，`GET .../logs/{id}/`
- 可选 `GET /api/scheduled-tasks/cron/preview/?expr=...`（cronstrue 风格中文描述 + 未来 5 次时间）
- 机制：`signals.py` 在 `post_save` 同步创建/更新 `django_celery_beat.PeriodicTask` + `CrontabSchedule`；`is_enabled=False` 时禁用；删除时清理。
- 服务：`services/dispatcher.py::dispatch_task(task_id) -> log_id`：按 `suite_type` 调用对应模块 `services.execution.execute_suite(...)`，聚合结果，写 `TaskExecutionLog`，最后调用 `notifications.services.trigger_notification(...)`；**模块缺失时记录 error 而不是崩溃**。

### 2.9 notifications
模型：
- `NotificationChannel(channel_code unique∈{dingtalk,wechat_work,feishu,email,webhook}, name, description, is_active, config_schema JSON)`
- `NotificationReceiver(project, name, channel FK, webhook_url, target_address（逗号分隔邮箱）, is_active, description, metadata JSON)`
- `EmailConfig(host, port=465, username, password, from_email, use_ssl=True, use_tls=False, is_active)`
- `NotificationLog(project null, receiver FK null, channel_code, title, content, status∈{success,failed}, error_message, payload JSON, scheduled_task FK null, task_execution_log FK null)`

接口：
- `GET/POST /api/notifications/channels/`、`GET/PATCH .../{id}/`
- `GET/POST /api/notifications/receivers/`（`?project=`）
- `GET/PUT/PATCH /api/notifications/email-config/`（单例）
- `POST /api/notifications/test/`（body receiver_id 或 channel_code+webhook）
- `GET /api/notifications/logs/`
- 服务：`services.py::trigger_notification(scheduled_task, execution_log, result=None) -> dict`（固定签名，供 scheduled_tasks / performance 调用）；`build_markdown(...)`；`send_dingtalk/send_wecom/send_feishu/send_email`；单渠道失败只记 `NotificationLog` 与日志，不影响主流程；HTTP 用 `requests`，测试中打桩。

### 2.10 common（已完成，勿改）
`BusinessError`、`PageNumberPagination`、`ProjectRolePermission`、`WebSocketMessageService`、`save_uploaded_file`、`parse_json/parse_yaml/extract_first_object`、`iter_operations/example_from_schema/request_body_schema/responses_summary`、`metrics`。

---

## 3. 前端契约

### 3.1 技术栈
Vue 3.3 + Vite 5 + Vue Router 4 + Pinia 2（persistedstate）+ Element Plus 2.4 + axios + ECharts 5（vue-echarts）+ @monaco-editor/vue3（可选懒加载）+ vitest。

### 3.2 结构
```
frontend/src/
  main.js App.vue
  router/index.js          # 路由 + 守卫
  stores/{auth,project,app}.js
  api/{client,auth,projects,apiTesting,webTesting,appTesting,performance,aiCore,scheduledTasks,notifications}.js
  layouts/MainLayout.vue
  components/{PageHeader,DataTable,StatusTag,EmptyState,JsonEditor,ConfirmButton,StatCard}.vue
  views/{login,dashboard,projects,api-testing,web-testing,app-testing,performance,ai-core,scheduled-tasks,notifications,monitoring}/
  utils/{format,download,ws}.js
  styles/index.scss
```

### 3.3 约定
- axios baseURL `/api`，请求拦截注入 `Authorization: Bearer <access>`；401 自动用 refresh 换新 token（单飞：并发 401 只刷新一次），失败跳登录。
- Vite dev server 代理 `/api`、`/media`、`/ws` → `http://127.0.0.1:8000`。
- 错误展示统一读取 `error.response.data.message`。
- 列表页统一 `{count, results}` 分页；表格空态、loading、错误态。
- 所有页面必须能在后端未启动时给出可读错误而非白屏。
- 构建必须通过：`cd frontend && pnpm build`。

### 3.4 页面清单（每页需含真实交互，不可只有占位）
登录、仪表盘、项目列表/详情（成员、环境、知识库、第三方配置）、API 测试（规范导入、模块树、端点、用例、套件、执行详情与报告）、Web 测试（模块树、用例、POM、MidScene、套件、执行）、App 测试（应用、用例、套件、运行、设备）、性能测试（配置、场景、执行、报告、AI 诊断、监控大盘）、AI 中心（模型、RAG、MCP、用量、Agent 调试）、定时任务（任务、日志）、通知中心（渠道、接收人、邮件、日志）。

---

## 4. 集成验证脚本（最终交付）
`scripts/verify.sh` 依次执行：
1. `backend: manage.py check`
2. `backend: manage.py makemigrations --check --dry-run`（无未生成迁移）
3. `backend: manage.py test apps -v 1`
4. `backend: 启动 runserver` + `scripts/smoke_api.py`（登录→项目→导入 spec→用例→执行→通知→定时任务）
5. `frontend: pnpm build` + `pnpm test`
