AITS（AI-empowered Intelligent Testing System）详细设计方案

文档版本：v2.0
更新日期：2026-05-15

目录

1.
项目概述与愿景

2.
技术栈选型

3.
平台架构设计

4.
核心功能模块

5.
AI 智能体清单

6.
监控与可观测性

7.
通知体系

8.
部署与运行

9.
v1 → v2 升级对照表

1. 项目概述与愿景

1.1 项目简介

AITS 是一个面向软件测试全流程的 AI 赋能一体化测试平台。它将先进的 AI 智能体（Agent）与传统自动化测试方法深度融合，覆盖 API 接口、Web UI、移动端 App、性能压测 四大测试域，致力于解决脚本维护成本高、用例设计覆盖率不足、缺陷定位困难、性能瓶颈分析复杂等行业痛点。

相比早期版本（v1），v2 在以下方面实现了实质性升级：

•
测试域扩展：在 API + Web 之外，新增 移动端 App 测试（基于 Sonic Spring Cloud 微服务集群）与 性能测试（Locust + Prometheus + Grafana）

•
AI 编排升级：从单一 LangChain Chain 模式升级为 LangGraph 1.x 多智能体编排，落地 7 个独立 Agent

•
协议扩展：原生支持 MCP（Model Context Protocol），可挂接外部工具能力

•
可观测性：新增 Prometheus + Grafana 指标监控、AI 性能诊断、定时告警闭环

•
通知中心：构建多渠道（钉钉 / 企微 / 飞书 / 邮件）+ 项目级接收人的通知体系

1.2 核心理念

理念

说明

AI-Driven

从需求理解、用例生成、脚本编写、执行自愈到结果诊断，全流程引入 LangGraph 多智能体

Low-Code / No-Code

自然语言生成、可视化场景编排、Postman 一键导入翻译，降低使用门槛

All-in-One

API + Web + 移动 + 性能 一体化，打破测试资产孤岛

Scalable & Integrable

微服务 + 可插拔 Agent + MCP 工具协议 + 多 LLM 供应商，便于扩展与集成

1.3 目标用户与核心价值

•
测试工程师（QA Engineers）：日常自动化测试设计、执行与分析的核心入口

•
测试经理（QA Managers）：通过仪表盘与报告体系监控质量、效率与覆盖率

•
开发工程师（Developers）：查看 AI 诊断报告，快速定位与修复缺陷

•
运维工程师（SRE）：基于 Prometheus + Grafana 进行性能基线管理与告警闭环

1.4 v2 升级摘要

维度

v1 早期方案

v2 当前实现

业务模块（Django App）

6 个

9 个（新增 app_testing / performance / notifications）

AI 框架

LangChain

LangGraph 1.x + LangChain 1.x

AI 智能体数量

2 个（构想）

7 个（已落地）

测试执行引擎

HttpRunner / Playwright

HttpRunner / Playwright / MidScene / Sonic / Locust

监控体系

无

Prometheus + Grafana + Windows Exporter + AI 诊断

通知体系

无

多渠道 + 项目级接收人 + 邮件 SMTP

MCP 协议

未提及

已实现（MCPConfiguration + langchain-mcp-adapters）

实时通信

笼统 WebSocket

Django Channels (ASGI) + JWT 鉴权中间件 + 多 Consumer

数据库

PostgreSQL

开发 SQLite，生产推荐 PostgreSQL（默认配置已改）

2. 技术栈选型

2.1 总览

层级

关键技术

前端框架

Vue 3.3.8 + Vite 5.x + Element Plus 2.4 + Pinia 2.1 + Vue Router 4.2

后端框架

Django 4.2.25 + Django REST Framework 3.14 + django-filter 23.5

异步任务

Celery 5.3.4 + django-celery-beat 2.5 + Flower 2.0.1 + Redis 5.0.1

实时通信

Django Channels 4.0.0 + channels-redis 4.1 + WebSocket（ASGI / Uvicorn）

AI 引擎

LangGraph 1.0.5 + LangChain 1.2 + langchain-openai/deepseek/huggingface/milvus/chroma/mcp-adapters

向量数据库

ChromaDB 1.4 / Milvus（pymilvus 2.6.5）+ sentence-transformers 5.1 + transformers 4.56

测试执行

HttpRunner（自研集成）+ Playwright + MidScene + Sonic Spring Cloud + Locust 2.43.3

