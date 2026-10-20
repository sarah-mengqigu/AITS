# AITS · AI-empowered Intelligent Testing System (v2)

面向软件测试全流程的 AI 赋能一体化测试平台：**API / Web UI / 移动端 App / 性能压测** 四大测试域，
LangGraph 多智能体编排、Django Channels 实时推送、Prometheus + Grafana 可观测、多渠道通知闭环。

设计文档：`docs/AITS设计文档V2.md` · 开发计划：`docs/DEVELOPMENT_PLAN.md` · 架构契约：`docs/ARCHITECTURE.md`

---

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3.3 · Vite 5 · Element Plus 2.4 · Pinia 2 · Vue Router 4 · ECharts 5 |
| 后端 | Django 4.2 · DRF 3.14 · SimpleJWT · django-filter · drf-spectacular |
| 异步 / 实时 | Celery 5.3 · django-celery-beat · Channels 4 · ASGI (Uvicorn/Daphne) |
| AI | LangGraph 兼容编排（可选 langgraph）· 自研 LLM 客户端 · RAG 双向量库 · MCP |
| 测试执行 | HttpRunner 兼容 YAML · Playwright · MidScene · Sonic · Locust |
| 数据 / 可观测 | SQLite/PostgreSQL · Redis · Prometheus · Grafana |

## 目录

```
backend/     Django 项目（9 个业务 app + common）
  aits_backend/     settings / urls / asgi / celery
  apps/             users projects api_testing web_testing app_testing
                    performance ai_core scheduled_tasks notifications common
  aits_monitor/     Prometheus + Grafana docker-compose 与配置
  utils/            prometheus File SD 等跨模块工具
frontend/    Vue 3 SPA
docs/        设计文档 / 开发计划 / 架构契约 / 验证报告
scripts/     dev.sh（一键启动）· verify.sh（一键验证）· smoke_api.py（端到端冒烟）
```

## 快速开始

```bash
# 1) 后端依赖（已预置 backend/.venv）
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 2) 迁移 + 创建管理员
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser

# 3) 启动
.venv/bin/python manage.py runserver 0.0.0.0:8000

# 4) 前端（另开终端）
cd frontend && pnpm install && pnpm dev
# 打开 http://127.0.0.1:5173
```

一键启动：`./scripts/dev.sh`　一键验证：`./scripts/verify.sh`

### 可选：Redis / 监控栈 / Sonic

```bash
# Redis（生产模式缓存 + Broker + Channel Layer）
redis-server --daemonize yes
export USE_REDIS=1

# Prometheus :9090 / Grafana :3000（admin/admin）
cd backend/aits_monitor && docker-compose up -d

# Sonic 移动端集群（可选，App 测试需要）
export SONIC_BASE_URL=http://127.0.0.1:3000 SONIC_USERNAME=... SONIC_PASSWORD=...
```

## 环境变量

见 `backend/aits_backend/settings.py` 顶部 env helper；常用项：

| 变量 | 默认 | 说明 |
|---|---|---|
| `AITS_ENV` | `dev` | `dev` / `test` / `prod`（test 自动 eager Celery + 内存通道） |
| `DJANGO_SECRET_KEY` | dev 占位 | 生产必须替换 |
| `DEBUG` | `True` | 生产置 `False` |
| `REDIS_URL` / `USE_REDIS` | `redis://127.0.0.1:6379/0` / 自动 | 缓存 / Broker / Channel Layer |
| `FRONTEND_BASE_URL` | `http://127.0.0.1:5173` | CORS / 通知报告链接 |
| `AITS_EXECUTION_MODE` | `simulated` | `real` 时启动 Playwright/Locust/HttpRunner 子进程 |
| `SONIC_BASE_URL` 等 | 空 | 移动端云真机集成 |
| `PROMETHEUS_SD_AUTO_UPDATE` | `True` | 自动维护 File SD 目标 |
| `GRAFANA_AI_NOTIFY_RECEIVER_ID` | 空 | AI 诊断默认通知接收人 |

## API 文档

后端启动后：`/api/docs/`（Swagger UI）、`/api/schema/`（OpenAPI）、`/api/redoc/`。
健康检查：`/health/`；指标：`/metrics/`。

## 测试

```bash
cd backend && AITS_ENV=test .venv/bin/python manage.py test apps -v 1
cd frontend && pnpm test -- --run
```

每个模块的自验证证据见 `docs/VERIFICATION.md`。
