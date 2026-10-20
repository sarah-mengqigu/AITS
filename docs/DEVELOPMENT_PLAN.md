# AITS v2 开发计划（Development Plan）

> 依据《AITS系统详细设计方案 v2.0》（`docs/AITS设计文档V2.md`）实施。
> 目标：交付可运行、可自验证的 AITS v2 平台（后端 Django + 前端 Vue3 + 监控栈配置 + 7 个 AI Agent）。

---

## 1. 环境事实（已探测）

| 项 | 状态 | 应对策略 |
|---|---|---|
| Python 3.10.9 | ✅ | 后端统一 venv：`backend/.venv` |
| Node 24 / pnpm | ✅ | 前端 Vite 5 |
| 网络（pypi/npm） | ✅ 可用 | 依赖安装 |
| Redis | ❌ 未安装/未运行 | 代码默认带上限降级：测试态 `InMemoryChannelLayer` + Celery `task_always_eager`；生产用 `REDIS_URL` 切换 |
| Docker daemon | ❌ 未运行 | 监控栈只交付 `docker-compose.yml` + `prometheus.yml` + `targets.json` + Grafana provisioning；用单元测试验证 File SD / `/metrics` / 诊断 webhook，不依赖容器 |
| Sonic 移动端集群 | ❌ 不可用 | App 测试以 Sonic HTTP 客户端 + 协议转换实现，用 mock 服务器测试（含 3001/3002/3003 业务码） |
| 外部 LLM Key | 未知 | `LLMConfiguration` 数据库驱动，运行时配置；Agent 支持 `mock` Provider（离线确定性输出）用于自验证 |

**结论**：所有模块必须「无外部服务也能启动与自测」——通过 env 开关（`AITS_ENV`）在 dev/test 使用内存实现，生产配置保留真实连接串。

---

## 2. 交付物与目录结构

```
AITS/
├── backend/
│   ├── manage.py                # DJANGO_SETTINGS_MODULE=aits_backend.settings
│   ├── requirements.txt         # 核心依赖
│   ├── requirements-ai.txt      # 可选重型依赖（langgraph/locust/chromadb…）
│   ├── aits_backend/            # settings / urls / asgi / wsgi / celery
│   ├── apps/
│   │   ├── common/              # 异常处理、分页、WS 基类、存储、解析器、任务工具
│   │   ├── users/               # 自定义 User + JWT
│   │   ├── projects/            # 项目/成员/环境/文件/第三方配置
│   │   ├── api_testing/         # OpenAPI/Postman/HttpRunner/执行
│   │   ├── web_testing/         # Playwright/MidScene/POM/Allure
│   │   ├── app_testing/         # Sonic 代理与用例转换
│   │   ├── performance/         # Locust/CSV/Prometheus SD/AI 诊断
│   │   ├── ai_core/             # LLM/RAG/MCP/7 Agents/Token 日志
│   │   ├── scheduled_tasks/     # Cron + Beat 同步 + 统一调度
│   │   └── notifications/       # 渠道/接收人/SMTP/分发
│   ├── utils/                   # prometheus_sd 等跨模块工具
│   ├── aits_monitor/            # docker-compose + prometheus + grafana provisioning
│   └── tests/                   # 集成冒烟脚本
├── frontend/
│   ├── src/{api,components,views,router,stores,utils,styles}
│   └── vitest 单测
├── docs/{AITS设计文档V2.md, DEVELOPMENT_PLAN.md, ARCHITECTURE.md, API.md, VERIFICATION.md}
└── scripts/{dev.sh, verify.sh}
```

---

## 3. 里程碑与并行策略

### M0 基座（串行，阻塞后续）
- backend 骨架：settings（env 驱动、SQLite、JWT、Celery、Channels、DRF、CORS、Prometheus）、asgi/wsgi/celery、9 个 app 骨架与 URL 聚合
- `users` + `common` + `projects` 完成并自测
- 前端骨架：Vite + Vue3 + Element Plus + Pinia + Router + Axios + 布局/登录
- 产出契约文档 `docs/ARCHITECTURE.md`（接口/模型/降级策略）

