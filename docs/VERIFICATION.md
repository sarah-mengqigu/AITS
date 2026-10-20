# AITS v2 验证报告（VERIFICATION）

> 生成时间：2026-10-20 · 环境：macOS / Python 3.10.9 / Node 24 / 无 Redis、无 Docker daemon、无 Sonic、无外部 LLM Key
> 复现：`./scripts/verify.sh`（后端全量测试 + 前端单测/构建 + 在线冒烟）

---

## 1. 结论摘要

| 维度 | 结果 |
|---|---|
| 后端自动化测试 | **418 passed / 0 failed**（11 个测试集合，含跨模块 E2E 与 WebSocket） |
| 后端系统检查 | `manage.py check` 0 issues；`makemigrations --check` 无缺失迁移 |
| API 文档 | 145 paths / **269 operations**，0 schema 错误（`docs/openapi.yaml` / `docs/API.md`） |
| 前端单元测试 | **129 passed**（8 个 spec） |
| 前端生产构建 | `pnpm build` ✅（dist 约 2.3 MB，gzip 后 < 700 KB 主包合计） |
| 在线冒烟 | 17/17 项通过（health / login / 12 个模块列表 / metrics / schema） |
| 端到端业务链路 | 注册→登录→项目→环境→规范导入→用例生成→套件执行→Web/App/性能执行→AI Agent→定时任务→通知，全链路通过 |
| 运行时约束 | 无 Redis / 无 Docker / 无 Sonic / 无 LLM Key 下仍可完整启动与自测（环境降级策略见 §6） |

---

## 2. 后端测试矩阵

命令：`cd backend && AITS_ENV=test .venv/bin/python manage.py test <target> -v 1`

| 测试集合 | 用例数 | 覆盖重点 |
|---|---:|---|
| `apps.users` | 10 | 注册/登录/邮箱登录/刷新旋转/登出黑名单/改密/鉴权失败信封 |
| `apps.projects` | 20 | 四类项目 CRUD、成员角色、环境默认切换、文件哈希去重、知识库、第三方配置、权限拒绝 |
| `apps.common` | 13 | 异常信封、分页、YAML/JSON 解析与修复、SHA256 存储、角色层级、`/health/`、`/metrics/` |
| `apps.api_testing` | 36 | OpenAPI3/Swagger2/Postman 解析、模块树、4 类用例生成、HttpRunner YAML、套件执行统计、断言失败、错误信封 |
| `apps.web_testing` | 40 | 模块树、用例、POM/备选定位、Playwright 脚本可编译、MidScene YAML、Allure result JSON、套件执行、real 模式缺依赖落 error |
| `apps.app_testing` | 46 | Sonic 登录/缓存/401 重登、3001/3002/3003 文案、步骤双向转换、simulated 执行、未配置降级 |
| `apps.performance` | 75 | locustfile 生成可编译、CSV/P95/错误率、阈值判定、Dashboard 零值结构、Grafana webhook、AI 规则诊断降级、File SD |
| `apps.ai_core` | 64 | Mock LLM 确定性、usage 计量、api_key 掩码、RAG 切块/检索/stats、StateGraph 语义、7 个 Agent 契约、权限 |
| `apps.scheduled_tasks` | 59 | PeriodicTask 同步/去重/禁用/删除、cron 校验与预览、三类 dispatch、部分失败 pass_rate、通知联动与异常隔离 |
| `apps.notifications` | 40 | Markdown/HTML 组装、always/fail 判定、多渠道与单渠道失败隔离、errcode 校验、SMTP 动态连接、日志 |
| `tests`（集成） | 15 | 9 个跨模块 E2E 流程 + 4 个 WebSocket（JWT/5 条路由/匿名拒绝）+ 2 个 `seed_demo` 守护 |
| **合计** | **418** | |

关键集成测试（`backend/tests/test_integration.py`）逐步验证：

