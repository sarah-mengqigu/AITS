# AITS v2 API 参考

> 由 `docs/openapi.yaml`（drf-spectacular 生成）自动整理，共 **145 条路径 / 269 个操作**。
> 运行时交互式文档：`/api/docs/`（Swagger UI）、`/api/redoc/`、`/api/schema/`。

## 通用约定

| 项 | 说明 |
|---|---|
| 认证 | `Authorization: Bearer <access_token>`；获取：`POST /api/auth/login/` |
| 分页 | 请求 `?page=&page_size=`；响应 `{count, page, page_size, total_pages, next, previous, results}` |
| 过滤/搜索/排序 | `?search=`、`?ordering=` 及各模块 `filterset_fields` |
| 错误信封 | `{"code": "...", "message": "...", "errors": {...}, "status_code": N}` |
| 长任务 | 返回 `202 {"task_id", "status"}`；进度经 `ws/task-status/<task_id>/?token=<jwt>` |
| 项目权限 | `viewer` 读、`editor` 写/执行、`admin`/`owner` 管理配置与删除 |
| 数据隔离 | 所有业务对象按 `.project` 归属过滤，非成员不可见 |

## AI 核心（模型 / RAG / MCP / Agents）

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `GET` | `/api/ai/agents/` | ai_agents_retrieve | 登录 |
| `POST` | `/api/ai/agents/{id}/run/` | ai_agents_run_create | 登录 |
| `GET` | `/api/ai/llm-configs/` | ai_llm_configs_list | 登录 |
| `POST` | `/api/ai/llm-configs/` | ai_llm_configs_create | 登录 |
| `DELETE` | `/api/ai/llm-configs/{id}/` | ai_llm_configs_destroy | 登录 |
| `GET` | `/api/ai/llm-configs/{id}/` | ai_llm_configs_retrieve | 登录 |
| `PATCH` | `/api/ai/llm-configs/{id}/` | ai_llm_configs_partial_update | 登录 |
| `PUT` | `/api/ai/llm-configs/{id}/` | ai_llm_configs_update | 登录 |
| `POST` | `/api/ai/llm-configs/{id}/set-default/` | ai_llm_configs_set_default_create | 登录 |
| `POST` | `/api/ai/llm-configs/{id}/test/` | ai_llm_configs_test_create | 登录 |
| `GET` | `/api/ai/mcp-configs/` | ai_mcp_configs_list | 登录 |
| `POST` | `/api/ai/mcp-configs/` | ai_mcp_configs_create | 登录 |
| `DELETE` | `/api/ai/mcp-configs/{id}/` | ai_mcp_configs_destroy | 登录 |
| `GET` | `/api/ai/mcp-configs/{id}/` | ai_mcp_configs_retrieve | 登录 |
| `PATCH` | `/api/ai/mcp-configs/{id}/` | ai_mcp_configs_partial_update | 登录 |
| `PUT` | `/api/ai/mcp-configs/{id}/` | ai_mcp_configs_update | 登录 |
| `POST` | `/api/ai/mcp-configs/{id}/refresh_tools/` | ai_mcp_configs_refresh_tools_create | 登录 |
| `GET` | `/api/ai/mcp-tools/` | ai_mcp_tools_list | 登录 |
| `GET` | `/api/ai/mcp-tools/{id}/` | ai_mcp_tools_retrieve | 登录 |
| `GET` | `/api/ai/rag-configs/` | ai_rag_configs_list | 登录 |
| `POST` | `/api/ai/rag-configs/` | ai_rag_configs_create | 登录 |
| `DELETE` | `/api/ai/rag-configs/{id}/` | ai_rag_configs_destroy | 登录 |
| `GET` | `/api/ai/rag-configs/{id}/` | ai_rag_configs_retrieve | 登录 |
| `PATCH` | `/api/ai/rag-configs/{id}/` | ai_rag_configs_partial_update | 登录 |
| `PUT` | `/api/ai/rag-configs/{id}/` | ai_rag_configs_update | 登录 |
| `POST` | `/api/ai/rag-configs/{id}/set-default/` | ai_rag_configs_set_default_create | 登录 |
| `POST` | `/api/ai/rag/index/` | ai_rag_index_create | 登录 |
| `POST` | `/api/ai/rag/search/` | ai_rag_search_create | 登录 |
| `GET` | `/api/ai/rag/stats/` | ai_rag_stats_retrieve | 登录 |
| `GET` | `/api/ai/usage-logs/` | ai_usage_logs_list | 登录 |
| `GET` | `/api/ai/usage-logs/{id}/` | ai_usage_logs_retrieve | 登录 |
| `GET` | `/api/ai/usage-stats/` | ai_usage_stats_retrieve | 登录 |