数据库

SQLite（开发默认）/ PostgreSQL（生产，psycopg2-binary 2.9）

监控可观测

Prometheus + Grafana + prometheus_client 0.23 + Windows Exporter

报告

Allure（allure-pytest 2.14）+ ECharts 5.4 + Vue3-Grid-Layout-Next

2.2 前端

•
Vue 3 + Vite：极致开发体验与高性能运行时（frontend/package.json）

•
Element Plus 2.4：企业级组件库，搭配 @element-plus/icons-vue

•
Pinia 2.1 + pinia-plugin-persistedstate：Vue 3 官方推荐状态管理，登录态持久化

•
ECharts 5.4 + vue-echarts 6.6：测试报告与性能数据可视化

•
Monaco Editor 0.45：在线脚本编辑（HttpRunner / Playwright / MidScene / Locust 脚本）

•
vue3-grid-layout-next 1.0：性能监控自定义仪表盘（拖拽布局）

•
vuedraggable 4.1 + sortablejs 1.15：场景编排器拖拽

•
html2canvas + jspdf：报告快照与 PDF 导出

•
WebSocket（原生 + JWT 透传）：实时执行进度、Agent 流式输出

2.3 后端

•
Django 4.2.25 + DRF 3.14：成熟 ORM、强大序列化与认证授权、Admin 开箱即用

•
JWT（djangorestframework-simplejwt 5.5）：Access Token 有效期 600 分钟，Refresh Token 1 天，旋转 + 黑名单（backend/aits_backend/settings.py SIMPLE_JWT）

•
Celery 5.3.4 + django-celery-beat 2.5 + Redis：分布式任务队列 + 数据库 Beat 调度器（CELERY_BEAT_SCHEDULER='django_celery_beat.schedulers:DatabaseScheduler'）

•
Flower 2.0.1：Celery 任务监控

•
Channels 4.0 + channels-redis 4.1：ASGI 协议下的 WebSocket，使用 Redis 作为 Channel Layer

•
django-redis 5.4：将 Redis 作为 Cache 后端（max_connections=50，连接池超时 5s）

•
django-cors-headers 4.3 + django-filter 23.5：跨域与查询过滤

2.4 AI 智能体核心

•
LangGraph 1.0.5：以 StateGraph 编排"判断—循环—状态修正"的有状态工作流，是 AI 编排的核心

•
LangChain 1.2：作为"胶水层"统一封装 LLM、向量库、Prompt、Tool

◦
Text LLM：OpenAI、DeepSeek、Qwen、本地 HuggingFace

◦
Vision LLM：Qwen-VL、Doubao Vision、Gemini、UI-TARS（用于截图理解 / POM 生成）

◦
mcp==1.12.4 + mcp-use==1.5.1 + langchain-mcp-adapters==0.2.1

◦
数据模型：MCPConfiguration + MCPTool，支持 filesystem / github / database / web_search / calendar / email 等内置 Provider

◦
向量库类型：ChromaDB / Milvus（双轨可选）

◦
Embedding：默认 BAAI/bge-large-zh-v1.5，支持 local（离线本地路径）/ remote（联网下载）双模式

◦
分块：chunk_size=1000，chunk_overlap=200（可调）

2.5 测试执行引擎集群

引擎

适用域

关键依赖

入口位置

HttpRunner

API 接口

httprunner 自研定制（backend/apps/httprunner/）

apps/api_testing/httprunner_runner.py

Playwright

Web UI

playwright + pytest-playwright

apps/web_testing/tasks.py

MidScene

Web UI 视觉

LLM Vision + langchain-openai

apps/ai_core/webui_midscene_agent.py

Sonic Spring Cloud

移动端 App

Java 微服务集群（sonic-server/）

apps/app_testing/services.py（HTTP 代理）

Locust

性能压测

locust==2.43.3 + gevent + geventhttpclient

apps/performance/tasks.py

2.6 数据与基础设施

•
关系数据库：开发默认 SQLite（db.sqlite3），生产推荐 PostgreSQL（settings.py 中 PostgreSQL 配置已注释保留）

•
缓存 + Broker：Redis（同时充当 Celery Broker、Channel Layer、Django Cache）

•
向量数据库：ChromaDB（轻量本地）/ Milvus（生产分布式）

