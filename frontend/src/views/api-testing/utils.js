/**
 * API 测试模块内部纯逻辑工具。
 *
 * 该文件不依赖 Vue / Element Plus / axios，只做枚举映射、JSON 校验、
 * 请求配置构建与执行报告格式化，方便在 `tests/unit/api-testing.spec.js`
 * 中直接做单元测试。视图组件负责渲染，工具函数负责“可验证的规则”。
 */

import { EMPTY_TEXT, formatDuration, formatPercent } from '@/utils/format'

// ---------------------------------------------------------------------------
// 通用小工具
// ---------------------------------------------------------------------------
function toNumber(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function toText(value) {
  return value === null || value === undefined ? '' : String(value)
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

// ---------------------------------------------------------------------------
// HTTP method：标签文案 / el-tag 颜色 / 方法主色
// ---------------------------------------------------------------------------
export const HTTP_METHODS = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace']

export const METHOD_META = {
  get: { label: 'GET', tagType: 'success', color: '#16a34a' },
  post: { label: 'POST', tagType: 'primary', color: '#2563eb' },
  put: { label: 'PUT', tagType: 'warning', color: '#d97706' },
  patch: { label: 'PATCH', tagType: 'warning', color: '#ea580c' },
  delete: { label: 'DELETE', tagType: 'danger', color: '#dc2626' },
  head: { label: 'HEAD', tagType: 'info', color: '#0d9488' },
  options: { label: 'OPTIONS', tagType: 'info', color: '#64748b' },
  trace: { label: 'TRACE', tagType: 'info', color: '#7c3aed' },
}

const UNKNOWN_METHOD_META = { label: '', tagType: 'info', color: '#94a3b8' }

/** 返回 method 的展示元信息（大小写不敏感，未知方法兜底 info）。 */
export function getMethodMeta(method) {
  const key = toText(method).trim().toLowerCase()
  const meta = METHOD_META[key]
  if (meta) return { key, ...meta }
  return { key, ...UNKNOWN_METHOD_META, label: key ? key.toUpperCase() : EMPTY_TEXT }
}

export function getMethodTagType(method) {
  return getMethodMeta(method).tagType
}

export function getMethodColor(method) {
  return getMethodMeta(method).color
}

export function getMethodLabel(method) {
  return getMethodMeta(method).label
}

// ---------------------------------------------------------------------------
// 执行状态：文案 / 标签类型 / 终态判断 / 进度
// ---------------------------------------------------------------------------
export const EXECUTION_STATUS_META = {
  pending: { label: '等待中', tagType: 'info' },
  running: { label: '执行中', tagType: 'warning' },
  passed: { label: '通过', tagType: 'success' },
  failed: { label: '失败', tagType: 'danger' },
  error: { label: '错误', tagType: 'danger' },
  cancelled: { label: '已取消', tagType: 'info' },
  skipped: { label: '跳过', tagType: 'info' },
}

export const EXECUTION_TERMINAL_STATUSES = ['passed', 'failed', 'error', 'cancelled']

export const EXECUTION_STATUS_OPTIONS = ['pending', 'running', 'passed', 'failed', 'error', 'cancelled'].map(
  (value) => ({ value, label: EXECUTION_STATUS_META[value].label }),
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
  const number = toNumber(value, 0)
  return Math.min(100, Math.max(0, Math.round(number)))
}

/** 根据执行记录的计数估算进度（终态 100，执行中最高 99，避免假完成）。 */
export function progressFromExecution(execution) {
  if (!execution || typeof execution !== 'object') return 0
  if (isExecutionTerminal(execution.status)) return 100
  const total = toNumber(execution.total)
  const finished =
    toNumber(execution.passed) + toNumber(execution.failed) + toNumber(execution.skipped)
  if (total <= 0) return execution.status === 'running' ? 10 : 0
  return Math.min(99, Math.max(1, Math.round((finished / total) * 100)))
}

/** 执行触发方式文案。 */
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
  return meta
    ? { key, ...meta }
    : { key, label: key || EMPTY_TEXT, tagType: 'info' }
}

// ---------------------------------------------------------------------------
// 接口规范
// ---------------------------------------------------------------------------
export const SPEC_SOURCE_OPTIONS = [
  { value: 'openapi', label: 'OpenAPI 3' },
  { value: 'swagger', label: 'Swagger 2' },
  { value: 'postman', label: 'Postman Collection' },
]

export const SPEC_STATUS_META = {
  pending: { label: '待解析', tagType: 'info' },
  parsed: { label: '已解析', tagType: 'success' },
  failed: { label: '解析失败', tagType: 'danger' },
}

export function getSpecSourceLabel(sourceType) {
  const found = SPEC_SOURCE_OPTIONS.find((item) => item.value === sourceType)
  return found ? found.label : toText(sourceType) || EMPTY_TEXT
}

export function getSpecStatusMeta(status) {
  const key = toText(status).trim().toLowerCase()
  const meta = SPEC_STATUS_META[key]
  return meta
    ? { status: key, ...meta }
    : { status: key, label: key || '未知', tagType: 'info' }
}

// ---------------------------------------------------------------------------
// 用例枚举
// ---------------------------------------------------------------------------
export const CASE_TYPE_OPTIONS = [
  { value: 'endpoint', label: '单接口' },
  { value: 'scenario', label: '场景' },
]

export const TEST_TYPE_META = {
  positive: { label: '正向', tagType: 'success' },
  negative: { label: '异常', tagType: 'danger' },
  boundary: { label: '边界', tagType: 'warning' },
  security: { label: '安全', tagType: 'info' },
  performance: { label: '性能', tagType: 'warning' },
}

export const TEST_TYPE_OPTIONS = Object.entries(TEST_TYPE_META).map(([value, meta]) => ({
  value,
  label: meta.label,
}))

export const SOURCE_OPTIONS = [
  { value: 'manual', label: '手工' },
  { value: 'ai', label: 'AI 生成' },
  { value: 'postman', label: 'Postman' },
]

export const PRIORITY_META = {
  1: { label: 'P1 高', tagType: 'danger' },
  2: { label: 'P2 中', tagType: 'warning' },
  3: { label: 'P3 低', tagType: 'info' },
}

export const PRIORITY_OPTIONS = Object.entries(PRIORITY_META).map(([value, meta]) => ({
  value: Number(value),
  label: meta.label,
}))

export function getCaseTypeLabel(caseType) {
  const found = CASE_TYPE_OPTIONS.find((item) => item.value === caseType)
  return found ? found.label : toText(caseType) || EMPTY_TEXT
}

export function getTestTypeMeta(testType) {
  const key = toText(testType).trim().toLowerCase()
  const meta = TEST_TYPE_META[key]
  return meta
    ? { key, ...meta }
    : { key, label: key || EMPTY_TEXT, tagType: 'info' }
}

export function getTestTypeLabel(testType) {
  return getTestTypeMeta(testType).label
}

export function getTestTypeTagType(testType) {
  return getTestTypeMeta(testType).tagType
}

export function getSourceLabel(source) {
  const found = SOURCE_OPTIONS.find((item) => item.value === source)
  return found ? found.label : toText(source) || EMPTY_TEXT
}

export function getPriorityMeta(priority) {
  const key = toNumber(priority, 2)
  const meta = PRIORITY_META[key]
  return meta ? { value: key, ...meta } : { value: key, label: `P${key}`, tagType: 'info' }
}

// ---------------------------------------------------------------------------
// 断言：type / json_path / expected / operator
// ---------------------------------------------------------------------------
export const ASSERTION_TYPE_OPTIONS = [
  { value: 'status_code', label: '状态码' },
  { value: 'json_path', label: 'JSON 路径' },
  { value: 'contains', label: '包含' },
  { value: 'len_gte', label: '长度 ≥' },
  { value: 'response_time_lt', label: '响应时间 <' },
  { value: 'header_present', label: '响应头存在' },
]

export const ASSERTION_OPERATOR_OPTIONS = [
  { value: 'equals', label: '等于' },
  { value: 'contains', label: '包含' },
  { value: 'gte', label: '大于等于' },
  { value: 'lt', label: '小于' },
]

/** 编辑器里的 operator 与后端断言的 type 双向映射。 */
export const OPERATOR_TO_ASSERTION_TYPE = {
  equals: 'json_path',
  contains: 'contains',
  gte: 'len_gte',
  lt: 'response_time_lt',
}

export const ASSERTION_TYPE_TO_OPERATOR = {
  status_code: 'equals',
  json_path: 'equals',
  equals: 'equals',
  eq: 'equals',
  contains: 'contains',
  len_gte: 'gte',
  length_gte: 'gte',
  response_time_lt: 'lt',
  time_lt: 'lt',
  header_present: 'equals',
}

export function getOperatorForAssertionType(type) {
  return ASSERTION_TYPE_TO_OPERATOR[toText(type).toLowerCase()] || 'equals'
}

export function getAssertionTypeForOperator(operator) {
  return OPERATOR_TO_ASSERTION_TYPE[toText(operator).toLowerCase()] || 'json_path'
}

function assertionValue(item) {
  if (!isPlainObject(item)) return ''
  const value = item.expected ?? item.value ?? item.expected_value ?? ''
  return value === null || value === undefined ? '' : value
}

/** 后端 assertions → 编辑器行模型（保留未识别的字段在提交时忽略）。 */
export function normalizeAssertionRows(assertions = []) {
  if (!Array.isArray(assertions)) return []
  return assertions
    .filter((item) => isPlainObject(item))
    .map((item) => {
      const type = toText(item.type).toLowerCase() || 'status_code'
      return {
        type,
        json_path: toText(item.json_path ?? item.path ?? item.field),
        expected: assertionValue(item),
        operator: getOperatorForAssertionType(type),
      }
    })
}

/** 编辑器行模型 → 后端 assertions 数组。 */
export function buildAssertionsPayload(rows = []) {
  if (!Array.isArray(rows)) return []
  return rows
    .filter((row) => isPlainObject(row) && row.type)
    .map((row) => {
      const payload = {
        type: toText(row.type),
        operator: row.operator || getOperatorForAssertionType(row.type),
      }
      const path = toText(row.json_path).trim()
      if (path) payload.json_path = path
      const expected = row.expected
      if (expected !== null && expected !== undefined && String(expected).trim() !== '') {
        payload.expected = expected
      }
      return payload
    })
}

/** 校验断言行，返回人类可读错误列表（空数组即合法）。 */
export function validateAssertionRows(rows = []) {
  if (!Array.isArray(rows)) return ['断言配置必须是数组']
  const errors = []
  rows.forEach((row, index) => {
    const label = `第 ${index + 1} 行断言`
    if (!isPlainObject(row) || !row.type) {
      errors.push(`${label}缺少断言类型`)
      return
    }
    const type = toText(row.type)
    if (type === 'status_code' && String(row.expected ?? '').trim() === '') {
      errors.push(`${label}缺少期望状态码`)
    }
    if (['json_path', 'contains', 'len_gte'].includes(type) && !toText(row.json_path).trim()) {
      errors.push(`${label}缺少 JSON 路径`)
    }
    if (type === 'header_present' && String(row.expected ?? '').trim() === '') {
      errors.push(`${label}缺少响应头名称`)
    }
  })
  return errors
}

// ---------------------------------------------------------------------------
// JSON 文本 / URL 校验 / 请求配置
// ---------------------------------------------------------------------------
export function isBlankText(value) {
  return toText(value).trim() === ''
}

/**
 * 校验 JSON 文本。
 * 返回 { valid, value, empty, message }，不抛异常。
 */
export function validateJsonText(text, { allowEmpty = true, label = 'JSON' } = {}) {
  const raw = toText(text)
  if (raw.trim() === '') {
    return allowEmpty
      ? { valid: true, value: undefined, empty: true, message: '' }
      : { valid: false, value: undefined, empty: true, message: `${label}不能为空` }
  }
  try {
    return { valid: true, value: JSON.parse(raw), empty: false, message: '' }
  } catch (error) {
    return {
      valid: false,
      value: undefined,
      empty: false,
      message: `${label}不是合法 JSON：${error?.message || '解析失败'}`,
    }
  }
}

/** 格式化 JSON 文本；失败时返回原文与错误信息。 */
export function formatJsonText(text) {
  const raw = toText(text)
  if (raw.trim() === '') return { ok: true, text: '', message: '' }
  try {
    return { ok: true, text: JSON.stringify(JSON.parse(raw), null, 2), message: '' }
  } catch (error) {
    return { ok: false, text: raw, message: `JSON 格式不合法：${error?.message || '解析失败'}` }
  }
}

export function isValidHttpUrl(value) {
  return /^https?:\/\/[^\s]+$/i.test(toText(value).trim())
}

/** 请求 URL 允许相对路径（/api/xxx）或完整 http(s) 地址。 */
export function isValidRequestUrl(value) {
  const raw = toText(value).trim()
  if (!raw) return false
  if (raw.startsWith('/')) return true
  return isValidHttpUrl(raw)
}

/** 粘贴的规范内容：JSON 必须可解析；YAML 交给后端解析。 */
export function validateSpecContent(text) {
  const raw = toText(text).trim()
  if (!raw) return { valid: false, message: '规范内容不能为空' }
  if (raw.startsWith('{') || raw.startsWith('[')) {
    try {
      JSON.parse(raw)
      return { valid: true, message: '' }
    } catch (error) {
      return { valid: false, message: `内容不是合法 JSON：${error?.message || '解析失败'}` }
    }
  }
  return { valid: true, message: '' }
}

/**
 * 从用例编辑表单构建 request_config。
 * 返回 { ok, config, errors, fieldErrors }；任何非法 JSON 都不会静默丢弃。
 */
export function buildRequestConfig(input = {}) {
  const method = toText(input.method || 'GET').toUpperCase()
  const url = toText(input.url).trim()
  const errors = []
  const fieldErrors = { params: '', headers: '', body: '' }
  const config = { method, url }

  if (!url) {
    errors.push('请求 URL 不能为空')
  } else if (!isValidRequestUrl(url)) {
    errors.push('请求 URL 需以 / 开头，或为 http(s) 完整地址')
  }

  const params = validateJsonText(input.paramsText, { label: 'Query 参数' })
  if (!params.valid) fieldErrors.params = params.message
  else if (!params.empty && !isPlainObject(params.value)) {
    fieldErrors.params = 'Query 参数必须是 JSON 对象'
  } else if (!params.empty && Object.keys(params.value).length) {
    config.params = params.value
  }

  const headers = validateJsonText(input.headersText, { label: '请求头' })
  if (!headers.valid) fieldErrors.headers = headers.message
  else if (!headers.empty && !isPlainObject(headers.value)) {
    fieldErrors.headers = '请求头必须是 JSON 对象'
  } else if (!headers.empty && Object.keys(headers.value).length) {
    config.headers = headers.value
  }

  const body = validateJsonText(input.bodyText, { label: '请求体' })
  if (!body.valid) fieldErrors.body = body.message
  else if (!body.empty && body.value !== null) {
    // 统一收敛为 HttpRunner 可识别的 raw/json 结构
    config.body = { mode: 'raw', json: body.value }
  }

  Object.entries(fieldErrors).forEach(([field, message]) => {
    if (message) errors.push(message)
  })

  return { ok: errors.length === 0, config, errors, fieldErrors }
}

/** 后端 request_config → 编辑表单字段（用于编辑已有用例）。 */
export function requestConfigToForm(config = {}) {
  const source = isPlainObject(config) ? config : {}
  let body = source.body
  if (isPlainObject(body) && ('json' in body || 'raw' in body || 'mode' in body)) {
    body = body.json ?? body.raw ?? null
  }
  return {
    method: toText(source.method || 'GET').toUpperCase(),
    url: toText(source.url || source.path || ''),
    paramsText:
      isPlainObject(source.params) && Object.keys(source.params).length
        ? JSON.stringify(source.params, null, 2)
        : '',
    headersText:
      isPlainObject(source.headers) && Object.keys(source.headers).length
        ? JSON.stringify(source.headers, null, 2)
        : '',
    bodyText:
      body === null || body === undefined || body === ''
        ? ''
        : JSON.stringify(body, null, 2),
  }
}

// ---------------------------------------------------------------------------
// 执行报告格式化
// ---------------------------------------------------------------------------
/** 报告中的用例明细 → 表格行模型。 */
export function normalizeReportCases(cases = []) {
  if (!Array.isArray(cases)) return []
  return cases.map((item, index) => {
    const source = isPlainObject(item) ? item : {}
    const statusMeta = getExecutionStatusMeta(source.status)
    return {
      index: index + 1,
      id: source.id ?? index,
      name: toText(source.name || source.case_name || `用例 ${index + 1}`),
      status: statusMeta.status,
      statusLabel: statusMeta.label,
      tagType: statusMeta.tagType,
      durationMs: toNumber(source.duration_ms),
      durationText: formatDuration(source.duration_ms),
      errorMessage: toText(source.error_message),
      assertions: Array.isArray(source.assertions) ? source.assertions : [],
      request: isPlainObject(source.request) ? source.request : {},
      response: isPlainObject(source.response) ? source.response : {},
    }
  })
}

const EMPTY_REPORT = () => ({
  ok: false,
  execution: {},
  summary: {
    total: 0,
    passed: 0,
    failed: 0,
    skipped: 0,
    passRate: 0,
    passRateText: '0.0%',
    durationMs: 0,
    durationText: '0 ms',
    status: getExecutionStatusMeta(''),
    mode: '',
  },
  cases: [],
  artifacts: {},
  generatedAt: '',
})

/**
 * 兼容三种报告来源：报告文件、内联报告、异常兜底。
 * 永不抛错；缺失字段统一补 0 / 空字符串。
 */
export function normalizeReport(report) {
  if (!isPlainObject(report)) return EMPTY_REPORT()
  const execution = isPlainObject(report.execution) ? report.execution : {}
  const summary = isPlainObject(report.summary) ? report.summary : {}
  const artifacts = isPlainObject(report.artifacts) ? report.artifacts : {}
  const cases = normalizeReportCases(report.cases)
  const passRate = toNumber(summary.pass_rate ?? execution.pass_rate)
  const durationMs = toNumber(summary.duration_ms ?? execution.duration_ms)
  return {
    ok: true,
    execution,
    summary: {
      total: toNumber(summary.total ?? execution.total),
      passed: toNumber(summary.passed ?? execution.passed),
      failed: toNumber(summary.failed ?? execution.failed),
      skipped: toNumber(summary.skipped ?? execution.skipped),
      passRate,
      passRateText: formatPercent(passRate),
      durationMs,
      durationText: formatDuration(durationMs),
      status: getExecutionStatusMeta(summary.status || execution.status),
      mode: toText(summary.mode || artifacts.mode),
    },
    cases,
    artifacts,
    generatedAt: toText(report.generated_at || report.generatedAt),
  }
}

/** 报告 JSON 下载文件名。 */
export function buildReportFilename(execution, prefix = 'api-execution-report') {
  const id = execution && (execution.id ?? execution.execution_id)
  return `${prefix}-${id || 'unknown'}.json`
}

// ---------------------------------------------------------------------------
// 生成用例结果摘要
// ---------------------------------------------------------------------------
/** 统一 GET 预览 / POST 生成两种返回结构。 */
export function summarizeGeneratedCases(payload) {
  const list = Array.isArray(payload?.cases) ? payload.cases : []
  const count = toNumber(payload?.created, list.length)
  return {
    count,
    preview: Boolean(payload?.preview),
    message: payload?.preview ? `预览 ${count} 条用例` : `已生成 ${count} 条用例`,
    cases: list.map((item, index) => {
      const source = isPlainObject(item) ? item : {}
      const request = isPlainObject(source.request_config) ? source.request_config : {}
      return {
        id: source.id ?? `generated-${index}`,
        name: toText(source.name || `用例 ${index + 1}`),
        testType: toText(source.test_type),
        testTypeLabel: getTestTypeLabel(source.test_type),
        priority: getPriorityMeta(source.priority).label,
        method: getMethodLabel(request.method),
        url: toText(request.url || request.path),
        assertionCount: Array.isArray(source.assertions) ? source.assertions.length : 0,
      }
    }),
  }
}