## API 测试

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `POST` | `/api/api-testing/ai/generate_scenario/` | api_testing_ai_generate_scenario_create | 登录 |
| `GET` | `/api/api-testing/cases/` | api_testing_cases_list | 登录 |
| `POST` | `/api/api-testing/cases/` | api_testing_cases_create | 登录 |
| `DELETE` | `/api/api-testing/cases/{id}/` | api_testing_cases_destroy | 登录 |
| `GET` | `/api/api-testing/cases/{id}/` | api_testing_cases_retrieve | 登录 |
| `PATCH` | `/api/api-testing/cases/{id}/` | api_testing_cases_partial_update | 登录 |
| `PUT` | `/api/api-testing/cases/{id}/` | api_testing_cases_update | 登录 |
| `GET` | `/api/api-testing/cases/{id}/generate_script/` | api_testing_cases_generate_script_retrieve | 登录 |
| `POST` | `/api/api-testing/cases/{id}/generate_script/` | api_testing_cases_generate_script_create | 登录 |
| `POST` | `/api/api-testing/cases/{id}/run/` | api_testing_cases_run_create | 登录 |
| `GET` | `/api/api-testing/endpoints/` | api_testing_endpoints_list | 登录 |
| `POST` | `/api/api-testing/endpoints/` | api_testing_endpoints_create | 登录 |
| `DELETE` | `/api/api-testing/endpoints/{id}/` | api_testing_endpoints_destroy | 登录 |
| `GET` | `/api/api-testing/endpoints/{id}/` | api_testing_endpoints_retrieve | 登录 |
| `PATCH` | `/api/api-testing/endpoints/{id}/` | api_testing_endpoints_partial_update | 登录 |
| `PUT` | `/api/api-testing/endpoints/{id}/` | api_testing_endpoints_update | 登录 |
| `GET` | `/api/api-testing/endpoints/{id}/generate_cases/` | api_testing_endpoints_generate_cases_retrieve | 登录 |
| `POST` | `/api/api-testing/endpoints/{id}/generate_cases/` | api_testing_endpoints_generate_cases_create | 登录 |
| `GET` | `/api/api-testing/executions/` | api_testing_executions_list | 登录 |
| `GET` | `/api/api-testing/executions/{id}/` | api_testing_executions_retrieve | 登录 |
| `POST` | `/api/api-testing/executions/{id}/cancel/` | api_testing_executions_cancel_create | 登录 |
| `GET` | `/api/api-testing/executions/{id}/report/` | api_testing_executions_report_retrieve | 登录 |
| `GET` | `/api/api-testing/modules/` | api_testing_modules_list | 登录 |
| `POST` | `/api/api-testing/modules/` | api_testing_modules_create | 登录 |
| `GET` | `/api/api-testing/modules/tree/` | api_testing_modules_tree_retrieve | 登录 |
| `DELETE` | `/api/api-testing/modules/{id}/` | api_testing_modules_destroy | 登录 |
| `GET` | `/api/api-testing/modules/{id}/` | api_testing_modules_retrieve | 登录 |
| `PATCH` | `/api/api-testing/modules/{id}/` | api_testing_modules_partial_update | 登录 |
| `PUT` | `/api/api-testing/modules/{id}/` | api_testing_modules_update | 登录 |
| `POST` | `/api/api-testing/postman/import/` | api_testing_postman_import_create | 登录 |
| `GET` | `/api/api-testing/specs/` | api_testing_specs_list | 登录 |
| `POST` | `/api/api-testing/specs/` | api_testing_specs_create | 登录 |
| `POST` | `/api/api-testing/specs/import/` | api_testing_specs_import_create | 登录 |
| `DELETE` | `/api/api-testing/specs/{id}/` | api_testing_specs_destroy | 登录 |
| `GET` | `/api/api-testing/specs/{id}/` | api_testing_specs_retrieve | 登录 |
| `PATCH` | `/api/api-testing/specs/{id}/` | api_testing_specs_partial_update | 登录 |
| `PUT` | `/api/api-testing/specs/{id}/` | api_testing_specs_update | 登录 |
| `POST` | `/api/api-testing/specs/{id}/reparse/` | api_testing_specs_reparse_create | 登录 |
| `GET` | `/api/api-testing/suites/` | api_testing_suites_list | 登录 |
| `POST` | `/api/api-testing/suites/` | api_testing_suites_create | 登录 |
| `DELETE` | `/api/api-testing/suites/{id}/` | api_testing_suites_destroy | 登录 |
| `GET` | `/api/api-testing/suites/{id}/` | api_testing_suites_retrieve | 登录 |
| `PATCH` | `/api/api-testing/suites/{id}/` | api_testing_suites_partial_update | 登录 |
| `PUT` | `/api/api-testing/suites/{id}/` | api_testing_suites_update | 登录 |
| `POST` | `/api/api-testing/suites/{id}/run/` | api_testing_suites_run_create | 登录 |

