import dayjs from 'dayjs'

/** 通用格式化与枚举映射工具（页面/表格/状态标签统一使用）。 */

export const EMPTY_TEXT = '—'

const isBlank = (value) =>
  value === null || value === undefined || value === '' || (typeof value === 'number' && Number.isNaN(value))

export function formatDate(value, template = 'YYYY-MM-DD') {
  if (isBlank(value)) return EMPTY_TEXT
  const date = dayjs(value)
  return date.isValid() ? date.format(template) : EMPTY_TEXT
}

export function formatDateTime(value, template = 'YYYY-MM-DD HH:mm:ss') {
  return formatDate(value, template)
}

export function formatTime(value) {
  return formatDate(value, 'HH:mm:ss')
}

/** 0-100 的百分比数值（后端 pass_rate 约定为百分数）。 */
export function formatPercent(value, digits = 1) {
  if (isBlank(value)) return EMPTY_TEXT
  const number = Number(value)
  if (!Number.isFinite(number)) return EMPTY_TEXT
  return `${number.toFixed(digits)}%`
}

export function formatNumber(value, digits = 0) {
  if (isBlank(value)) return EMPTY_TEXT
  const number = Number(value)
  if (!Number.isFinite(number)) return EMPTY_TEXT
  return number.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/** 毫秒 → 可读时长：850 ms / 1.25 s / 2 min 3 s。 */
export function formatDuration(value) {
  if (isBlank(value)) return EMPTY_TEXT
  const ms = Number(value)
  if (!Number.isFinite(ms) || ms < 0) return EMPTY_TEXT
  if (ms < 1000) return `${Math.round(ms)} ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds.toFixed(2)} s`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  if (minutes < 60) return `${minutes} min ${rest} s`
  const hours = Math.floor(minutes / 60)
  return `${hours} h ${minutes % 60} min`
}

/** 字节 → B / KB / MB / GB。 */
export function formatBytes(value, digits = 1) {
  if (isBlank(value)) return EMPTY_TEXT
  const bytes = Number(value)
  if (!Number.isFinite(bytes) || bytes < 0) return EMPTY_TEXT
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB', 'PB']
  let size = bytes / 1024
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(digits)} ${units[index]}`
}

/** 相对时间：刚刚 / 5 分钟前 / 3 小时前 / 日期。 */
export function formatRelativeTime(value) {
  if (isBlank(value)) return EMPTY_TEXT
  const date = dayjs(value)
  if (!date.isValid()) return EMPTY_TEXT
  const diffSeconds = dayjs().diff(date, 'second')
  if (diffSeconds < 60) return '刚刚'
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)} 分钟前`
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)} 小时前`
  if (diffSeconds < 86400 * 7) return `${Math.floor(diffSeconds / 86400)} 天前`
  return formatDateTime(value, 'YYYY-MM-DD HH:mm')
}

/** 执行/任务状态 → 中文文案。 */
export const STATUS_TEXT = {
  pending: '待执行',
  queued: '排队中',
  running: '执行中',
  passed: '通过',
  failed: '失败',
  error: '错误',
  cancelled: '已取消',
  canceled: '已取消',
  skipped: '跳过',
  success: '成功',
  failed_send: '发送失败',
  active: '启用',
  inactive: '禁用',
  enabled: '启用',
  disabled: '禁用',
  indexed: '已索引',
  processing: '索引中',
  resolved: '已解决',
  ignored: '已忽略',
  waiting: '等待中',
  success_send: '发送成功',
}

/** 状态 → Element Plus el-tag 的 type。 */
export const STATUS_TAG_TYPE = {
  pending: 'info',
  queued: 'info',
  running: 'warning',
  passed: 'success',
  failed: 'danger',
  error: 'danger',
  cancelled: 'info',
  canceled: 'info',
  skipped: 'info',
  success: 'success',
  active: 'success',
  inactive: 'info',
  enabled: 'success',
  disabled: 'info',
  indexed: 'success',
  processing: 'warning',
  resolved: 'success',
  ignored: 'info',
  waiting: 'info',
}

/** 状态 → 颜色 hex（用于图表/圆点）。 */
export const STATUS_COLOR = {
  pending: '#94a3b8',
  queued: '#94a3b8',
  running: '#f59e0b',
  passed: '#16a34a',
  failed: '#dc2626',
  error: '#dc2626',
  cancelled: '#64748b',
  canceled: '#64748b',
  skipped: '#94a3b8',
  success: '#16a34a',
  active: '#16a34a',
  inactive: '#94a3b8',
  indexed: '#16a34a',
  processing: '#f59e0b',
  resolved: '#16a34a',
  ignored: '#94a3b8',
}

export function getStatusText(status, fallback = '未知') {
  if (isBlank(status)) return fallback
  return STATUS_TEXT[status] || String(status)
}

export function getStatusTagType(status) {
  if (isBlank(status)) return 'info'
  return STATUS_TAG_TYPE[status] || 'info'
}

export function getStatusColor(status) {
  if (isBlank(status)) return '#94a3b8'
  return STATUS_COLOR[status] || '#94a3b8'
}

// ---------------------------------------------------------------------------
// 业务枚举文案（项目 / 环境 / 角色 / 测试类型）
// ---------------------------------------------------------------------------

export const PROJECT_TYPE_TEXT = {
  api: 'API 接口测试',
  web: 'Web UI 测试',
  app: '移动端 App 测试',
  perf: '性能测试',
}

export const PROJECT_TYPE_TAG_TYPE = {
  api: 'primary',
  web: 'success',
  app: 'warning',
  perf: 'danger',
}

export const PROJECT_ROLE_TEXT = {
  owner: '拥有者',
  admin: '管理员',
  editor: '编辑',
  viewer: '只读',
}

export const ENVIRONMENT_TYPE_TEXT = {
  dev: '开发环境',
  test: '测试环境',
  staging: '预发布环境',
  prod: '生产环境',
  custom: '自定义',
}

export const TEST_TYPE_TEXT = {
  positive: '正向',
  negative: '异常',
  boundary: '边界',
  security: '安全',
  performance: '性能',
}

export const SOURCE_TEXT = {
  manual: '手工',
  ai: 'AI 生成',
  postman: 'Postman',
}

export function getProjectTypeText(type) {
  return PROJECT_TYPE_TEXT[type] || type || EMPTY_TEXT
}

export function getRoleText(role) {
  return PROJECT_ROLE_TEXT[role] || role || EMPTY_TEXT
}

export function getEnvironmentTypeText(type) {
  return ENVIRONMENT_TYPE_TEXT[type] || type || EMPTY_TEXT
}
