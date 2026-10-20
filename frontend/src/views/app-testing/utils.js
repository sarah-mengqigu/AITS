/**
 * 移动端 App 测试模块的纯逻辑工具（无 Vue / DOM 依赖，可单元测试）。
 *
 * 契约来源：docs/ARCHITECTURE.md §2.5 与 backend/apps/app_testing/{models,serializers}.py
 * - 运行状态 pending/running/passed/failed/error/cancelled
 * - 平台 android 必填 package_name，ios 必填 bundle_id
 * - AITS 步骤 {action, target, value, expect, description}
 * - Sonic 步骤 [{type, content: {action(中文), target, value, expect}}]
 * - Sonic 未配置：读接口返回 []，详情/远控返回 {detail: "sonic_not_configured"}
 */

// ---------------------------------------------------------------------------
// 枚举与文案
// ---------------------------------------------------------------------------
export const PLATFORM_OPTIONS = [
  { value: 'android', label: 'Android' },
  { value: 'ios', label: 'iOS' },
]

export const PLATFORM_TEXT = { android: 'Android', ios: 'iOS' }

export const PLATFORM_TAG_TYPE = { android: 'success', ios: 'primary' }

export const RUN_STATUS_TEXT = {
  pending: '待执行',
  running: '执行中',
  passed: '通过',
  failed: '失败',
  error: '错误',
  cancelled: '已取消',
}

export const RUN_STATUS_TAG_TYPE = {
  pending: 'info',
  running: 'warning',
  passed: 'success',
  failed: 'danger',
  error: 'danger',
  cancelled: 'info',
}

export const TERMINAL_STATUSES = ['passed', 'failed', 'error', 'cancelled']

export const APP_SOURCE_TEXT = {
  manual: '手工创建',
  ai: 'AI 生成',
  sonic: 'Sonic 同步',
}

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

export const TRIGGER_TYPE_TEXT = {
  manual: '手动触发',
  scheduled: '定时触发',
  api: 'API 触发',
}

/** 与后端 APP_STEP_ACTIONS 对齐。 */
export const APP_STEP_ACTION_OPTIONS = [
  { value: 'tap', label: '点击' },
  { value: 'click', label: '点击（别名）' },
  { value: 'input', label: '输入' },
  { value: 'fill', label: '输入（别名）' },
  { value: 'swipe', label: '滑动' },
  { value: 'assert', label: '断言' },
  { value: 'assert_text', label: '断言文本' },
  { value: 'wait', label: '等待' },
  { value: 'back', label: '返回' },
  { value: 'start_app', label: '启动应用' },
  { value: 'stop_app', label: '关闭应用' },
]

export const APP_STEP_ACTION_KEYS = APP_STEP_ACTION_OPTIONS.map((item) => item.value)

const APP_STEP_ACTION_LABEL = APP_STEP_ACTION_OPTIONS.reduce((acc, item) => {
  acc[item.value] = item.label
  return acc
}, {})

export const APP_STEP_ACTIONS_REQUIRING_TARGET = [
  'tap',
  'click',
  'input',
  'fill',
  'swipe',
  'assert',
  'assert_text',
]

export const APP_STEP_ACTIONS_REQUIRING_VALUE = ['input', 'fill', 'assert', 'assert_text']

export const SONIC_NOT_CONFIGURED = 'sonic_not_configured'

export const SONIC_GUIDANCE =
  '未配置 Sonic 服务：请在后端环境变量中设置 SONIC_BASE_URL（可选 SONIC_USERNAME / SONIC_PASSWORD），重启服务后重试。'

export const SONIC_STEP_TYPE_LABEL = { 0: '操作', 1: '断言', 2: '其他' }

// ---------------------------------------------------------------------------
// 基础工具
// ---------------------------------------------------------------------------
export function getRunStatusText(status, fallback = '未知') {
  if (!status) return fallback
  return RUN_STATUS_TEXT[status] || fallback
}

export function getRunStatusTagType(status) {
  return RUN_STATUS_TAG_TYPE[status] || 'info'
}

export function getPlatformText(platform, fallback = '—') {
  if (!platform) return fallback
  return PLATFORM_TEXT[platform] || String(platform)
}