### M1 后端业务模块（并行 7 路）
每个 subagent 独占一个 `backend/apps/<app>/` 目录，只改本目录 + 本目录 migrations，禁止改 `settings.py`/根 `urls.py`（已在 M0 固定 include）。

| 并行流 | 模块 | 核心验收 |
|---|---|---|
| B1 | api_testing | OpenAPI/Postman 解析、用例/套件/执行、HttpRunner YAML 生成与内置执行器、WS 进度 |
| B2 | web_testing | 模块树/用例/套件/执行、POM、Playwright 脚本生成、Allure results 产出、MidScene 脚本 |
| B3 | app_testing | Sonic 鉴权/设备/套件代理、步骤互转、错误码友好提示 |
| B4 | performance | 配置/场景/执行、locustfile 生成、CSV 解析、Prometheus File SD、AI 诊断记录 |
| B5 | ai_core | LLM/RAG/MCP 模型、ModelManager、Mock Provider、7 个 Agent（LangGraph 可选）、Token 日志 |
| B6 | scheduled_tasks | Cron CRUD、PeriodicTask 同步、调度执行、执行日志、通知联动 |
| B7 | notifications | 渠道/接收人/SMTP、Markdown 组装、webhook/邮件发送、失败容错 |

### M2 前端功能页（并行 5 路，依赖 M1 接口契约）
| 流 | 页面 |
|---|---|
| F1 | 项目管理 / 环境 / 成员 / 知识库 |
| F2 | API 测试（导入、模块树、用例、套件、执行、报告） |
| F3 | Web 测试 + App 测试（POM、MidScene、设备面板） |
| F4 | 性能测试 + 监控大盘（ECharts + Grid 布局 + AI 诊断） |
| F5 | AI 中心（模型/RAG/MCP/Agent 对话）+ 定时任务 + 通知中心 |

### M3 集成与验证（串行）
- `makemigrations/migrate`、全量 `manage.py test`
- 启动后端 + 前端，跑端到端冒烟脚本（登录→建项目→导入 spec→生成用例→执行→报告→通知→定时任务）
- `pnpm build` + vitest
- 监控栈静态校验（prometheus.yml 语法、targets.json、compose 结构）
- 输出 `docs/VERIFICATION.md` 证据表

---

## 4. 自验证标准（每个模块必须通过）

1. `python manage.py test apps.<module> -v 1` 全绿（模型/序列化器/API/服务单测）
2. 每个模块 ≥ 8 个测试用例，覆盖：正常路径、权限/校验失败、降级路径
3. API 层用 DRF `APIClient` 走真实 URL 路由与 JWT
4. 服务层对无外部依赖的纯逻辑（解析、转换、统计、组装）做确定性断言
5. 外部依赖（Sonic/Grafana/LLM/Redis）一律 mock 或 env 降级
6. 前端：`pnpm build` 成功 + 关键 store/util vitest 通过
7. 提交前根目录 `scripts/verify.sh` 一键全绿

---

## 5. 关键设计决策

- **LLM 调用层自研薄客户端**（OpenAI 兼容 `/chat/completions`），`langchain/langgraph` 作为可选增强；未安装时用内置 `StateGraph` 兼容实现，保证 Agent 可测。
- **7 个 Agent 共用统一基类**：状态 TypedDict、节点流式回调 → WebSocket、结构化输出校验、RAG 注入点、token 计量。
- **执行引擎抽象**：`BaseRunner`（API/Web/App/Perf）→ 真实子进程实现 + `SimulatedRunner`（env 开启），使执行链路在无浏览器/无压测机时可验证。
- **通知与调度解耦**：`notifications.services.trigger_notification` 单一入口，失败只记日志。
- **多租户边界**：所有业务对象挂 `project`，权限经 `ProjectMember.role` 判定（owner/admin 写配置，editor 写用例，viewer 只读）。