•
监控：Prometheus + Grafana（backend/aits_monitor/docker-compose.yml）

•
容器化：aits_monitor 与 sonic-server 均提供 docker-compose

•
Web 服务器：Uvicorn（ASGI）+ Nginx（生产反代，可选）

3. 平台架构设计

3.1 架构分层（总览图）

下图为 v2 最新平台架构总览：

平台采用 前后端分离 + 微服务协同 + 智能体编排 的混合架构，核心由 5 个层级 组成：

层级

组成

前端展示层

Vue 3 SPA（项目管理 / API / Web / App / 性能 / 定时任务 / AI 配置 / 通知）

API 服务层

Django REST + Channels(ASGI) + JWT 鉴权

业务逻辑层

9 个 Django App（apps/projects、api_testing、web_testing、app_testing、performance、ai_core、scheduled_tasks、notifications、users）

执行与异步层

Celery Worker + Celery Beat + Flower + 5 路测试执行引擎

数据与基础设施层

SQLite/PostgreSQL + Redis + ChromaDB/Milvus + Prometheus + Grafana + Sonic Spring Cloud

3.2 核心组件交互

3.3 端到端数据流

代码块
Plain Text

WebSocket 通道在 backend/aits_backend/asgi.py 与 backend/apps/api_testing/routing.py 中注册：

•
ws/scenario_generation-streaming/ —— API 场景 Agent 流式输出

•
ws/midscene_script_generation-streaming/ —— MidScene 脚本生成

•
ws/webui_test_generation-streaming/ —— WebUI 用例生成

•
ws/webui_auto_test-streaming/ —— WebUI 自动化执行

•
ws/task-status/<task_id>/ —— 通用任务状态推送

均经过自定义 WebSocketJWTAuthMiddlewareStack（见 backend/apps/common/websocket/websocket_core.py）完成 JWT 鉴权。

3.4 部署拓扑

4. 核心功能模块

业务逻辑层共 9 个 Django App + 1 个公共模块，对应 backend/aits_backend/settings.py INSTALLED_APPS 中的 users / projects / api_testing / ai_core / web_testing / app_testing / scheduled_tasks / notifications / performance。

4.1 项目管理 apps/projects

功能职责

•
多项目、多环境管理（API / Web / App / Perf 四类项目）

•
项目成员与权限控制（Owner / Admin / Editor / Viewer）

•
知识库文档管理（用于 RAG 索引）

•
统一环境配置（Environment 模型，支持三类测试环境）

•
文件上传管理（基于哈希去重）

•
Sonic 项目映射（sonic_project_id，App 测试与 Sonic 云真机项目绑定）

•
性能项目可关联多个 API 项目（linked_api_projects 自关联 M2M）

•
项目第三方系统集成配置（ProjectThirdPartyConfig）

核心模型（见 backend/apps/projects/models.py）

•
Project：基础信息，含 project_type ∈ {api, web, app, perf}

•
ProjectMember：成员与权限

•
Environment：统一环境配置

•
UploadedFile：文件上传与去重

•
ProjectThirdPartyConfig：每项目唯一的第三方集成配置

亮点特性

•
项目类型四分（API / Web / App / Perf），各自独立工作台

•
性能项目可挂载多个 API 项目作为压测来源

•
Sonic 项目 ID 桥接，无缝对接移动端云真机

4.2 API 测试 apps/api_testing

功能职责

•
OpenAPI / Swagger / Postman Collection 文档解析

•
API 端点（Endpoint）与模块（Module）管理

•
端点级 + 场景级 双形态测试用例

•
测试套件管理与异步执行

•
HttpRunner 脚本生成与执行（YAML / Python）

•
实时执行进度推送（WebSocket）

•
Postman 用例一键导入并通过 LLM 翻译为 HttpRunner 原生结构

核心模型（见 backend/apps/api_testing/models.py）

•
APISpecification / APIModule / APIEndpoint

•
APITestCase：支持端点用例与场景用例两种类型

•
APITestSuite + APITestSuiteCaseExecution

•
APITestExecution + APITestCaseExecutionDetail + APITestSuiteExecutionDetail

核心服务

•
APIParserService（OpenAPI 解析）

•
PostmanParserService（backend/apps/api_testing/postman_parser_service.py）：纯规则解析 Postman Collection v2.1