## 移动端 App 测试

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `GET` | `/api/app-testing/applications/` | app_testing_applications_list | 登录 |
| `POST` | `/api/app-testing/applications/` | app_testing_applications_create | 登录 |
| `DELETE` | `/api/app-testing/applications/{id}/` | app_testing_applications_destroy | 登录 |
| `GET` | `/api/app-testing/applications/{id}/` | app_testing_applications_retrieve | 登录 |
| `PATCH` | `/api/app-testing/applications/{id}/` | app_testing_applications_partial_update | 登录 |
| `PUT` | `/api/app-testing/applications/{id}/` | app_testing_applications_update | 登录 |
| `GET` | `/api/app-testing/cases/` | app_testing_cases_list | 登录 |
| `POST` | `/api/app-testing/cases/` | app_testing_cases_create | 登录 |
| `DELETE` | `/api/app-testing/cases/{id}/` | app_testing_cases_destroy | 登录 |
| `GET` | `/api/app-testing/cases/{id}/` | app_testing_cases_retrieve | 登录 |
| `PATCH` | `/api/app-testing/cases/{id}/` | app_testing_cases_partial_update | 登录 |
| `PUT` | `/api/app-testing/cases/{id}/` | app_testing_cases_update | 登录 |
| `POST` | `/api/app-testing/cases/{id}/generate_steps/` | app_testing_cases_generate_steps_create | 登录 |
| `GET` | `/api/app-testing/devices/` | app_testing_devices_retrieve | 登录 |
| `GET` | `/api/app-testing/devices/{id}/` | app_testing_devices_retrieve_2 | 登录 |
| `POST` | `/api/app-testing/devices/{id}/remote/` | app_testing_devices_remote_create | 登录 |
| `GET` | `/api/app-testing/element-pages/` | app_testing_element_pages_retrieve | 登录 |
| `GET` | `/api/app-testing/modules/` | app_testing_modules_list | 登录 |
| `POST` | `/api/app-testing/modules/` | app_testing_modules_create | 登录 |
| `GET` | `/api/app-testing/modules/tree/` | app_testing_modules_tree_retrieve | 登录 |
| `DELETE` | `/api/app-testing/modules/{id}/` | app_testing_modules_destroy | 登录 |
| `GET` | `/api/app-testing/modules/{id}/` | app_testing_modules_retrieve | 登录 |
| `PATCH` | `/api/app-testing/modules/{id}/` | app_testing_modules_partial_update | 登录 |
| `PUT` | `/api/app-testing/modules/{id}/` | app_testing_modules_update | 登录 |
| `GET` | `/api/app-testing/runs/` | app_testing_runs_list | 登录 |
| `GET` | `/api/app-testing/runs/{id}/` | app_testing_runs_retrieve | 登录 |
| `POST` | `/api/app-testing/runs/{id}/cancel/` | app_testing_runs_cancel_create | 登录 |
| `GET` | `/api/app-testing/runs/{id}/report/` | app_testing_runs_report_retrieve | 登录 |
| `GET` | `/api/app-testing/suites/` | app_testing_suites_list | 登录 |
| `POST` | `/api/app-testing/suites/` | app_testing_suites_create | 登录 |
| `DELETE` | `/api/app-testing/suites/{id}/` | app_testing_suites_destroy | 登录 |
| `GET` | `/api/app-testing/suites/{id}/` | app_testing_suites_retrieve | 登录 |
| `PATCH` | `/api/app-testing/suites/{id}/` | app_testing_suites_partial_update | 登录 |
| `PUT` | `/api/app-testing/suites/{id}/` | app_testing_suites_update | 登录 |
| `POST` | `/api/app-testing/suites/{id}/run/` | app_testing_suites_run_create | 登录 |

