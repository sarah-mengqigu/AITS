/**
 * Web UI 测试模块的纯逻辑工具（无 Vue / DOM 依赖，可单元测试）。
 *
 * 契约来源：docs/ARCHITECTURE.md §2.4 与 backend/apps/web_testing/{models,serializers}.py
 * - 执行状态 pending/running/passed/failed/error/cancelled
 * - 脚本类型 playwright / midscene
 * - 步骤结构 {action, target, value, expect, description}
 */

// ---------------------------------------------------------------------------
// 枚举与文案
// ---------------------------------------------------------------------------
export const EXECUTION_STATUS_TEXT = {
  pending: '待执行',
  running: '执行中',
  passed: '通过',
  failed: '失败',
  error: '错误',
  cancelled: '已取消',
}

export const EXECUTION_STATUS_TAG_TYPE = {
  pending: 'info',
  running: 'warning',
  passed: 'success',
  failed: 'danger',
  error: 'danger',
  cancelled: 'info',
}

export const CASE_STATUS_TEXT = {
  pending: '待执行',
  running: '执行中',
  passed: '通过',
  failed: '失败',
  skipped: '跳过',
  error: '错误',
}

export const CASE_STATUS_TAG_TYPE = {
  pending: 'info',
  running: 'warning',
  passed: 'success',
  failed: 'danger',
  skipped: 'info',
  error: 'danger',
}

/** 执行终态：到达后不再轮询 / 允许展示取消按钮。 */
export const TERMINAL_STATUSES = ['passed', 'failed', 'error', 'cancelled']

export const SCRIPT_TYPE_OPTIONS = [
  { value: 'playwright', label: 'Playwright' },
  { value: 'midscene', label: 'MidScene' },
]

export const SCRIPT_TYPE_TEXT = { playwright: 'Playwright', midscene: 'MidScene' }

export const CASE_TYPE_OPTIONS = [
  { value: 'ui', label: 'UI 用例' },
  { value: 'api_mixed', label: '接口混合用例' },
]

export const CASE_TYPE_TEXT = { ui: 'UI 用例', api_mixed: '接口混合用例' }

export const PRIORITY_OPTIONS = [
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
  { value: 'critical', label: '紧急' },
]

export const PRIORITY_TEXT = { low: '低', medium: '中', high: '高', critical: '紧急' }

export const PRIORITY_TAG_TYPE = {
  low: 'info',
  medium: 'info',
  high: 'warning',
  critical: 'danger',
}

export const BROWSER_OPTIONS = [
  { value: 'chromium', label: 'Chromium' },
  { value: 'firefox', label: 'Firefox' },
  { value: 'webkit', label: 'WebKit' },
]

export const BROWSER_TEXT = { chromium: 'Chromium', firefox: 'Firefox', webkit: 'WebKit' }

export const SOURCE_TEXT = {
  manual: '手工创建',
  ai: 'AI 生成',
  recording: '录制',
}

export const TRIGGER_TYPE_TEXT = {
  manual: '手动触发',
  scheduled: '定时触发',
  api: 'API 触发',
}

export const LOCATOR_TYPE_OPTIONS = [
  { value: 'css', label: 'CSS 选择器' },
  { value: 'xpath', label: 'XPath' },
  { value: 'text', label: '文本' },
  { value: 'role', label: 'ARIA Role' },
  { value: 'id', label: '元素 ID' },
  { value: 'testid', label: 'Test ID' },
]

export const LOCATOR_TYPE_TEXT = {
  css: 'CSS',
  xpath: 'XPath',
  text: '文本',
  role: 'ARIA Role',
  id: '元素 ID',
  testid: 'Test ID',
}

export const LOCATOR_TYPE_KEYS = LOCATOR_TYPE_OPTIONS.map((item) => item.value)

export const MIDSCENE_STATUS_TEXT = {
  draft: '草稿',
  generated: '已生成',
  failed: '生成失败',
}

