/**
 * 性能测试 / 监控大盘模块内部纯逻辑工具。
 *
 * 该文件不依赖 Vue / Element Plus / axios，只做枚举映射、指标格式化、
 * 表单校验与 dashboard 数据转换，方便在 `tests/unit/performance.spec.js`
 * 中直接做单元测试。视图组件负责渲染，工具函数负责“可验证的规则”。
 */

import { EMPTY_TEXT, formatNumber } from '@/utils/format'

// ---------------------------------------------------------------------------
// 通用小工具
// ---------------------------------------------------------------------------
function toNumber(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function toInteger(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? Math.trunc(number) : fallback
}

function toText(value) {
  return value === null || value === undefined ? '' : String(value)
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

/** 正整数（或数字字符串）→ 数字；非法/<=0 返回 null。 */
function toPositiveInt(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  if (!Number.isFinite(number) || !Number.isInteger(number) || number <= 0) return null
  return number
}

/**
 * 从 axios / 普通 Error 中提取一条可读错误信息。
 * 优先读取后端统一错误体的 `message`，其次 `detail`，最后兜底。
 */
export function readErrorMessage(error, fallback = '操作失败，请稍后重试') {
  const data = error?.response?.data
  if (typeof data === 'string' && data.trim()) return data
  if (data && typeof data === 'object') {
    if (typeof data.message === 'string' && data.message.trim()) return data.message
    if (typeof data.detail === 'string' && data.detail.trim()) return data.detail
  }
  if (typeof error?.message === 'string' && error.message.trim()) return error.message
  return fallback
}

// ---------------------------------------------------------------------------
// 执行状态
// ---------------------------------------------------------------------------
export const EXECUTION_STATUS_META = {
  pending: { label: '等待中', tagType: 'info' },
  running: { label: '执行中', tagType: 'warning' },
  passed: { label: '通过', tagType: 'success' },
  failed: { label: '失败', tagType: 'danger' },
  error: { label: '错误', tagType: 'danger' },
  cancelled: { label: '已取消', tagType: 'info' },
}

export const EXECUTION_TERMINAL_STATUSES = ['passed', 'failed', 'error', 'cancelled']

export const EXECUTION_STATUS_OPTIONS = Object.entries(EXECUTION_STATUS_META).map(
  ([value, meta]) => ({ value, label: meta.label }),
)

export function isExecutionTerminal(status) {
  return EXECUTION_TERMINAL_STATUSES.includes(toText(status).trim().toLowerCase())
}

/** 状态元信息：未知状态保留原文作为文案，永不抛错。 */
export function getExecutionStatusMeta(status) {
  const key = toText(status).trim().toLowerCase()
  const meta = EXECUTION_STATUS_META[key]
  return {
    status: key,
    label: meta ? meta.label : key || '未知',
    tagType: meta ? meta.tagType : 'info',
    terminal: isExecutionTerminal(key),
  }
}

export function getExecutionStatusLabel(status, fallback = '未知') {
  const meta = getExecutionStatusMeta(status)
  return meta.status ? meta.label : fallback
}

export function getExecutionStatusTagType(status) {
  return getExecutionStatusMeta(status).tagType
}

/** 归一化进度：任意输入 → 0..100 整数。 */
export function clampProgress(value) {
  return clamp(Math.round(toNumber(value, 0)), 0, 100)
}

/** 根据执行记录估算进度（终态 100，执行中给一个保守的中间值）。 */
export function progressFromExecution(execution) {
  if (!isPlainObject(execution)) return 0
  if (isExecutionTerminal(execution.status)) return 100
  if (execution.status === 'running') return 55
  if (execution.status === 'pending') return 5
  return 0
}

// ---------------------------------------------------------------------------
// 触发方式 / 场景来源 / 诊断枚举
// ---------------------------------------------------------------------------
export const TRIGGER_TYPE_META = {
  manual: { label: '手动', tagType: 'primary' },
  scheduled: { label: '定时', tagType: 'warning' },
  api: { label: 'API 调用', tagType: 'info' },
}

export const TRIGGER_TYPE_OPTIONS = Object.entries(TRIGGER_TYPE_META).map(([value, meta]) => ({
  value,
  label: meta.label,
}))

export function getTriggerTypeMeta(triggerType) {
  const key = toText(triggerType).trim().toLowerCase()
  const meta = TRIGGER_TYPE_META[key]
  return meta ? { key, ...meta } : { key, label: key || EMPTY_TEXT, tagType: 'info' }
}

export const SCENARIO_SOURCE_META = {
  api_suite: { label: 'API 套件', tagType: 'primary' },
  api_case: { label: 'API 用例', tagType: 'success' },
  custom_script: { label: '自定义脚本', tagType: 'warning' },
}

export const SCENARIO_SOURCE_OPTIONS = Object.entries(SCENARIO_SOURCE_META).map(
  ([value, meta]) => ({ value, label: meta.label }),
)

export function getScenarioSourceMeta(sourceType) {
  const key = toText(sourceType).trim().toLowerCase()
  const meta = SCENARIO_SOURCE_META[key]
  return meta ? { key, ...meta } : { key, label: key || EMPTY_TEXT, tagType: 'info' }
}

export const DIAGNOSIS_SOURCE_META = {
  grafana: { label: 'Grafana 告警', tagType: 'warning' },
  manual: { label: '手动诊断', tagType: 'primary' },
}

export const DIAGNOSIS_SOURCE_OPTIONS = Object.entries(DIAGNOSIS_SOURCE_META).map(
  ([value, meta]) => ({ value, label: meta.label }),
)

export function getDiagnosisSourceMeta(source) {
  const key = toText(source).trim().toLowerCase()
  const meta = DIAGNOSIS_SOURCE_META[key]
  return meta ? { key, ...meta } : { key, label: key || EMPTY_TEXT, tagType: 'info' }
}

export const DIAGNOSIS_STATUS_META = {
  pending: { label: '待处理', tagType: 'warning' },
  resolved: { label: '已解决', tagType: 'success' },
  ignored: { label: '已忽略', tagType: 'info' },
}

export const DIAGNOSIS_STATUS_OPTIONS = Object.entries(DIAGNOSIS_STATUS_META).map(
  ([value, meta]) => ({ value, label: meta.label }),
)

export function getDiagnosisStatusMeta(status) {
  const key = toText(status).trim().toLowerCase()
  const meta = DIAGNOSIS_STATUS_META[key]
  return meta ? { key, ...meta } : { key, label: key || '未知', tagType: 'info' }
}

/**
 * Grafana / 规则诊断的严重级别（后端 severity 为自由文本）。
 * 兼容 critical / warning / info、中文与 Grafana 常见别名。
 */
export const SEVERITY_META = {
  critical: { label: '严重', tagType: 'danger', color: '#dc2626', level: 4 },
  crit: { label: '严重', tagType: 'danger', color: '#dc2626', level: 4 },
  fatal: { label: '致命', tagType: 'danger', color: '#b91c1c', level: 5 },
  blocker: { label: '阻断', tagType: 'danger', color: '#b91c1c', level: 5 },
  high: { label: '高', tagType: 'danger', color: '#dc2626', level: 4 },
  error: { label: '错误', tagType: 'danger', color: '#dc2626', level: 4 },
  major: { label: '重要', tagType: 'danger', color: '#ea580c', level: 4 },
  严重: { label: '严重', tagType: 'danger', color: '#dc2626', level: 4 },
  warning: { label: '警告', tagType: 'warning', color: '#d97706', level: 3 },
  warn: { label: '警告', tagType: 'warning', color: '#d97706', level: 3 },
  medium: { label: '中', tagType: 'warning', color: '#d97706', level: 3 },
  警告: { label: '警告', tagType: 'warning', color: '#d97706', level: 3 },
  info: { label: '提示', tagType: 'info', color: '#2563eb', level: 2 },
  informational: { label: '提示', tagType: 'info', color: '#2563eb', level: 2 },
  low: { label: '低', tagType: 'info', color: '#0d9488', level: 2 },
  minor: { label: '低', tagType: 'info', color: '#0d9488', level: 2 },
  debug: { label: '调试', tagType: 'info', color: '#64748b', level: 1 },
  提示: { label: '提示', tagType: 'info', color: '#2563eb', level: 2 },
}

const UNKNOWN_SEVERITY_META = { label: '未分级', tagType: 'info', color: '#94a3b8', level: 0 }

export function getSeverityMeta(severity) {
  const raw = toText(severity).trim()
  const key = raw.toLowerCase()
  if (!key) return { key: '', ...UNKNOWN_SEVERITY_META }
  const meta = SEVERITY_META[key]
  if (meta) return { key, ...meta }
  return { key, label: raw, tagType: 'info', color: '#94a3b8', level: 1 }
}

// ---------------------------------------------------------------------------
// 指标格式化（TPS / 延迟 / 错误率 / 成功率）
// ---------------------------------------------------------------------------
/** TPS：保留 2 位小数，非法值按 0 展示。 */
export function formatTps(value) {
  return formatNumber(toNumber(value), 2)
}

/** 延迟（毫秒）：四舍五入 + 千分位；负数/非法值按 0 展示。 */
export function formatLatency(value) {
  const number = Math.max(0, toNumber(value))
  return `${Math.round(number).toLocaleString('zh-CN')} ms`
}

/** 错误率归一化：后端返回 0..1 的小数，超出边界时收敛到 [0, 1]。 */
export function normalizeErrorRate(value) {
  return clamp(toNumber(value), 0, 1)
}

/** 错误率 → 百分数数值（0..100）。 */
export function errorRatePercent(value) {
  return Number((normalizeErrorRate(value) * 100).toFixed(2))
}

/** 错误率 → 百分比文案（0.0021 → 0.21%）。 */
export function formatErrorRate(value, digits = 2) {
  return `${(normalizeErrorRate(value) * 100).toFixed(digits)}%`
}

/** 成功率 → 百分数数值（0..100），由错误率推导。 */
export function successRatePercent(errorRate) {
  return Number((100 - errorRatePercent(errorRate)).toFixed(2))
}

/** 成功率 → 百分比文案（0.0021 → 99.79%）。 */
export function formatSuccessRate(errorRate, digits = 2) {
  return `${successRatePercent(errorRate).toFixed(digits)}%`
}

/** 耗时（毫秒）→ 可读文案（复用统一格式，空值显示 —）。 */
export function formatDurationText(value) {
  if (value === null || value === undefined || value === '') return EMPTY_TEXT
  const number = toNumber(value)
  if (number < 0) return EMPTY_TEXT
  if (number < 1000) return `${Math.round(number)} ms`
  const seconds = number / 1000
  if (seconds < 60) return `${seconds.toFixed(2)} s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes} min ${Math.round(seconds % 60)} s`
}

// ---------------------------------------------------------------------------
// JSON / URL 校验
// ---------------------------------------------------------------------------
export function isBlankText(value) {
  return toText(value).trim() === ''
}

export function isValidHttpUrl(value) {
  return /^https?:\/\/[^\s]+$/i.test(toText(value).trim())
}

/**
 * 校验 JSON 对象文本（数组 / 标量视为非法）。
 * 返回 { valid, value, empty, message }，不抛异常。
 */
export function validateJsonObject(text, { allowEmpty = true, label = 'JSON' } = {}) {
  const raw = toText(text)
  if (!raw.trim()) {
    return allowEmpty
      ? { valid: true, value: {}, empty: true, message: '' }
      : { valid: false, value: undefined, empty: true, message: `${label}不能为空` }
  }
  let value
  try {
    value = JSON.parse(raw)
  } catch (error) {
    return {
      valid: false,
      value: undefined,
      empty: false,
      message: `${label}不是合法 JSON：${error?.message || '解析失败'}`,
    }
  }
  if (!isPlainObject(value)) {
    return {
      valid: false,
      value,
      empty: false,
      message: `${label}必须是 JSON 对象（不能是数组或标量）`,
    }
  }
  return { valid: true, value, empty: false, message: '' }
}

/** 格式化 JSON 文本；失败时返回原文与错误信息。 */
export function formatJsonText(text) {
  const raw = toText(text)
  if (!raw.trim()) return { ok: true, text: '', message: '' }
  try {
    return { ok: true, text: JSON.stringify(JSON.parse(raw), null, 2), message: '' }
  } catch (error) {
    return { ok: false, text: raw, message: `JSON 格式不合法：${error?.message || '解析失败'}` }
  }
}

// ---------------------------------------------------------------------------
// 负载配置表单
// ---------------------------------------------------------------------------
/** 编辑行 → 表单模型。 */
export function loadConfigToForm(row = {}) {
  const source = isPlainObject(row) ? row : {}
  return {
    name: toText(source.name),
    users: toNumber(source.users, 10),
    spawn_rate: toNumber(source.spawn_rate, 5),
    duration_seconds: toNumber(source.duration_seconds, 60),
    host: toText(source.host),
    configText:
      isPlainObject(source.config) && Object.keys(source.config).length
        ? JSON.stringify(source.config, null, 2)
        : '{}',
    description: toText(source.description),
  }
}

/** 表单模型 → 后端请求体。 */
export function buildLoadConfigPayload(form = {}) {
  const config = validateJsonObject(form.configText, { label: '扩展配置' })
  return {
    name: toText(form.name).trim(),
    users: toInteger(form.users, 0),
    spawn_rate: toNumber(form.spawn_rate, 0),
    duration_seconds: toInteger(form.duration_seconds, 0),
    host: toText(form.host).trim(),
    config: config.valid ? config.value : {},
    description: toText(form.description).trim(),
  }
}

/** 校验负载配置表单；返回 { valid, errors, fieldErrors, payload }。 */
export function validateLoadConfig(form = {}) {
  const fieldErrors = {
    name: '',
    users: '',
    spawn_rate: '',
    duration_seconds: '',
    host: '',
    configText: '',
  }
  const errors = []
  const setError = (field, message) => {
    if (!fieldErrors[field]) fieldErrors[field] = message
    errors.push(message)
  }

  const name = toText(form.name).trim()
  if (!name) setError('name', '配置名称不能为空')

  const users = Number(form.users)
  if (!Number.isFinite(users) || !Number.isInteger(users) || users <= 0) {
    setError('users', '并发用户数必须为正整数')
  }

  const spawnRate = Number(form.spawn_rate)
  if (!Number.isFinite(spawnRate) || spawnRate <= 0) {
    setError('spawn_rate', '并发增长率必须大于 0')
  }

  const duration = Number(form.duration_seconds)
  if (!Number.isFinite(duration) || !Number.isInteger(duration) || duration <= 0) {
    setError('duration_seconds', '持续时间必须为正整数（秒）')
  }

  const host = toText(form.host).trim()
  if (host && !isValidHttpUrl(host)) {
    setError('host', '目标 Host 必须是 http(s):// 开头的完整地址')
  }

  const config = validateJsonObject(form.configText, { label: '扩展配置' })
  if (!config.valid) setError('configText', config.message)

  return {
    valid: errors.length === 0,
    errors,
    fieldErrors,
    payload: errors.length === 0 ? buildLoadConfigPayload(form) : null,
  }
}

// ---------------------------------------------------------------------------
// 性能场景表单
// ---------------------------------------------------------------------------
export const SCENARIO_SOURCE_TYPES = ['api_suite', 'api_case', 'custom_script']

/** 自定义 locustfile 校验：非空且包含 HttpUser。 */
export function validateCustomScript(source) {
  const raw = toText(source).trim()
  if (!raw) {
    return { valid: false, hasHttpUser: false, message: '自定义脚本不能为空' }
  }
  const hasHttpUser = /HttpUser/.test(raw)
  if (!hasHttpUser) {
    return {
      valid: false,
      hasHttpUser: false,
      message: 'Locust 脚本必须包含 HttpUser 用户类（from locust import HttpUser）',
    }
  }
  return { valid: true, hasHttpUser: true, message: '' }
}

/** 场景编辑行 → 表单模型。 */
export function scenarioToForm(row = {}) {
  const source = isPlainObject(row) ? row : {}
  return {
    name: toText(source.name),
    description: toText(source.description),
    source_type: toText(source.source_type) || 'api_suite',
    source_suite: source.source_suite ?? null,
    source_case: source.source_case ?? null,
    custom_script: toText(source.custom_script),
    endpoint_count: toNumber(source.endpoint_count, 0),
    config: source.config ?? null,
    variablesText:
      isPlainObject(source.variables) && Object.keys(source.variables).length
        ? JSON.stringify(source.variables, null, 2)
        : '{}',
    is_active: source.is_active !== false,
  }
}

/** 表单模型 → 后端请求体。 */
export function buildScenarioPayload(form = {}) {
  const sourceType = toText(form.source_type) || 'api_suite'
  const variables = validateJsonObject(form.variablesText, { label: '变量' })
  return {
    name: toText(form.name).trim(),
    description: toText(form.description).trim(),
    source_type: sourceType,
    source_suite: sourceType === 'api_suite' ? toPositiveInt(form.source_suite) : null,
    source_case: sourceType === 'api_case' ? toPositiveInt(form.source_case) : null,
    custom_script: sourceType === 'custom_script' ? toText(form.custom_script) : '',
    endpoint_count: Math.max(0, toInteger(form.endpoint_count, 0)),
    config: toPositiveInt(form.config),
    variables: variables.valid ? variables.value : {},
    is_active: form.is_active !== false,
  }
}

/** 校验场景表单；返回 { valid, errors, fieldErrors, payload }。 */
export function validateScenarioForm(form = {}) {
  const fieldErrors = {
    name: '',
    source_type: '',
    source_suite: '',
    source_case: '',
    custom_script: '',
    variablesText: '',
    endpoint_count: '',
    config: '',
  }
  const errors = []
  const setError = (field, message) => {
    if (!fieldErrors[field]) fieldErrors[field] = message
    errors.push(message)
  }

  const name = toText(form.name).trim()
  if (!name) setError('name', '场景名称不能为空')

  const sourceType = toText(form.source_type)
  if (!SCENARIO_SOURCE_TYPES.includes(sourceType)) {
    setError('source_type', '请选择有效的场景来源类型')
  } else if (sourceType === 'api_suite') {
    if (!toPositiveInt(form.source_suite)) setError('source_suite', '请选择来源 API 套件')
  } else if (sourceType === 'api_case') {
    if (!toPositiveInt(form.source_case)) setError('source_case', '请选择来源 API 用例')
  } else {
    const script = validateCustomScript(form.custom_script)
    if (!script.valid) setError('custom_script', script.message)
  }

  const variables = validateJsonObject(form.variablesText, { label: '变量' })
  if (!variables.valid) setError('variablesText', variables.message)

  const endpointCount = form.endpoint_count
  if (endpointCount !== null && endpointCount !== undefined && endpointCount !== '') {
    const number = Number(endpointCount)
    if (!Number.isFinite(number) || !Number.isInteger(number) || number < 0) {
      setError('endpoint_count', '接口数量必须为非负整数')
    }
  }

  if (form.config !== null && form.config !== undefined && form.config !== '') {
    if (!toPositiveInt(form.config)) setError('config', '负载配置不符合要求')
  }

  return {
    valid: errors.length === 0,
    errors,
    fieldErrors,
    payload: errors.length === 0 ? buildScenarioPayload(form) : null,
  }
}

/** 场景来源展示文案（套件/用例来自关联 API 项目时带项目名）。 */
export function describeScenarioSource(row = {}) {
  const source = isPlainObject(row) ? row : {}
  const sourceType = toText(source.source_type)
  if (sourceType === 'api_suite') {
    return toText(source.source_suite_name) || (source.source_suite ? `套件 #${source.source_suite}` : EMPTY_TEXT)
  }
  if (sourceType === 'api_case') {
    return toText(source.source_case_name) || (source.source_case ? `用例 #${source.source_case}` : EMPTY_TEXT)
  }
  if (sourceType === 'custom_script') {
    const script = toText(source.custom_script)
    return script ? '自定义 Locust 脚本' : EMPTY_TEXT
  }
  return EMPTY_TEXT
}

/** 生成脚本下载文件名（去掉文件系统非法字符）。 */
export function buildScriptFilename(scenario = {}) {
  const raw = toText(scenario.name || 'scenario').trim()
  const safe =
    raw
      .replace(/[\\/:*?"<>|\s]+/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '') || 'scenario'
  return `locustfile-${safe}.py`
}

/** 执行报告下载文件名。 */
export function buildReportFilename(execution = {}) {
  const id = execution && (execution.id ?? execution.execution_id)
  return `performance-report-${id || 'unknown'}.json`
}

// ---------------------------------------------------------------------------
// 执行数据转换
// ---------------------------------------------------------------------------
/** 单条执行记录（snake_case）→ 表格行模型。 */
export function normalizeExecutionRow(row = {}) {
  const source = isPlainObject(row) ? row : {}
  const statusMeta = getExecutionStatusMeta(source.status)
  const triggerMeta = getTriggerTypeMeta(source.trigger_type)
  return {
    id: source.id,
    name: toText(source.name) || '未命名执行',
    projectId: source.project ?? null,
    projectName: toText(source.project_name),
    scenarioId: source.scenario ?? source.scenario_id ?? null,
    scenarioName: toText(source.scenario_name) || EMPTY_TEXT,
    configName: toText(source.config_name),
    status: statusMeta.status,
    statusLabel: statusMeta.label,
    statusTagType: statusMeta.tagType,
    terminal: statusMeta.terminal,
    triggerType: triggerMeta.key,
    triggerLabel: triggerMeta.label,
    triggerTagType: triggerMeta.tagType,
    avgTps: toNumber(source.avg_tps),
    p50: toNumber(source.p50_response_time),
    p95: toNumber(source.p95_response_time),
    p99: toNumber(source.p99_response_time),
    errorRate: normalizeErrorRate(source.error_rate),
    totalRequests: toNumber(source.total_requests),
    durationMs: toNumber(source.duration_ms),
    statusCodeDist: isPlainObject(source.status_code_dist) ? source.status_code_dist : {},
    errorMessage: toText(source.error_message),
    startedAt: toText(source.started_at || source.created_at),
    createdAt: toText(source.created_at),
    summary: isPlainObject(source.summary) ? source.summary : {},
  }
}

/** 状态码分布 → 按状态码升序的表格行（含占比）。 */
export function normalizeStatusCodeDist(dist, totalRequests = 0) {
  if (!isPlainObject(dist)) return []
  const rows = Object.entries(dist)
    .map(([code, count]) => ({ code: toText(code), count: toNumber(count) }))
    .filter((row) => row.code !== '')
    .sort((left, right) => {
      const leftNumber = Number(left.code)
      const rightNumber = Number(right.code)
      if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
        return leftNumber - rightNumber
      }
      return left.code.localeCompare(right.code)
    })
  const sum = toNumber(totalRequests) > 0 ? toNumber(totalRequests) : rows.reduce((acc, row) => acc + row.count, 0)
  return rows.map((row) => ({
    ...row,
    percent: sum > 0 ? Number(((row.count / sum) * 100).toFixed(2)) : 0,
  }))
}

// ---------------------------------------------------------------------------
// Dashboard（/api/performance/dashboard/）数据转换
// ---------------------------------------------------------------------------
const EMPTY_SUMMARY = () => ({
  executions: 0,
  passed: 0,
  failed: 0,
  error: 0,
  cancelled: 0,
  running: 0,
  pending: 0,
  failedTotal: 0,
  avgTps: 0,
  avgP95: 0,
  avgP99: 0,
  avgErrorRate: 0,
  totalRequests: 0,
})

const EMPTY_DIAGNOSIS = () => ({
  total: 0,
  pending: 0,
  resolved: 0,
  ignored: 0,
  bySeverity: {},
})

function normalizeSeverityCounts(value) {
  if (!isPlainObject(value)) return {}
  return Object.entries(value).reduce((acc, [key, count]) => {
    const name = toText(key).trim()
    if (name) acc[name] = toNumber(count)
    return acc
  }, {})
}

/**
 * dashboard 响应 → 视图模型。
 *
 * 兼容字段缺失 / 类型异常；`trend[].passed` 后端口径暂未填充（恒为 0），
 * 这里用 `executions - failed` 推导通过数，保证堆叠折线可用。
 */
export function normalizeDashboard(payload = {}) {
  const source = isPlainObject(payload) ? payload : {}
  const rawSummary = isPlainObject(source.summary) ? source.summary : {}
  const failed = toNumber(rawSummary.failed)
  const error = toNumber(rawSummary.error)
  const summary = {
    ...EMPTY_SUMMARY(),
    executions: toNumber(rawSummary.executions),
    passed: toNumber(rawSummary.passed),
    failed,
    error,
    cancelled: toNumber(rawSummary.cancelled),
    running: toNumber(rawSummary.running),
    pending: toNumber(rawSummary.pending),
    failedTotal: failed + error,
    avgTps: toNumber(rawSummary.avg_tps),
    avgP95: toNumber(rawSummary.avg_p95),
    avgP99: toNumber(rawSummary.avg_p99),
    avgErrorRate: normalizeErrorRate(rawSummary.avg_error_rate),
    totalRequests: toNumber(rawSummary.total_requests),
  }

  const trend = Array.isArray(source.trend)
    ? source.trend.filter(isPlainObject).map((row) => {
        const executions = toNumber(row.executions)
        const rowFailed = toNumber(row.failed)
        const reportedPassed = toNumber(row.passed)
        return {
          date: toText(row.date),
          executions,
          passed: reportedPassed > 0 ? reportedPassed : Math.max(executions - rowFailed, 0),
          failed: rowFailed,
          avgTps: toNumber(row.avg_tps),
          avgP95: toNumber(row.avg_p95),
          avgErrorRate: normalizeErrorRate(row.avg_error_rate),
        }
      })
    : []

  const recentExecutions = Array.isArray(source.recent_executions)
    ? source.recent_executions.filter(isPlainObject).map(normalizeExecutionRow)
    : []

  const rawDiagnosis = isPlainObject(source.diagnosis) ? source.diagnosis : {}
  const diagnosis = {
    ...EMPTY_DIAGNOSIS(),
    total: toNumber(rawDiagnosis.total),
    pending: toNumber(rawDiagnosis.pending),
    resolved: toNumber(rawDiagnosis.resolved),
    ignored: toNumber(rawDiagnosis.ignored),
    bySeverity: normalizeSeverityCounts(rawDiagnosis.by_severity),
  }

  const range = isPlainObject(source.range) ? source.range : {}

  return {
    days: Math.max(1, toInteger(source.days, 7)),
    range: { start: toText(range.start), end: toText(range.end) },
    summary,
    trend,
    recentExecutions,
    diagnosis,
    hasData: summary.executions > 0 || recentExecutions.length > 0,
  }
}

export default {
  normalizeDashboard,
  normalizeExecutionRow,
  validateLoadConfig,
  validateScenarioForm,
}