## 认证（JWT）

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `POST` | `/api/auth/change-password/` | auth_change_password_create | 登录 |
| `POST` | `/api/auth/login/` | auth_login_create | 登录 |
| `POST` | `/api/auth/logout/` | auth_logout_create | 登录 |
| `GET` | `/api/auth/me/` | auth_me_retrieve | 登录 |
| `PATCH` | `/api/auth/me/` | auth_me_partial_update | 登录 |
| `PUT` | `/api/auth/me/` | auth_me_update | 登录 |
| `POST` | `/api/auth/refresh/` | auth_refresh_create | 按项目角色 |
| `POST` | `/api/auth/register/` | auth_register_create | 登录 |
| `POST` | `/api/auth/verify/` | auth_verify_create | 按项目角色 |

## 通知中心

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `GET` | `/api/notifications/channels/` | notifications_channels_list | 登录 |
| `POST` | `/api/notifications/channels/` | notifications_channels_create | 登录 |
| `GET` | `/api/notifications/channels/{id}/` | notifications_channels_retrieve | 登录 |
| `PATCH` | `/api/notifications/channels/{id}/` | notifications_channels_partial_update | 登录 |
| `PUT` | `/api/notifications/channels/{id}/` | notifications_channels_update | 登录 |
| `GET` | `/api/notifications/email-config/` | notifications_email_config_retrieve | 登录 |
| `PATCH` | `/api/notifications/email-config/` | notifications_email_config_partial_update | 登录 |
| `PUT` | `/api/notifications/email-config/` | notifications_email_config_update | 登录 |
| `GET` | `/api/notifications/logs/` | notifications_logs_list | 登录 |
| `GET` | `/api/notifications/logs/{id}/` | notifications_logs_retrieve | 登录 |
| `GET` | `/api/notifications/receivers/` | notifications_receivers_list | 登录 |
| `POST` | `/api/notifications/receivers/` | notifications_receivers_create | 登录 |
| `DELETE` | `/api/notifications/receivers/{id}/` | notifications_receivers_destroy | 登录 |
| `GET` | `/api/notifications/receivers/{id}/` | notifications_receivers_retrieve | 登录 |
| `PATCH` | `/api/notifications/receivers/{id}/` | notifications_receivers_partial_update | 登录 |
| `PUT` | `/api/notifications/receivers/{id}/` | notifications_receivers_update | 登录 |
| `POST` | `/api/notifications/test/` | notifications_test_create | 登录 |

## 性能测试

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `GET` | `/api/performance/configs/` | performance_configs_list | 登录 |
| `POST` | `/api/performance/configs/` | performance_configs_create | 登录 |
| `DELETE` | `/api/performance/configs/{id}/` | performance_configs_destroy | 登录 |
| `GET` | `/api/performance/configs/{id}/` | performance_configs_retrieve | 登录 |
| `PATCH` | `/api/performance/configs/{id}/` | performance_configs_partial_update | 登录 |
| `PUT` | `/api/performance/configs/{id}/` | performance_configs_update | 登录 |
| `GET` | `/api/performance/dashboard/` | performance_dashboard_retrieve | 登录 |
| `GET` | `/api/performance/diagnoses/` | performance_diagnoses_list | 登录 |
| `POST` | `/api/performance/diagnoses/` | performance_diagnoses_create | 登录 |
| `DELETE` | `/api/performance/diagnoses/{id}/` | performance_diagnoses_destroy | 登录 |
| `GET` | `/api/performance/diagnoses/{id}/` | performance_diagnoses_retrieve | 登录 |
| `PATCH` | `/api/performance/diagnoses/{id}/` | performance_diagnoses_partial_update | 登录 |
| `PUT` | `/api/performance/diagnoses/{id}/` | performance_diagnoses_update | 登录 |
| `GET` | `/api/performance/executions/` | performance_executions_list | 登录 |
| `GET` | `/api/performance/executions/{id}/` | performance_executions_retrieve | 登录 |
| `POST` | `/api/performance/executions/{id}/cancel/` | performance_executions_cancel_create | 登录 |
| `GET` | `/api/performance/executions/{id}/report/` | performance_executions_report_retrieve | 登录 |
| `GET` | `/api/performance/grafana/webhook/` | performance_grafana_webhook_retrieve | 匿名 |
| `POST` | `/api/performance/grafana/webhook/` | performance_grafana_webhook_create | 匿名 |
| `GET` | `/api/performance/scenarios/` | performance_scenarios_list | 登录 |
| `POST` | `/api/performance/scenarios/` | performance_scenarios_create | 登录 |
| `DELETE` | `/api/performance/scenarios/{id}/` | performance_scenarios_destroy | 登录 |
| `GET` | `/api/performance/scenarios/{id}/` | performance_scenarios_retrieve | 登录 |
| `PATCH` | `/api/performance/scenarios/{id}/` | performance_scenarios_partial_update | 登录 |
| `PUT` | `/api/performance/scenarios/{id}/` | performance_scenarios_update | 登录 |
| `POST` | `/api/performance/scenarios/{id}/generate_script/` | performance_scenarios_generate_script_create | 登录 |
| `POST` | `/api/performance/scenarios/{id}/run/` | performance_scenarios_run_create | 登录 |