•
PostmanScriptTranslator（backend/apps/ai_core/postman_script_translator.py）：将 pm.test() / pre-request JS 翻译为 HttpRunner validate / extract

•
ApiEndpointGenTestcaseService：AI 端点用例生成

•
HttpRunnerService：HttpRunner 脚本生成与执行

亮点特性

•
端点 + 场景双轨用例（场景由 LangGraph Agent 生成）

•
多类型测试用例（正向 / 负向 / 边界 / 安全）

•
Postman 一键导入翻译，平滑迁移既有资产

•
异步执行 + WebSocket 实时进度

4.3 Web UI 测试 apps/web_testing

功能职责

•
WebUI 测试模块树（WebUITestModule，自引用父子结构）

•
测试用例 / 测试套件 / 执行记录管理

•
POM（Page Object Model）页面对象与元素管理

•
Playwright 脚本生成与执行

•
MidScene 脚本（视觉 AI）支持

•
Allure 报告集成

核心模型（见 backend/apps/web_testing/models.py）

•
WebUITestModule / WebUITestCase / WebUITestSuite / WebUITestExecution

•
WebPage / WebElement（POM）

•
MidSceneScript

核心服务

•
PlaywrightRunner：Playwright 子进程执行器

•
WebUITestCaseGenerator（backend/apps/ai_core/webui_testcase_agent.py）：多 Agent 角色化用例生成

•
WebUIPlaywrightAgent（backend/apps/ai_core/webui_playwright_agent.py）：自然语言 → Playwright 脚本

•
MidSceneAgent（backend/apps/ai_core/webui_midscene_agent.py）：视觉模型驱动的 UI 测试

•
MidSceneScriptAgent（backend/apps/ai_core/midscene_script_agent.py）

亮点特性

•
多 Agent 协作（LangGraph 编排）

•
Playwright + MidScene 双执行模式

•
POM 智能维护

•
Allure 报告嵌入式预览

4.4 移动端 App 测试 apps/app_testing 【新增】

功能职责

•
移动端用例编排（AppTestCase，步骤为 JSON，含 sonic_steps 快照）

•
被测应用（AppTestApplication）管理（含 Android 包名 / iOS Bundle ID）

•
模块树（AppTestModule）组织

•
测试运行（AppTestRun）与套件

◦
设备列表 / 设备详情代理

◦
设备远程控制（远控面板）

◦
测试套件运行（runSuite）

◦
元素页面（ElementPages）映射

•
Sonic 业务码错误友好提示（如 3001 套件不存在 / 3002 套件无用例 / 3003 无在线设备）

核心模型（见 backend/apps/app_testing/models.py）

•
AppTestModule / AppTestApplication / AppTestCase / AppTestRun

核心服务

•
backend/apps/app_testing/services.py：HTTP 代理 Sonic Controller API

•
backend/apps/app_testing/sonic_auth.py：Sonic Token 自动登录与续期

•
backend/apps/app_testing/sonic_case.py：用例步骤与 Sonic 步骤格式互转

亮点特性

•
AITS 项目 ↔ Sonic 项目通过 Project.sonic_project_id 桥接

•
用例同时保留"AITS 内部步骤" + "Sonic 兼容步骤"两份结构，便于回放与扩展

•
在定时任务中可指定 device_udid / device_id / device_name / platform

•
设备远控面板（前端 DeviceRemotePanel.vue）通过 jmuxer 实时回放屏幕流

4.5 性能测试 apps/performance 【新增】

功能职责

•
发压配置模板（并发数 / 爬坡率 / 时长）

•
压测场景管理：来源 ∈ {接口套件导入 / 接口用例导入 / 自定义脚本}

•
压测执行（Celery 子进程跑 Locust）

•
CSV 解析（聚合统计、P95、错误率）

•
Prometheus + Grafana 实时监控

•
AI 性能诊断：Grafana Webhook → LLM 分析 → 写入 AiDiagnosisRecord

•
监控大盘自定义布局（vue3-grid-layout-next）

核心模型（见 backend/apps/performance/models.py）

•
LoadConfiguration：发压配置模板

•
PerformanceScenario：压测场景，三种来源类型

•
PerformanceExecution：单次执行，含 total_requests / avg_tps / p95_response_time / error_rate / celery_task_id

•
AiDiagnosisRecord：Grafana 告警 → AI 诊断结果（含 grafana_url / diagnosis_content / 处理状态）