export function getPriorityText(priority, fallback = '中') {
  if (!priority) return fallback
  return PRIORITY_TEXT[priority] || String(priority)
}

export function getAppStepActionLabel(action) {
  if (!action) return '步骤'
  return APP_STEP_ACTION_LABEL[action] || String(action)
}

export function isValidAppStepAction(action) {
  return APP_STEP_ACTION_KEYS.includes(String(action || ''))
}

export function isTerminalStatus(status) {
  return TERMINAL_STATUSES.includes(String(status || ''))
}

/** 列表接口统一兼容 `{count, results}`、裸数组。 */
export function normalizeListPayload(payload) {
  if (Array.isArray(payload)) return { results: payload, count: payload.length }
  if (payload && typeof payload === 'object') {
    const results = Array.isArray(payload.results)
      ? payload.results
      : Array.isArray(payload.devices)
        ? payload.devices
        : Array.isArray(payload.data)
          ? payload.data
          : []
    const count = Number.isFinite(Number(payload.count)) ? Number(payload.count) : results.length
    return { results, count }
  }
  return { results: [], count: 0 }
}

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

export function toTreeOptions(nodes = [], { includeAll = false, allLabel = '全部模块' } = {}) {
  const mapNode = (node) => ({
    value: node.id,
    label: node.name,
    children: Array.isArray(node.children) ? node.children.map(mapNode) : [],
  })
  const options = Array.isArray(nodes) ? nodes.map(mapNode) : []
  if (includeAll) return [{ value: null, label: allLabel, children: [] }, ...options]
  return options
}

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
// 应用（平台字段校验）
// ---------------------------------------------------------------------------
/**
 * 校验应用表单。平台切换时只校验对应字段：
 * - android：必须填写 package_name
 * - ios：必须填写 bundle_id
 * @returns {{valid: boolean, errors: Record<string, string>}}
 */
export function validateApplicationForm(form = {}) {
  const errors = {}
  if (!String(form.name || '').trim()) errors.name = '请输入应用名称'
  const platform = String(form.platform || '').trim()
  if (!PLATFORM_TEXT[platform]) {
    errors.platform = '平台仅支持 android 或 ios'
    return { valid: false, errors }
  }
  if (platform === 'android') {
    if (!String(form.package_name || '').trim()) {
      errors.package_name = 'Android 应用必须填写包名（package_name）'
    }
  }
  if (platform === 'ios') {
    if (!String(form.bundle_id || '').trim()) {
      errors.bundle_id = 'iOS 应用必须填写 Bundle ID（bundle_id）'
    }
  }
  return { valid: Object.keys(errors).length === 0, errors }
}

/** 按平台清理提交载荷：android 只提交包名，ios 只提交 Bundle ID。 */
export function buildApplicationPayload(form = {}) {
  const platform = String(form.platform || 'android')
  return {
    name: String(form.name || '').trim(),
    platform,
    package_name: platform === 'android' ? String(form.package_name || '').trim() : '',
    bundle_id: platform === 'ios' ? String(form.bundle_id || '').trim() : '',
    app_version: String(form.app_version || '').trim(),
    description: String(form.description || '').trim(),
  }
}

/** 列表展示用的应用标识（Android 包名 / iOS Bundle ID）。 */
export function applicationIdentifier(app = {}) {
  const platform = String(app.platform || '')
  if (platform === 'ios') return app.bundle_id || app.package_name || ''
  return app.package_name || app.bundle_id || ''
}

/** 平台切换时的提示文案。 */
export function platformFieldHint(platform) {
  if (platform === 'ios') return 'iOS 应用请填写 Bundle ID（例如 com.example.app）'
  return 'Android 应用请填写包名（例如 com.example.app）'
}

// ---------------------------------------------------------------------------
// 用例步骤
// ---------------------------------------------------------------------------
export function emptyAppStep(action = 'tap') {
  return { action, target: '', value: '', expect: '', description: '' }
}