## 项目管理

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `GET` | `/api/projects/` | projects_list | 登录 |
| `POST` | `/api/projects/` | projects_create | 登录 |
| `GET` | `/api/projects/environments/` | projects_environments_list | 登录 |
| `POST` | `/api/projects/environments/` | projects_environments_create | 登录 |
| `DELETE` | `/api/projects/environments/{id}/` | projects_environments_destroy | 登录 |
| `GET` | `/api/projects/environments/{id}/` | projects_environments_retrieve | 登录 |
| `PATCH` | `/api/projects/environments/{id}/` | projects_environments_partial_update | 登录 |
| `PUT` | `/api/projects/environments/{id}/` | projects_environments_update | 登录 |
| `POST` | `/api/projects/environments/{id}/set-default/` | projects_environments_set_default_create | 登录 |
| `GET` | `/api/projects/files/` | projects_files_list | 登录 |
| `POST` | `/api/projects/files/` | projects_files_create | 登录 |
| `DELETE` | `/api/projects/files/{id}/` | projects_files_destroy | 登录 |
| `GET` | `/api/projects/files/{id}/` | projects_files_retrieve | 登录 |
| `PATCH` | `/api/projects/files/{id}/` | projects_files_partial_update | 登录 |
| `PUT` | `/api/projects/files/{id}/` | projects_files_update | 登录 |
| `GET` | `/api/projects/files/{id}/download/` | projects_files_download_retrieve | 登录 |
| `GET` | `/api/projects/knowledge/` | projects_knowledge_list | 登录 |
| `POST` | `/api/projects/knowledge/` | projects_knowledge_create | 登录 |
| `DELETE` | `/api/projects/knowledge/{id}/` | projects_knowledge_destroy | 登录 |
| `GET` | `/api/projects/knowledge/{id}/` | projects_knowledge_retrieve | 登录 |
| `PATCH` | `/api/projects/knowledge/{id}/` | projects_knowledge_partial_update | 登录 |
| `PUT` | `/api/projects/knowledge/{id}/` | projects_knowledge_update | 登录 |
| `POST` | `/api/projects/knowledge/{id}/reindex/` | projects_knowledge_reindex_create | 登录 |
| `GET` | `/api/projects/members/` | projects_members_list | 登录 |
| `POST` | `/api/projects/members/` | projects_members_create | 登录 |
| `DELETE` | `/api/projects/members/{id}/` | projects_members_destroy | 登录 |
| `GET` | `/api/projects/members/{id}/` | projects_members_retrieve | 登录 |
| `PATCH` | `/api/projects/members/{id}/` | projects_members_partial_update | 登录 |
| `PUT` | `/api/projects/members/{id}/` | projects_members_update | 登录 |
| `DELETE` | `/api/projects/{id}/` | projects_destroy | 登录 |
| `GET` | `/api/projects/{id}/` | projects_retrieve | 登录 |
| `PATCH` | `/api/projects/{id}/` | projects_partial_update | 登录 |
| `PUT` | `/api/projects/{id}/` | projects_update | 登录 |
| `GET` | `/api/projects/{id}/members/` | projects_members_retrieve_2 | 登录 |
| `POST` | `/api/projects/{id}/members/add/` | projects_members_add_create | 登录 |
| `DELETE` | `/api/projects/{id}/members/{member_id}/` | projects_members_destroy_2 | 登录 |
| `GET` | `/api/projects/{id}/stats/` | projects_stats_retrieve | 登录 |
| `GET` | `/api/projects/{id}/third-party-config/` | projects_third_party_config_retrieve | 登录 |
| `PATCH` | `/api/projects/{id}/third-party-config/` | projects_third_party_config_partial_update | 登录 |
| `PUT` | `/api/projects/{id}/third-party-config/` | projects_third_party_config_update | 登录 |