export const MIDSCENE_STATUS_TAG_TYPE = {
  draft: 'info',
  generated: 'success',
  failed: 'danger',
}

/** 与后端 serializers.STEP_ACTIONS 对齐（提交非法 action 会被 400 拒绝）。 */
export const STEP_ACTION_OPTIONS = [
  { value: 'goto', label: '打开页面' },
  { value: 'click', label: '点击' },
  { value: 'fill', label: '输入' },
  { value: 'assert_text', label: '断言文本' },
  { value: 'assert_visible', label: '断言可见' },
  { value: 'wait', label: '等待' },
  { value: 'press', label: '按键' },
  { value: 'keyboard', label: '键盘输入' },
  { value: 'hover', label: '悬停' },
  { value: 'select', label: '下拉选择' },
  { value: 'check', label: '勾选' },
  { value: 'uncheck', label: '取消勾选' },
  { value: 'scroll', label: '滚动' },
  { value: 'upload', label: '上传文件' },
  { value: 'screenshot', label: '截图' },
]

export const STEP_ACTION_KEYS = STEP_ACTION_OPTIONS.map((item) => item.value)

const STEP_ACTION_LABEL = STEP_ACTION_OPTIONS.reduce((acc, item) => {
  acc[item.value] = item.label
  return acc
}, {})

/** 必须填写 target 的 action（其余如 wait / screenshot 可只填 value）。 */
export const STEP_ACTIONS_REQUIRING_TARGET = [
  'goto',
  'click',
  'fill',
  'assert_text',
  'assert_visible',
  'press',
  'keyboard',
  'hover',
  'select',
  'check',
  'uncheck',
  'upload',
]

/** 必须填写 value 的 action。 */
export const STEP_ACTIONS_REQUIRING_VALUE = [
  'fill',
  'press',
  'keyboard',
  'select',
  'upload',
]

// ---------------------------------------------------------------------------
// 基础工具
// ---------------------------------------------------------------------------
export function getExecutionStatusText(status, fallback = '未知') {
  if (!status) return fallback
  return EXECUTION_STATUS_TEXT[status] || fallback
}

export function getExecutionStatusTagType(status) {
  return EXECUTION_STATUS_TAG_TYPE[status] || 'info'
}

export function getCaseStatusText(status, fallback = '未知') {
  if (!status) return fallback
  return CASE_STATUS_TEXT[status] || fallback
}

export function getCaseStatusTagType(status) {
  return CASE_STATUS_TAG_TYPE[status] || 'info'
}

export function getScriptTypeText(type, fallback = '—') {
  if (!type) return fallback
  return SCRIPT_TYPE_TEXT[type] || String(type)
}

export function getPriorityText(priority, fallback = '中') {
  if (!priority) return fallback
  return PRIORITY_TEXT[priority] || String(priority)
}

export function getStepActionLabel(action) {
  if (!action) return '步骤'
  return STEP_ACTION_LABEL[action] || String(action)
}

export function isValidStepAction(action) {
  return STEP_ACTION_KEYS.includes(String(action || ''))
}

export function isTerminalStatus(status) {
  return TERMINAL_STATUSES.includes(String(status || ''))
}

/** 列表接口统一兼容 `{count, results}`、裸数组与 `{results}`。 */
export function normalizeListPayload(payload) {
  if (Array.isArray(payload)) return { results: payload, count: payload.length }
  if (payload && typeof payload === 'object') {
    const results = Array.isArray(payload.results)
      ? payload.results
      : Array.isArray(payload.data)
        ? payload.data
        : []
    const count = Number.isFinite(Number(payload.count)) ? Number(payload.count) : results.length
    return { results, count }
  }
  return { results: [], count: 0 }
}