1. 登录 + 项目 + 环境（含默认环境）
2. OpenAPI 导入 → 3 个端点 → 生成 4 类用例 → 生成可解析的 HttpRunner YAML
3. API 套件执行 → 202 → 终态 + 统计 + 明细 + 报告
4. Web 用例 → Playwright 脚本 → 套件执行 → 终态
5. App 用例（自动生成 `sonic_steps`）→ 套件执行（Sonic 未配置 → simulated）→ 设备接口空降级
6. 性能场景（custom_script）→ 执行 → `total_requests > 0` → Dashboard 聚合
7. AI Mock 模型 → 7 个 Agent 列出 → `api_testcase` 运行 → usage 统计
8. 通知接收人 → 定时任务（cron + PeriodicTask）→ 立即运行 → 日志统计 + 通知日志（webhook 打桩）
9. `/health/` + `/metrics/` + `/api/schema/`

WebSocket 测试（`backend/tests/test_websocket.py`）：
`ws/task-status/<id>/` 收到业务推送；`ws/scenario_generation-streaming/` 收到 Agent 帧；
四条流通道均可连接；无效 token 收到 `unauthorized` 并断开。

---

## 3. 在线冒烟（真实 HTTP）

```
$ backend/.venv/bin/python scripts/smoke_live.py
✔ health  aits-backend v2.0.0
✔ login   admin
✔ projects / api specs / api executions / web executions / app runs
✔ perf executions / perf dashboard / ai models / ai agents
✔ scheduled tasks / task logs / notification receivers / notification logs
✔ prometheus metrics exposed
✔ openapi schema served
all live checks passed
```

演示数据：`manage.py seed_demo`（幂等）创建 4 个项目（api/web/app/perf）、1 份 OpenAPI 规范（4 端点 / 16 用例）、
Web/App/性能各 1 条绿色执行、AI Mock 模型 + RAG + MCP 配置、通知接收人、工作日 9 点定时任务（含一次执行日志）。

---

## 4. 前端验证

| 项 | 命令 | 结果 |
|---|---|---|
| 生产构建 | `cd frontend && pnpm build` | ✅ exit 0 |
| 单元测试 | `pnpm test -- --run` | ✅ 129 passed / 8 files（20 API、16 Web/App、35 性能/监控、32 AI/定时/通知、6 项目上下文、7 格式化、8 认证、5 下载） |
| 路由/页面 | 14 个顶级路由 + 40+ 子路由，均有真实页面 | 无占位页 |
| 控制台 | Playwright 实测登录/仪表盘/API 执行/项目列表 | 0 error / 0 warning（已修复 el-link 弃用告警） |

页面清单（真实交互，均对接真实接口）：

- 登录 / 仪表盘（统计卡 + ECharts 趋势 + 状态分布）
- 项目列表 / 详情（概览、成员、环境、知识库、第三方配置）
- API 测试 6 页（总览、规范导入、模块树与端点、用例与脚本、套件、执行详情与报告）
- Web 测试 7 页（总览、模块、用例、套件、执行、POM、MidScene）
- App 测试 8 页（总览、应用、模块、用例、套件、运行、设备、元素页面）
- 性能测试 5 页（总览、负载配置、场景、执行、AI 诊断）+ 监控大盘
- AI 中心 6 页（总览、模型、RAG、MCP、用量、Agent 调试）
- 定时任务 2 页（任务、日志）+ 通知中心 5 页（渠道、接收人、邮件、日志、测试发送）
- 个人中心（资料 / 改密）、404

截图（`docs/screenshots/`）：

| 截图 | 内容 |
|---|---|
| `01-dashboard.png` | 仪表盘：4 项目 / 18 用例 / 7 执行 / 100% 通过率 + 趋势图 |
| `02-api-endpoints.png` | 模块树 + 4 个端点（方法标签、分页、生成用例） |
| `03-api-executions.png` | 执行记录：通过率进度、通过/失败/总数、报告入口 |
| `04-web-cases.png` | Web 用例（步骤编辑器、脚本生成） |
| `05-app-runs.png` | App 运行记录 |
| `06-monitoring.png` | 监控大盘（Prometheus/Grafana 联动 + 性能指标） |
| `07-ai-models.png` | LLM 配置（Mock 模型、测试连通性、设为默认） |
| `08-scheduled-tasks.png` | 定时任务（Cron + 上次执行） |
| `09-notifications.png` | 通知接收人 |
| `10-projects.png` | 四类项目列表 |
| `11-performance.png` | 性能测试总览（TPS / P95 / 错误率 / 最近执行） |