核心服务

•
backend/apps/performance/tasks.py run_performance_test：Celery 子进程跑 Locust，轮询写指标

•
backend/apps/performance/script_utils.py generate_locust_script：根据场景生成 locustfile.py

•
backend/apps/performance/stats_csv.py：解析 Locust CSV（aggregate / percentiles）

•
backend/utils/prometheus_sd.py update_windows_exporter_target：自动维护 Prometheus File SD 目标文件

亮点特性

•
性能项目可挂多个 API 项目作为脚本源

•
Locust 子进程隔离运行，CSV 实时解析回写指标

•
Prometheus File SD 自动注册被压机器（基于本机出口 IPv4）

•
AI 性能诊断：告警 → LLM 分析 → 通知接收人 → 处理闭环

4.6 AI 核心 apps/ai_core

功能职责

•
多 LLM 模型管理（OpenAI / DeepSeek / Qwen / 本地 HuggingFace 等）

•
视觉模型支持（Qwen-VL / UI-TARS / Doubao Vision / Gemini）

•
RAG 知识库管理（ChromaDB / Milvus 双轨）

•
MCP 协议支持（Model Context Protocol）

•
LangGraph 多 Agent 工作流编排

•
LLM 使用日志（Token 统计与审计）

核心模型（见 backend/apps/ai_core/models.py）

•
LLMConfiguration：统一管理 LLM 与视觉模型，支持 is_default（同类型唯一）

•
RAGConfiguration：向量库类型 + Embedding 加载模式（local / remote）+ 分块参数 + Chroma/Milvus 连接信息

•
MCPConfiguration + MCPTool：MCP 服务器配置（原始 JSON 形式）+ 工具索引

•
LLMUsageLog：Token 使用日志（prompt / completion / total / 响应时间 / 成功标记 / 任务类型与 ID）

核心服务

•
ModelManager（backend/apps/ai_core/model_manager.py）：统一调度多模型

•
RAGService（backend/apps/ai_core/rag_service.py）：知识库索引与检索

•
EmbeddingLoader（backend/apps/ai_core/embedding_loader.py）：嵌入模型双模式加载

亮点特性

•
数据库驱动的模型配置（无需重启即可切换）

•
LangGraph 工作流编排（参见 §5）

•
RAG 双向量库 + 双 Embedding 加载模式

•
MCP 协议扩展，可挂接外部工具能力

•
Token 用量统计可下钻到任务类型 / 任务 ID

4.7 定时任务 apps/scheduled_tasks

功能职责

•
统一调度中心（Web / API / App 三类测试套件）

•
Cron 表达式配置（如 0 9 * * 1-5）

•
执行历史与结构化日志（TaskExecutionLog）

•
与通知中心联动（任务完成自动推送）

•
App 类型可附加 app_run_config（设备 UDID 等）

核心模型（见 backend/apps/scheduled_tasks/models.py）

•
ScheduledTask：含 suite_type ∈ {web, app, api}、suite_ids（JSON 数组）、cron_expression、environment、notice_targets（M2M → NotificationReceiver）

•
TaskExecutionLog：执行结果统计、报告路径、step_log

核心机制

•
django-celery-beat 数据库调度器：动态增删改不需要重启 Beat

•
signals.py：任务保存时同步生成 / 更新 PeriodicTask

•
与通知中心解耦：任务完成时调用 notifications.services.trigger_notification

亮点特性

•
三类测试套件统一调度

•
Cron 表达式配置 + 友好描述（前端 cronstrue）

•
触发条件可选 always / fail

•
执行历史完整链路追踪

4.8 通知中心 apps/notifications 【新增】

功能职责

•
全局渠道管理（钉钉 / 企业微信 / 飞书 / 邮件等）

•
项目级通知接收对象（NotificationReceiver）

•
邮件 SMTP 动态配置（EmailConfig）

•
定时任务完成结果通知（trigger_notification）

•
Markdown 推送 + HTML 邮件双形态

核心模型（见 backend/apps/notifications/models.py）

•
NotificationChannel：全局渠道元数据，含 channel_code（如 dingtalk / wechat_work / email）

•
NotificationReceiver：项目级接收对象，关联渠道 + Webhook 地址或邮箱

•
EmailConfig：SMTP 配置（端口默认 465，SSL 默认开启）