/** 树节点扁平化（模块树用于下拉/统计）。 */
export function flattenTree(nodes = []) {
  const out = []
  const walk = (list, depth = 0) => {
    if (!Array.isArray(list)) return
    list.forEach((node) => {
      if (!node || typeof node !== 'object') return
      out.push({ ...node, depth })
      walk(node.children, depth + 1)
    })
  }
  walk(nodes)
  return out
}

/** 树 → el-tree-select 选项（label/value/children）。 */
export function toTreeOptions(nodes = [], { includeAll = false, allLabel = '全部模块' } = {}) {
  const mapNode = (node) => ({
    value: node.id,
    label: node.name,
    children: Array.isArray(node.children) ? node.children.map(mapNode) : [],
  })
  const options = Array.isArray(nodes) ? nodes.map(mapNode) : []
  if (includeAll) {
    return [{ value: null, label: allLabel, children: [] }, ...options]
  }
  return options
}

/** 安全解析 JSON 文本（表单里的 assertions / alternatives / config）。 */
export function parseJsonText(text, { allowEmpty = true, expected = null } = {}) {
  const raw = typeof text === 'string' ? text.trim() : text
  if (raw === '' || raw === null || raw === undefined) {
    if (allowEmpty) return { ok: true, value: expected === 'array' ? [] : expected === 'object' ? {} : null }
    return { ok: false, error: 'JSON 不能为空', value: null }
  }
  if (typeof raw !== 'string') return { ok: true, value: raw }
  let value
  try {
    value = JSON.parse(raw)
  } catch (error) {
    return { ok: false, error: `JSON 格式不合法：${error?.message || '解析失败'}`, value: null }
  }
  if (expected === 'array' && !Array.isArray(value)) {
    return { ok: false, error: 'JSON 必须是数组', value: null }
  }
  if (expected === 'object' && (Array.isArray(value) || typeof value !== 'object' || value === null)) {
    return { ok: false, error: 'JSON 必须是对象', value: null }
  }
  return { ok: true, value }
}

// ---------------------------------------------------------------------------
// 用例步骤
// ---------------------------------------------------------------------------
export function emptyStep(action = 'click') {
  return { action, target: '', value: '', expect: '', description: '' }
}

/** 容忍后端/历史数据的多种键名（selector/locator/assert）。 */
export function normalizeStep(step) {
  if (!step || typeof step !== 'object') {
    return emptyStep()
  }
  const action = String(step.action || '').trim()
  const target = step.target ?? step.selector ?? step.locator ?? ''
  const value = step.value ?? step.input ?? ''
  const expect = step.expect ?? step.assert ?? step.expected ?? ''
  return {
    action,
    target: typeof target === 'object' && target !== null
      ? target.name || target.selector || JSON.stringify(target)
      : String(target ?? ''),
    value: typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value ?? ''),
    expect: typeof expect === 'object' && expect !== null ? JSON.stringify(expect) : String(expect ?? ''),
    description: String(step.description ?? ''),
  }
}

export function normalizeSteps(steps) {
  if (!Array.isArray(steps)) return []
  return steps.map((step) => normalizeStep(step))
}

/**
 * 校验步骤数组，返回 `{valid, errors, steps}`。
 * 规则与后端 serializer 对齐（action 必填且在允许集合内），并额外提示
 * target/value 缺失，避免提交后才在服务端报错。
 */
export function validateSteps(steps) {
  const list = Array.isArray(steps) ? steps : []
  const errors = []
  const cleaned = []
  list.forEach((step, index) => {
    const normalized = normalizeStep(step)
    const position = index + 1
    if (!normalized.action) {
      errors.push(`第 ${position} 个步骤缺少 action`)
      return
    }
    if (!isValidStepAction(normalized.action)) {
      errors.push(`第 ${position} 个步骤 action 不支持：${normalized.action}`)
      return
    }
    if (STEP_ACTIONS_REQUIRING_TARGET.includes(normalized.action) && !normalized.target.trim()) {
      errors.push(`第 ${position} 个步骤（${getStepActionLabel(normalized.action)}）需要填写 target`)
    }
    if (STEP_ACTIONS_REQUIRING_VALUE.includes(normalized.action) && !normalized.value.trim()) {
      errors.push(`第 ${position} 个步骤（${getStepActionLabel(normalized.action)}）需要填写 value`)
    }
    cleaned.push(normalized)
  })
  return { valid: errors.length === 0, errors, steps: cleaned }
}