## 定时任务

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `GET` | `/api/scheduled-tasks/cron/preview/` | scheduled_tasks_cron_preview_retrieve | 登录 |
| `GET` | `/api/scheduled-tasks/logs/` | scheduled_tasks_logs_list | 登录 |
| `GET` | `/api/scheduled-tasks/logs/{id}/` | scheduled_tasks_logs_retrieve | 登录 |
| `GET` | `/api/scheduled-tasks/tasks/` | scheduled_tasks_tasks_list | 登录 |
| `POST` | `/api/scheduled-tasks/tasks/` | scheduled_tasks_tasks_create | 登录 |
| `DELETE` | `/api/scheduled-tasks/tasks/{id}/` | scheduled_tasks_tasks_destroy | 登录 |
| `GET` | `/api/scheduled-tasks/tasks/{id}/` | scheduled_tasks_tasks_retrieve | 登录 |
| `PATCH` | `/api/scheduled-tasks/tasks/{id}/` | scheduled_tasks_tasks_partial_update | 登录 |
| `PUT` | `/api/scheduled-tasks/tasks/{id}/` | scheduled_tasks_tasks_update | 登录 |
| `GET` | `/api/scheduled-tasks/tasks/{id}/logs/` | scheduled_tasks_tasks_logs_retrieve | 登录 |
| `POST` | `/api/scheduled-tasks/tasks/{id}/run/` | scheduled_tasks_tasks_run_create | 登录 |
| `POST` | `/api/scheduled-tasks/tasks/{id}/toggle/` | scheduled_tasks_tasks_toggle_create | 登录 |

## 用户目录

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `GET` | `/api/users/` | users_list | 登录 |
| `GET` | `/api/users/brief/` | users_brief_retrieve | 登录 |
| `POST` | `/api/users/create_user/` | users_create_user_create | 登录 |
| `GET` | `/api/users/{id}/` | users_retrieve | 登录 |