核心服务

◦
拉取任务的 notice_targets，按 trigger_condition 判定（always / fail）

◦
组装 Markdown：任务名 / 通过率 / 通过-失败-跳过-总计 / 报告链接

◦
钉钉 / 企微 走 webhook，邮件走 EmailMultiAlternatives + get_connection

◦
单渠道失败不影响其他渠道与主流程

亮点特性

•
全局渠道 + 项目级接收人 双层模型，复用 + 隔离兼顾

•
Markdown / HTML 双格式自动适配渠道

•
报告链接基于 FRONTEND_BASE_URL 自动拼接

•
失败容错：单渠道异常仅记日志

4.9 用户管理 apps/users

功能职责

•
自定义 User 模型（AUTH_USER_MODEL='users.User'）

•
JWT 认证（Access + Refresh）

•
Token 黑名单（rest_framework_simplejwt.token_blacklist）

核心特性

•
Access Token 有效期 600 分钟，Refresh Token 1 天

•
旋转 Refresh Token，旧 Token 自动加入黑名单

•
Authorization: Bearer <token> 标准协议

4.10 通用基础 apps/common

功能职责

•
WebSocket 服务体系（websocket/）

•
异常处理（api/api_exception_handler.py，DRF EXCEPTION_HANDLER）

•
文件存储（storage/file_storage.py，含 API 规范文件服务）

•
Celery 任务工具函数（task/）

•
解析器（parsers/，YAML / JSON 修复与提取）

关键能力

•
WebSocketJWTAuthMiddlewareStack：URL 参数 ?token=xxx 自动解析 JWT

•
BaseWebSocketConsumer + StreamingConsumerMixin + TaskStatusMixin：可复用的 Consumer 基类

•
WebSocketMessageService：业务侧统一消息推送入口

•
WebSocketConsumerFactory：Consumer 注册中心

5. AI 智能体清单

AITS v2 共落地 7 个 LangGraph Agent + 1 个 LLM 服务节点，全部位于 apps/ai_core/：

序号

名称

文件位置

职责

1

API 端点用例生成器

api_testcase_generator.py

基于 OpenAPI 端点 + RAG 上下文，生成 HttpRunner 用例（正向 / 负向 / 边界 / 安全）

2

API 场景 Agent

api_scenario_agent.py

自然语言 → 业务上下文识别 → API 映射 → 端到端 HttpRunner 场景脚本（LangGraph StateGraph）

3

Postman 脚本翻译 Agent

postman_script_translator.py

把 pm.test() / pre-request JS 翻译为 HttpRunner 原生 validate / extract / variables / debugtalk_snippets，使用 Pydantic 结构化输出

4

WebUI 用例生成 Agent

webui_testcase_agent.py

多角色子智能体协作（LangGraph 流式输出），生成 WebUI 测试用例

5

WebUI Playwright Agent

webui_playwright_agent.py

自然语言 + POM → Playwright 脚本

6

MidScene Agent

webui_midscene_agent.py

基于视觉模型的 UI 测试 Agent

7

MidScene 脚本 Agent

midscene_script_agent.py

MidScene 脚本生成与维护

—

LLM 服务节点

model_manager.py

多模型调度、流式回调、错误重试

此外，性能测试 AI 诊断虽未独立成 Agent，但同样调用 LLMManager，将 Grafana 告警转为 AiDiagnosisRecord.diagnosis_content，详见 §6.3。

LangGraph 编排关键模式

•
使用 StateGraph + TypedDict 定义 Agent 状态（如 ScenarioAgentState）

•
节点输出通过 send_node_start_notification_helper 推送到 WebSocket，前端可见每一步

•
使用 Pydantic BaseModel 实现结构化输出（结合 LLM Function Call）

•
RAG 检索作为节点之一，按需调用 get_rag_manager()

6. 监控与可观测性 【新增章节】

6.1 Prometheus + Grafana 容器化

aits_monitor 子目录提供完整的监控栈 docker-compose（backend/aits_monitor/docker-compose.yml）：

代码块
YAML
services:
  prometheus:
    image: prom/prometheus:latest
    ports: ["9090:9090"]
    volumes:

prometheus.yml 中的两个 scrape job：

•
locust-performance：抓取 Locust prometheus exporter（host.docker.internal:8089）