/** 单步 → 中文摘要，例如 `1. 点击 登录按钮`。 */
export function formatStep(step, index = null) {
  const normalized = normalizeStep(step)
  const prefix = index === null ? '' : `${index}. `
  const label = getStepActionLabel(normalized.action)
  const parts = [label]
  if (normalized.target) parts.push(normalized.target)
  let text = `${prefix}${parts.join(' ')}`
  if (normalized.value) text += ` = ${normalized.value}`
  if (normalized.expect) text += `（期望：${normalized.expect}）`
  return text
}

export function summarizeSteps(steps) {
  const list = normalizeSteps(steps)
  if (!list.length) return '暂无步骤'
  return `${list.length} 个步骤：${list.map((step) => getStepActionLabel(step.action)).join(' → ')}`
}

/** 只保留有内容的行，并清理空字符串字段（提交给后端）。 */
export function buildStepsPayload(steps) {
  if (!Array.isArray(steps)) return []
  return steps
    .map((step) => normalizeStep(step))
    .filter((step) => step.action)
    .map((step) => {
      const item = { action: step.action }
      if (step.target) item.target = step.target
      if (step.value) item.value = step.value
      if (step.expect) item.expect = step.expect
      if (step.description) item.description = step.description
      return item
    })
}

// ---------------------------------------------------------------------------
// 执行/统计
// ---------------------------------------------------------------------------
/** 通过率：优先后端 pass_rate，缺失时以 passed/(passed+failed) 计算。 */
export function computePassRate(execution = {}) {
  const raw = execution?.pass_rate
  if (raw !== null && raw !== undefined && raw !== '' && Number.isFinite(Number(raw))) {
    return Number(raw)
  }
  const passed = Number(execution?.passed) || 0
  const failed = Number(execution?.failed) || 0
  if (passed + failed === 0) return 0
  return Math.round((passed * 10000) / (passed + failed)) / 100
}

/** 执行列表聚合（总览统计卡）。 */
export function summarizeExecutions(executions = []) {
  const list = Array.isArray(executions) ? executions : []
  const summary = {
    current: list.length,
    pending: 0,
    running: 0,
    passed: 0,
    failed: 0,
    error: 0,
    cancelled: 0,
    cases: 0,
    passedCases: 0,
    failedCases: 0,
    passRate: 0,
  }
  list.forEach((item) => {
    const status = String(item?.status || '')
    if (summary[status] !== undefined) summary[status] += 1
    summary.cases += Number(item?.total) || 0
    summary.passedCases += Number(item?.passed) || 0
    summary.failedCases += Number(item?.failed) || 0
  })
  const executed = summary.passed + summary.failed + summary.error
  summary.passRate = executed ? Math.round((summary.passed * 10000) / executed) / 100 : 0
  return summary
}

/** 执行 / 任务状态归一（WS 消息与轮询结果共用）。 */
export function normalizeTaskStatus(payload) {
  if (!payload || typeof payload !== 'object') return { status: '', progress: null, message: '' }
  const data = payload.data && typeof payload.data === 'object' ? payload.data : payload
  const rawStatus = data.status ?? data.task_status ?? data.execution_status ?? ''
  const progressValue = Number(data.progress)
  return {
    status: String(rawStatus || '').toLowerCase(),
    progress: Number.isFinite(progressValue) ? Math.max(0, Math.min(100, progressValue)) : null,
    message: data.message || data.detail || '',
  }
}