---

## 5. 监控与可观测性验证

- `GET /metrics/` 输出 `aits_test_executions_total` / `aits_test_cases_total` / `aits_ai_requests_total` / `aits_ai_tokens_total` / `aits_execution_duration_seconds` 等指标（单测 + 在线冒烟双重验证）。
- `backend/aits_monitor/`：`docker-compose.yml`（Prometheus 9090 / Grafana 3000）、`prometheus.yml`（3 个 job：aits-backend、locust-performance、windows-exporter file_sd）、`alerts.yml`（5 条告警规则）、`targets.json`、Grafana 数据源与 `aits-overview` 面板（9 个 panel）。
- **未在本机启动容器**（Docker daemon 不可用）：配置已通过 YAML/JSON 解析校验；File SD 写入函数有单测（`apps.performance` 75 项内含）。
- `utils/prometheus_sd.py` 在性能执行前自动发现本机出口 IPv4 并写入 `targets.json`（演示中写入 `172.20.10.8:9182`）。

---

## 6. 降级策略验证（无外部依赖仍可运行）

| 外部依赖 | 缺失时的行为 | 验证方式 |
|---|---|---|
| Redis | dev/test 默认内存缓存 + `InMemoryChannelLayer` + Celery eager；生产 `USE_REDIS=1` 启用 | 全量测试在无 Redis 下运行；设置项 `USE_REDIS` 由 env 控制 |
| Docker/Prometheus/Grafana | 监控页面显示配置引导；`/metrics/` 仍可抓取 | 页面截图 + 冒烟 |
| Sonic | 读接口返回 `[]`/`{configured:false}`，写/运行动作返回 `sonic_not_configured`；App 执行走 simulated | `apps.app_testing` 46 项测试 + E2E |
| Playwright | real 模式探测失败 → 执行记录 `error` 并带清晰信息，不残留 running | `apps.web_testing` real 模式测试 |
| Locust | real 模式不可用 → 执行记录 `error`；simulated 产出确定性 CSV/报告 | `apps.performance` 测试 |
| LLM Key | `provider=mock` 或 `AI_MOCK_MODE` → 确定性输出；Agent 全部可运行 | `apps.ai_core` 64 项 + E2E |
| Celery Worker | eager 模式同步执行，`202` 返回后立即完成 | 全部执行类测试 |

---

## 7. 已知限制 / 后续建议

1. **真实引擎联调**：本机未安装 Playwright 浏览器、Locust、Sonic 集群，`AITS_EXECUTION_MODE=real` 的端到端路径未实测（降级与错误落库已测）。建议在具备依赖的环境执行一次真实冒烟。
2. **真实 LLM**：仅实现 OpenAI 兼容 `/chat/completions`；Azure 的 `api-version`/deployment 路径未适配。生产需要真实 Key 联调。
3. **RAG**：默认使用确定性哈希嵌入 + 词法门槛（保证离线可用与可测），语义召回弱于真实 Embedding；安装 `sentence-transformers`/`chromadb` 后可替换。
4. **MCP**：`refresh_tools` 离线解析 server_config，未实现真实 stdio/SSE 握手。
5. **监控栈**：Docker 配置未实际启动验证（仅静态校验 + 单测）。
6. **WebSocket 流式**：路由与鉴权已测；Agent 真实流式输出依赖真实 LLM 才会产生 chunk。
7. **报告下载**：API/Web 报告以 JSON/HTML 路径 + `?download=1` 提供，未接入 Allure CLI 生成静态站点。

---

## 8. 复现步骤

```bash
# 1) 后端
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo          # 演示数据（可选）
.venv/bin/python manage.py runserver 0.0.0.0:8000

# 2) 前端
cd frontend && pnpm install && pnpm dev        # http://127.0.0.1:5173

# 3) 一键验证
./scripts/verify.sh
```