export function normalizeAppStep(step) {
  if (!step || typeof step !== 'object') return emptyAppStep()
  const action = String(step.action || '').trim().toLowerCase()
  const target = step.target ?? step.selector ?? ''
  const value = step.value ?? step.input ?? ''
  const expect = step.expect ?? step.assert ?? ''
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

export function normalizeAppSteps(steps) {
  if (!Array.isArray(steps)) return []
  return steps.map((step) => normalizeAppStep(step))
}

export function validateAppSteps(steps) {
  const list = Array.isArray(steps) ? steps : []
  const errors = []
  const cleaned = []
  list.forEach((step, index) => {
    const normalized = normalizeAppStep(step)
    const position = index + 1
    if (!normalized.action) {
      errors.push(`第 ${position} 个步骤缺少 action`)
      return
    }
    if (!isValidAppStepAction(normalized.action)) {
      errors.push(`第 ${position} 个步骤 action 不支持：${normalized.action}`)
      return
    }
    if (APP_STEP_ACTIONS_REQUIRING_TARGET.includes(normalized.action) && !normalized.target.trim()) {
      errors.push(`第 ${position} 个步骤（${getAppStepActionLabel(normalized.action)}）需要填写 target`)
    }
    if (APP_STEP_ACTIONS_REQUIRING_VALUE.includes(normalized.action) && !normalized.value.trim()) {
      errors.push(`第 ${position} 个步骤（${getAppStepActionLabel(normalized.action)}）需要填写 value`)
    }
    cleaned.push(normalized)
  })
  return { valid: errors.length === 0, errors, steps: cleaned }
}

export function formatAppStep(step, index = null) {
  const normalized = normalizeAppStep(step)
  const prefix = index === null ? '' : `${index}. `
  const parts = [getAppStepActionLabel(normalized.action)]
  if (normalized.target) parts.push(normalized.target)
  let text = `${prefix}${parts.join(' ')}`
  if (normalized.value) text += ` = ${normalized.value}`
  if (normalized.expect) text += `（期望：${normalized.expect}）`
  return text
}

export function buildAppStepsPayload(steps) {
  if (!Array.isArray(steps)) return []
  return steps
    .map((step) => normalizeAppStep(step))
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

/** Sonic 步骤快照 → 只读表格行（`{type, content: {...}}`）。 */
export function summarizeSonicSteps(sonicSteps) {
  if (!Array.isArray(sonicSteps)) return []
  return sonicSteps.map((step, index) => {
    if (!step || typeof step !== 'object') {
      return { index: index + 1, typeLabel: '未知', action: '', target: '', value: '', expect: '' }
    }
    const content = step.content && typeof step.content === 'object' ? step.content : step
    const type = Number(step.type)
    return {
      index: index + 1,
      typeLabel: Number.isFinite(type) ? SONIC_STEP_TYPE_LABEL[type] || `类型 ${type}` : '—',
      action: content.action || '',
      target: content.target || '',
      value: content.value || '',
      expect: content.expect || '',
      description: content.description || '',
    }
  })
}

// ---------------------------------------------------------------------------
// Sonic 设备 / 元素页面
// ---------------------------------------------------------------------------
/** 后端 `{detail: "sonic_not_configured"}` / `{configured: false}` 判定。 */
export function isSonicNotConfigured(payload) {
  if (!payload || typeof payload !== 'object') return false
  if (payload.detail === SONIC_NOT_CONFIGURED) return true
  if (payload.configured === false) return true
  return false
}

/** 设备列表接口返回内容归一：数组 / `{results}` / `{detail}` → 数组。 */
export function normalizeDeviceList(payload) {
  if (isSonicNotConfigured(payload)) return []
  const { results } = normalizeListPayload(payload)
  return results.filter((item) => item && typeof item === 'object')
}

/** Sonic 设备字段容错归一（不同 Sonic 版本字段名不一致）。 */
export function formatDevice(device = {}) {
  const udid = device.udid || device.deviceUdid || device.id || ''
  return {
    udid: String(udid || ''),
    name: device.name || device.deviceName || device.model || '未命名设备',
    model: device.model || device.deviceModel || '',
    platform: String(device.platform || device.os || 'android').toLowerCase() === 'ios'
      ? 'ios'
      : 'android',
    version: device.version || device.osVersion || '',
    status: device.status || device.state || '',
    statusText: device.status === 'ONLINE' || device.state === 'online' || device.online === true
      ? '在线'
      : device.status || device.state || '未知',
    size: device.size || device.resolution || '',
    raw: device,
  }
}

export function normalizeElementPageList(payload) {
  if (isSonicNotConfigured(payload)) return []
  const { results } = normalizeListPayload(payload)
  return results.filter((item) => item && typeof item === 'object')
}

/** 设备配置（套件保存 / 运行覆盖）。 */
export function buildDeviceConfig(form = {}) {
  const config = {}
  const udid = String(form.device_udid || form.udid || '').trim()
  if (udid) config.udid = udid
  const name = String(form.device_name || '').trim()
  if (name) config.device_name = name
  const platform = String(form.platform || '').trim()
  if (platform) config.platform = platform
  return config
}

export function describeDeviceConfig(deviceConfig = {}) {
  if (!deviceConfig || typeof deviceConfig !== 'object') return '未指定设备'
  const udid = deviceConfig.udid || deviceConfig.device_udid || ''
  const name = deviceConfig.device_name || ''
  const platform = deviceConfig.platform ? getPlatformText(deviceConfig.platform) : ''
  if (!udid && !name) return '未指定设备（使用默认设备）'
  return [name, udid, platform].filter(Boolean).join(' / ')
}

/** 运行/远程调试中 Sonic 相关错误码 → 中文引导。 */
export function describeSonicError(error) {
  const code = error?.code || error?.response?.data?.code || ''
  const message = error?.message || ''
  if (code === SONIC_NOT_CONFIGURED || /sonic_not_configured/.test(message)) {
    return SONIC_GUIDANCE
  }
  if (code === 'sonic_remote_unavailable') {
    return '获取远控信息失败，请确认设备在线后重试'
  }
  return message || 'Sonic 请求失败'
}

/** 远控返回信息归一（`ws_url` + jmuxer 配置）。 */
export function normalizeRemoteInfo(payload = {}) {
  const wsUrl = payload.ws_url || payload.wsUrl || ''
  const jmuxer = payload.jmuxer && typeof payload.jmuxer === 'object' ? payload.jmuxer : {}
  return {
    configured: payload.configured !== false && payload.detail !== SONIC_NOT_CONFIGURED,
    wsUrl: String(wsUrl || ''),
    jmuxer,
    detail: payload.detail || '',
  }
}

// ---------------------------------------------------------------------------
// 统计
// ---------------------------------------------------------------------------
export function summarizeRuns(runs = []) {
  const list = Array.isArray(runs) ? runs : []
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

export function computePassRate(run = {}) {
  const raw = run?.pass_rate
  if (raw !== null && raw !== undefined && raw !== '' && Number.isFinite(Number(raw))) {
    return Number(raw)
  }
  const passed = Number(run?.passed) || 0
  const failed = Number(run?.failed) || 0
  if (passed + failed === 0) return 0
  return Math.round((passed * 10000) / (passed + failed)) / 100
}

/** 运行详情 summary.cases 归一（后端写入的用例明细）。 */
export function normalizeRunCases(summary = {}) {
  const cases = Array.isArray(summary?.cases) ? summary.cases : []
  return cases.map((item, index) => ({
    key: item?.id ?? item?.case_id ?? index,
    name: item?.name || item?.case_name || item?.title || `用例 ${index + 1}`,
    status: item?.status || '',
    duration: Number(item?.duration_ms ?? item?.duration ?? 0) || 0,
    error: item?.error_message || item?.error || '',
    steps: Array.isArray(item?.steps) ? item.steps : [],
    raw: item,
  }))
}

/** WS/轮询状态归一。 */
export function normalizeTaskStatus(payload) {
  if (!payload || typeof payload !== 'object') return { status: '', progress: null, message: '' }
  const data = payload.data && typeof payload.data === 'object' ? payload.data : payload
  const rawStatus = data.status ?? data.task_status ?? data.run_status ?? ''
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

export function describeRunResult(state = {}) {
  const status = String(state?.status || '')
  if (status === 'passed') return '运行通过'
  if (status === 'failed') return '运行失败'
  if (status === 'error') return '运行异常'
  if (status === 'cancelled') return '运行已取消'
  return '运行结束'
}