•
windows-exporter：使用 file_sd_configs 动态加载被压机器列表

6.2 File SD 自动注册

backend/utils/prometheus_sd.py 的 update_windows_exporter_target() 方法：

•
通过 UDP dummy 探测本机出口 IPv4

•
输出到 backend/aits_monitor/prometheus/targets.json

•
在性能项目执行前自动调用，无需手动维护 IP

代码块
JSON
[
  {
    "targets": ["192.168.x.x:9182"],
    "labels": {"instance": "AITS-Generator", "role": "load-generator"}
  }
]

是否启用受 settings.py PROMETHEUS_SD_AUTO_UPDATE 控制（默认 True）。

6.3 AI 性能诊断闭环

关键设计

•
AiDiagnosisRecord 落库三态：pending / resolved / ignored

•
默认通知接收人由 GRAFANA_AI_NOTIFY_RECEIVER_ID 或 GRAFANA_AI_NOTIFY_RECEIVER_NAME_KEYWORD（默认匹配 "AI测试部门群"）选定

•
接收人缓存于 Redis（performance:grafana_ai_notify_target）

6.4 Windows Exporter 接入

被压机器需运行 Windows Exporter（端口 9182），AITS 性能模块在每次执行前自动将其 IP 写入 Prometheus File SD，无需手工维护 targets.json。

7. 通知体系 【新增章节】

7.1 模型分层

代码块
Plain Text
NotificationChannel (全局渠道)
    │ 1
    │ N
    ↓
NotificationReceiver (项目级接收对象)
    │ N

•
NotificationChannel（全局）：渠道元数据 + 接入说明（channel_code ∈ {dingtalk, wechat_work, feishu, email, ...}）

•
NotificationReceiver（项目级）：必须归属项目，关联全局渠道，存放 webhook_url 或 target_address（邮箱列表，逗号分隔）

•
EmailConfig：SMTP 服务器配置，独立于渠道，用于邮件渠道发送

7.2 触发与组装

入口：trigger_notification(scheduled_task_id, execution_log, result=None)（见 backend/apps/notifications/services.py）

判定流程：

1.
重查 TaskExecutionLog，获取最新统计

2.
若 task.trigger_condition == 'fail' 且本次全部通过，直接返回

3.
拉取 task.notice_targets.filter(is_active=True)

4.
组装 Markdown：

代码块
Markdown
## 定时任务执行结果
**任务名称**: <name>
**执行结果**: 已完成
**通过/失败/跳过/总计**: <p>/<f>/<s>/<t>
**成功率**: <r>%
**测试结论**: 测试通过 | 测试未通过
**开始时间**: yyyy-MM-dd HH:mm:ss

◦
钉钉：{"msgtype":"markdown","markdown":{"title":..., "text":...}}

◦
企微：{"msgtype":"markdown","markdown":{"content":...}}

◦
邮件：EmailMultiAlternatives + 动态 SMTP（从 EmailConfig 读取）

6.
单渠道异常仅日志，不影响其他渠道与主流程

7.3 邮件渠道

•
端口默认 465，SSL 默认开启

•
通过 get_connection(host=..., port=..., username=..., password=..., use_ssl=...) 建立动态连接

•
HTML + 纯文本双格式，自适应客户端

8. 部署与运行

8.1 启动顺序（开发环境）

按 backend/启动脚本.txt 顺序执行：

代码块
PowerShell
# 1. Redis（如未自启）
redis-server
# 检查
netstat -an | findstr 6379

8.2 监控容器

代码块
PowerShell
cd /d D:\dev\proj\aits-system\backend\aits_monitor
docker-compose up -d
# Prometheus :9090
# Grafana :3000  (默认账号 admin / admin)

8.3 Sonic 移动端集群

代码块
PowerShell
cd /d D:\dev\proj\aits-system\sonic-server
# 国内镜像编排
docker-compose -f docker-compose-zh.yml up -d
# 启动 sonic-mysql / sonic-server-eureka / sonic-server-gateway / sonic-server-controller / sonic-server-folder

8.4 关键环境变量

变量

默认值

说明

DJANGO_SECRET_KEY

dev 占位

生产必须替换

DEBUG

True

生产置 False

REDIS_URL

redis://localhost:6379/0

Celery Broker / Cache / Channel Layer

FRONTEND_BASE_URL