export function getProgressPercent(state = {}) {
  const value = Number(state?.progress)
  if (Number.isFinite(value)) return Math.max(0, Math.min(100, value))
  const status = String(state?.status || '')
  if (status === 'pending') return 5
  if (status === 'running') return 60
  if (isTerminalStatus(status)) return 100
  return 0
}

/** 套件/用例执行结果 → 提示文案。 */
export function describeExecutionResult(state = {}) {
  const status = String(state?.status || '')
  if (status === 'passed') return '执行通过'
  if (status === 'failed') return '执行失败'
  if (status === 'error') return '执行异常'
  if (status === 'cancelled') return '执行已取消'
  return '执行结束'
}

// ---------------------------------------------------------------------------
// POM
// ---------------------------------------------------------------------------
/** POM 页面引用下拉（case.pom_refs 保存页面 id 数组）。 */
export function pageOptions(pages = []) {
  if (!Array.isArray(pages)) return []
  return pages.map((page) => ({
    value: page.id,
    label: page.name,
    url: page.url || '',
  }))
}

/** 规范化后端返回的元素列表（兼容裸数组 / 分页结构）。 */
export function normalizeElementList(payload) {
  const { results } = normalizeListPayload(payload)
  return results.map((item) => ({
    ...item,
    alternatives: Array.isArray(item?.alternatives) ? item.alternatives : [],
  }))
}

/** 备选定位行 → 后端 alternatives（`[{locator_type, locator_value}]`）。 */
export function buildAlternatives(rows = []) {
  if (!Array.isArray(rows)) return []
  return rows
    .map((row) => ({
      locator_type: String(row?.locator_type || 'css'),
      locator_value: String(row?.locator_value || '').trim(),
    }))
    .filter((row) => row.locator_value)
}

/** 批量 upsert JSON → `{page, elements}`；返回 `{ok, value, error}`。 */
export function parseBulkElements(text, pageId) {
  const parsed = parseJsonText(text, { allowEmpty: false, expected: 'array' })
  if (!parsed.ok) return parsed
  const elements = parsed.value
    .map((item, index) => {
      if (!item || typeof item !== 'object') {
        return { __error: `第 ${index + 1} 项必须是对象` }
      }
      const name = String(item.name || '').trim()
      const locatorValue = String(item.locator_value || item.selector || '').trim()
      if (!name) return { __error: `第 ${index + 1} 项缺少 name` }
      if (!locatorValue) return { __error: `第 ${index + 1} 项（${name}）缺少 locator_value` }
      const locatorType = String(item.locator_type || 'css')
      if (!LOCATOR_TYPE_KEYS.includes(locatorType)) {
        return { __error: `第 ${index + 1} 项（${name}）locator_type 非法：${locatorType}` }
      }
      return {
        name,
        locator_type: locatorType,
        locator_value: locatorValue,
        description: String(item.description || ''),
        alternatives: buildAlternatives(item.alternatives),
      }
    })
  const firstError = elements.find((item) => item && item.__error)
  if (firstError) return { ok: false, error: firstError.__error, value: null }
  if (!pageId) return { ok: false, error: '请先选择页面', value: null }
  return { ok: true, value: { page: pageId, elements }, error: '' }
}

/** 生成脚本/内容下载文件名。 */
export function scriptFileName(caseItem = {}, scriptType = 'playwright') {
  const base = String(caseItem?.name || 'web-case')
    .replace(/[\\/:*?"<>|\s]+/g, '_')
    .slice(0, 60)
  const ext = scriptType === 'midscene' ? 'yaml' : 'py'
  return `${base || 'web-case'}.${ext}`
}

export function midsceneFileName(script = {}) {
  const base = String(script?.name || 'midscene-script')
    .replace(/[\\/:*?"<>|\s]+/g, '_')
    .slice(0, 60)
  return `${base || 'midscene-script'}.${script?.script_type === 'python' ? 'py' : 'yaml'}`
}
