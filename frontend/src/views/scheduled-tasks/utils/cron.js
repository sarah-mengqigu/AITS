/**
 * 定时任务 Cron 相关的纯逻辑：预览响应归一化、中文描述兜底、选项字典。
 *
 * 后端契约（backend/apps/scheduled_tasks/views.py::CronViewSet）：
 * GET /api/scheduled-tasks/cron/preview/?expr=...&timezone=...&count=5
 * -> {valid, expression, description, next_runs: ["YYYY-MM-DD HH:MM:SS"], timezone, message}
 * 非法表达式不是 HTTP 错误，而是 valid=false + message，便于边输入边校验。
 */

export const SUITE_TYPE_OPTIONS = [
  { value: 'api', label: 'API 接口测试' },
  { value: 'web', label: 'Web UI 测试' },
  { value: 'app', label: '移动端 App 测试' },
]

export const TRIGGER_CONDITION_OPTIONS = [
  { value: 'always', label: '总是通知' },
  { value: 'fail', label: '仅失败时通知' },
]

export const TIMEZONE_OPTIONS = [
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Asia/Singapore',
  'UTC',
  'Europe/London',
  'America/New_York',
]

export const CRON_PRESETS = [
  { label: '每 5 分钟', expr: '*/5 * * * *' },
  { label: '每小时整点', expr: '0 * * * *' },
  { label: '每天 09:00', expr: '0 9 * * *' },
  { label: '每周一 09:00', expr: '0 9 * * 1' },
  { label: '每月 1 日 02:00', expr: '0 2 1 * *' },
]

export const SUITE_TYPE_LABELS = SUITE_TYPE_OPTIONS.reduce((acc, item) => {
  acc[item.value] = item.label
  return acc
}, {})

export const TRIGGER_CONDITION_LABELS = TRIGGER_CONDITION_OPTIONS.reduce((acc, item) => {
  acc[item.value] = item.label
  return acc
}, {})

export function suiteTypeLabel(value) {
  return SUITE_TYPE_LABELS[value] || value || '—'
}

export function triggerConditionLabel(value) {
  return TRIGGER_CONDITION_LABELS[value] || value || '—'
}

const WEEKDAY_LABELS = ['日', '一', '二', '三', '四', '五', '六', '日']

/** `2025-01-01 09:00:00` / `2025-01-01T09:00:00` → `2025-01-01 09:00`。 */
export function formatCronRun(value) {
  const text = String(value ?? '').trim()
  if (!text) return ''
  const match = text.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})/)
  if (match) return `${match[1]} ${match[2]}`
  return text
}

/**
 * 本地中文描述兜底：后端描述缺失/未就绪时仍能给出可读说明。
 * 只覆盖常见 5 字段表达式，其它返回空串（页面会提示手动确认）。
 */
export function describeCronLocally(expression) {
  const parts = String(expression ?? '')
    .trim()
    .split(/\s+/)
  if (parts.length !== 5) return ''
  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts
  const isNumber = (value) => /^\d+$/.test(value)
  const pad = (value) => String(value).padStart(2, '0')

  if (minute === '*' && hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
    return '每分钟执行'
  }
  const stepMatch = minute.match(/^\*\/(\d+)$/)
  if (stepMatch && hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
    return `每 ${Number(stepMatch[1])} 分钟执行`
  }
  if (isNumber(minute) && hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
    return `每小时第 ${Number(minute)} 分钟执行`
  }
  if (isNumber(minute) && isNumber(hour)) {
    const time = `${pad(hour)}:${pad(minute)}`
    if (dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
      return `每天 ${time} 执行`
    }
    if (dayOfMonth === '*' && month === '*' && dayOfWeek === '1-5') {
      return `每个工作日 ${time} 执行`
    }
    if (dayOfMonth === '*' && month === '*' && isNumber(dayOfWeek)) {
      return `每周${WEEKDAY_LABELS[Number(dayOfWeek) % 7]} ${time} 执行`
    }
    if (isNumber(dayOfMonth) && month === '*' && dayOfWeek === '*') {
      return `每月 ${Number(dayOfMonth)} 日 ${time} 执行`
    }
  }
  return ''
}

/**
 * 归一化 cron 预览响应，产出视图层直接可用的模型。
 * @param {object} payload 后端响应
 * @param {{ count?: number }} options 期望展示的未来执行次数（默认 5）
 */
export function normalizeCronPreview(payload = {}, { count = 5 } = {}) {
  const source = payload && typeof payload === 'object' ? payload : {}
  const valid = Boolean(source.valid)
  const expression = String(source.expression || '').trim()
  const nextRuns = Array.isArray(source.next_runs) ? source.next_runs : []
  const description = String(source.description || '').trim()

  return {
    valid,
    expression,
    description: valid ? description || describeCronLocally(expression) : '',
    message: String(source.message || '').trim() || (valid ? '' : '无效的 cron 表达式'),
    timezone: String(source.timezone || '').trim(),
    nextRuns: valid
      ? nextRuns
          .map(formatCronRun)
          .filter(Boolean)
          .slice(0, Math.max(Number(count) || 0, 0))
      : [],
  }
}

/** 简单防抖（返回包装后的函数与取消方法）。 */
export function debounce(fn, wait = 450) {
  let timer = null
  const wrapped = (...args) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      fn(...args)
    }, wait)
  }
  wrapped.cancel = () => {
    if (timer) clearTimeout(timer)
    timer = null
  }
  return wrapped
}