http://127.0.0.1:5173

通知报告链接、CORS、CSRF 来源

SONIC_BASE_URL

空

Sonic Controller 入口；空则无法拉设备/套件

SONIC_API_PREFIX

/server/api

Sonic 接口前缀

SONIC_USERNAME/PASSWORD/TOKEN/PROJECT_ID

—

Sonic 登录凭据

PROMETHEUS_SD_AUTO_UPDATE

True

是否自动维护 Prometheus File SD

GRAFANA_AI_NOTIFY_RECEIVER_ID / GRAFANA_AI_NOTIFY_RECEIVER_NAME_KEYWORD

空 / "AI测试部门群"

AI 诊断默认通知接收人

8.5 生产部署建议

•
Web 服务器：Nginx 反代 Uvicorn，统一处理静态文件与 SSL

•
数据库：切换为 PostgreSQL（settings.py 中保留有完整配置注释）

•
Celery 池：Linux 下使用默认 prefork，Windows 推荐 eventlet

•
Redis 持久化：开启 AOF 与 RDB

•
Channels 频道：Redis Channel Layer capacity=100，expiry=60s，group_expiry=86400s（已配）

•
Sonic 与监控：建议独立宿主机 / K8s 部署，便于资源隔离

9. v1 → v2 升级对照表

9.1 模块层

模块

v1 状态

v2 状态

项目管理 projects

已有

已有 + sonic_project_id / linked_api_projects / ProjectThirdPartyConfig

API 测试 api_testing

已有（HttpRunner）

已有 + Postman 解析 + Postman 脚本 AI 翻译 + 场景编排器

Web 测试 web_testing

已有（Playwright）

已有 + MidScene + 多 Agent + POM 管理

App 测试 app_testing

无

新增（Sonic Spring Cloud 集成）

性能测试 performance

无

新增（Locust + Prometheus + Grafana + AI 诊断）

AI 核心 ai_core

已有（2 Agent）

已有 + 7 Agent + MCP 协议 + RAG 双向量库 + Token 日志

定时任务 scheduled_tasks

已有（Web/API）

已有 + App 类型 + app_run_config + 通知触发

通知中心 notifications

无

新增（多渠道 + 邮件 SMTP + 项目级接收人）

用户管理 users

已有

已有 + JWT 黑名单 + 旋转 Refresh

9.2 技术栈层

项

v1 文档

v2 实际

Django

5.2.5（笔误）

4.2.25

LangChain

未锁版本

1.2.0

LangGraph

未提及

1.0.5

Celery

未锁

5.3.4

Channels

未锁

4.0.0

ChromaDB

未锁

1.4.0

Milvus（pymilvus）

未锁

2.6.5

Locust

未提及

2.43.3

MCP

未提及

mcp 1.12.4 + mcp-use 1.5.1 + langchain-mcp-adapters 0.2.1

Prometheus

未提及

prometheus_client 0.23.1 + 容器化部署

Sonic

未提及

Spring Cloud（Eureka + Gateway + Controller + Folder）

数据库

PostgreSQL

开发 SQLite，生产 PostgreSQL

9.3 架构层

维度

v1 描述

v2 描述

业务层 App 数量

6

9

测试执行引擎

2（HttpRunner + Playwright）

5（+ MidScene + Sonic + Locust）

AI Agent 数量

2（构想）

7（已实现）

实时通信

笼统 WebSocket

Channels + ASGI + JWT 中间件 + 5 个 Consumer

报告体系

Allure

Allure + ECharts 实时大盘 + Prometheus/Grafana + AI 诊断

通知

—

多渠道 + 项目级接收人 + 邮件 SMTP

监控

—

Prometheus + Grafana + Windows Exporter + AI 性能诊断

部署形态

单体

单体 + 监控容器 + Sonic 容器集群

9.4 概念变化

•
Agent 形态：从"单步 Chain"演进到"有状态 StateGraph"，每步可流式输出到 WebSocket

•
测试资产：从"用例 → 套件"二级结构演进到"模块树 → 用例 → 套件 → 执行 → 报告"五级结构

•
通知：从"无"演进到"任务完成 → Markdown 自动组装 → 多渠道分发 → 失败容错"

•
可观测：从"无"演进到"指标采集 → 大盘可视化 → 告警触发 → AI 诊断 → 通知 → 处置闭环"