## Web UI 测试

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `GET` | `/api/web-testing/cases/` | web_testing_cases_list | 登录 |
| `POST` | `/api/web-testing/cases/` | web_testing_cases_create | 登录 |
| `DELETE` | `/api/web-testing/cases/{id}/` | web_testing_cases_destroy | 登录 |
| `GET` | `/api/web-testing/cases/{id}/` | web_testing_cases_retrieve | 登录 |
| `PATCH` | `/api/web-testing/cases/{id}/` | web_testing_cases_partial_update | 登录 |
| `PUT` | `/api/web-testing/cases/{id}/` | web_testing_cases_update | 登录 |
| `POST` | `/api/web-testing/cases/{id}/generate_from_nl/` | web_testing_cases_generate_from_nl_create | 登录 |
| `POST` | `/api/web-testing/cases/{id}/generate_script/` | web_testing_cases_generate_script_create | 登录 |
| `POST` | `/api/web-testing/cases/{id}/run/` | web_testing_cases_run_create | 登录 |
| `GET` | `/api/web-testing/elements/` | web_testing_elements_list | 登录 |
| `POST` | `/api/web-testing/elements/` | web_testing_elements_create | 登录 |
| `POST` | `/api/web-testing/elements/bulk/` | web_testing_elements_bulk_create | 登录 |
| `DELETE` | `/api/web-testing/elements/{id}/` | web_testing_elements_destroy | 登录 |
| `GET` | `/api/web-testing/elements/{id}/` | web_testing_elements_retrieve | 登录 |
| `PATCH` | `/api/web-testing/elements/{id}/` | web_testing_elements_partial_update | 登录 |
| `PUT` | `/api/web-testing/elements/{id}/` | web_testing_elements_update | 登录 |
| `GET` | `/api/web-testing/executions/` | web_testing_executions_list | 登录 |
| `GET` | `/api/web-testing/executions/{id}/` | web_testing_executions_retrieve | 登录 |
| `POST` | `/api/web-testing/executions/{id}/cancel/` | web_testing_executions_cancel_create | 登录 |
| `GET` | `/api/web-testing/executions/{id}/report/` | web_testing_executions_report_retrieve | 登录 |
| `GET` | `/api/web-testing/midscene-scripts/` | web_testing_midscene_scripts_list | 登录 |
| `POST` | `/api/web-testing/midscene-scripts/` | web_testing_midscene_scripts_create | 登录 |
| `DELETE` | `/api/web-testing/midscene-scripts/{id}/` | web_testing_midscene_scripts_destroy | 登录 |
| `GET` | `/api/web-testing/midscene-scripts/{id}/` | web_testing_midscene_scripts_retrieve | 登录 |
| `PATCH` | `/api/web-testing/midscene-scripts/{id}/` | web_testing_midscene_scripts_partial_update | 登录 |
| `PUT` | `/api/web-testing/midscene-scripts/{id}/` | web_testing_midscene_scripts_update | 登录 |
| `POST` | `/api/web-testing/midscene-scripts/{id}/generate/` | web_testing_midscene_scripts_generate_create | 登录 |
| `GET` | `/api/web-testing/modules/` | web_testing_modules_list | 登录 |
| `POST` | `/api/web-testing/modules/` | web_testing_modules_create | 登录 |
| `GET` | `/api/web-testing/modules/tree/` | web_testing_modules_tree_retrieve | 登录 |
| `DELETE` | `/api/web-testing/modules/{id}/` | web_testing_modules_destroy | 登录 |
| `GET` | `/api/web-testing/modules/{id}/` | web_testing_modules_retrieve | 登录 |
| `PATCH` | `/api/web-testing/modules/{id}/` | web_testing_modules_partial_update | 登录 |
| `PUT` | `/api/web-testing/modules/{id}/` | web_testing_modules_update | 登录 |
| `GET` | `/api/web-testing/pages/` | web_testing_pages_list | 登录 |
| `POST` | `/api/web-testing/pages/` | web_testing_pages_create | 登录 |
| `DELETE` | `/api/web-testing/pages/{id}/` | web_testing_pages_destroy | 登录 |
| `GET` | `/api/web-testing/pages/{id}/` | web_testing_pages_retrieve | 登录 |
| `PATCH` | `/api/web-testing/pages/{id}/` | web_testing_pages_partial_update | 登录 |
| `PUT` | `/api/web-testing/pages/{id}/` | web_testing_pages_update | 登录 |
| `GET` | `/api/web-testing/pages/{id}/elements/` | web_testing_pages_elements_retrieve | 登录 |
| `GET` | `/api/web-testing/suites/` | web_testing_suites_list | 登录 |
| `POST` | `/api/web-testing/suites/` | web_testing_suites_create | 登录 |
| `DELETE` | `/api/web-testing/suites/{id}/` | web_testing_suites_destroy | 登录 |
| `GET` | `/api/web-testing/suites/{id}/` | web_testing_suites_retrieve | 登录 |
| `PATCH` | `/api/web-testing/suites/{id}/` | web_testing_suites_partial_update | 登录 |
| `PUT` | `/api/web-testing/suites/{id}/` | web_testing_suites_update | 登录 |
| `POST` | `/api/web-testing/suites/{id}/run/` | web_testing_suites_run_create | 登录 |

## WebSocket 通道

| 路径 | 用途 |
|---|---|
| `ws/task-status/<task_id>/?token=<jwt>` | 通用任务状态推送（执行进度） |
| `ws/scenario_generation-streaming/?token=<jwt>` | API 场景 Agent 流式输出 |
| `ws/midscene_script_generation-streaming/?token=<jwt>` | MidScene 脚本生成流 |
| `ws/webui_test_generation-streaming/?token=<jwt>` | WebUI 用例生成流 |
| `ws/webui_auto_test-streaming/?token=<jwt>` | WebUI 自动化执行流 |

鉴权失败返回 `{"type":"error","code":"unauthorized"}` 并断开（code 4001）。
