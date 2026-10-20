import { describe, expect, it } from 'vitest'

import {
  buildLoadConfigPayload,
  buildReportFilename,
  buildScenarioPayload,
  buildScriptFilename,
  describeScenarioSource,
  errorRatePercent,
  formatErrorRate,
  formatLatency,
  formatSuccessRate,
  formatTps,
  getDiagnosisSourceMeta,
  getDiagnosisStatusMeta,
  getExecutionStatusMeta,
  getScenarioSourceMeta,
  getSeverityMeta,
  getTriggerTypeMeta,
  isExecutionTerminal,
  loadConfigToForm,
  normalizeDashboard,
  normalizeErrorRate,
  normalizeExecutionRow,
  normalizeStatusCodeDist,
  progressFromExecution,
  readErrorMessage,
  scenarioToForm,
  successRatePercent,
  validateCustomScript,
  validateJsonObject,
  validateLoadConfig,
  validateScenarioForm,
} from '@/views/performance/utils'
import {
  RANGE_OPTIONS,
  buildDiagnosisPieOption,
  buildErrorRateOption,
  buildExecutionTrendOption,
  buildTpsLatencyOption,
  buildTrendFromExecutions,
  executionTimestamp,
  filterExecutionsByRange,
  getRangeOption,
  normalizeExecutionRows,
  rangeToDays,
} from '@/views/monitoring/utils'

// ---------------------------------------------------------------------------
// 1. 状态 / 严重级别映射
// ---------------------------------------------------------------------------
describe('性能测试状态与严重级别映射', () => {
  it('执行状态：中文文案、el-tag 类型、终态判断与未知状态兜底', () => {
    expect(getExecutionStatusMeta('passed')).toMatchObject({
      label: '通过',
      tagType: 'success',
      terminal: true,
    })
    expect(getExecutionStatusMeta('RUNNING')).toMatchObject({
      label: '执行中',
      tagType: 'warning',
      terminal: false,
    })
    expect(getExecutionStatusMeta('failed')).toMatchObject({ label: '失败', tagType: 'danger' })
    expect(getExecutionStatusMeta('error')).toMatchObject({ label: '错误', tagType: 'danger' })
    expect(getExecutionStatusMeta('cancelled')).toMatchObject({ label: '已取消', tagType: 'info' })
    expect(getExecutionStatusMeta('custom_status')).toMatchObject({
      label: 'custom_status',
      tagType: 'info',
      terminal: false,
    })
    expect(getExecutionStatusMeta(undefined).label).toBe('未知')
    expect(isExecutionTerminal('passed')).toBe(true)
    expect(isExecutionTerminal('cancelled')).toBe(true)
    expect(isExecutionTerminal('pending')).toBe(false)
  })

  it('诊断状态 / 来源 / 触发方式 / 场景来源映射', () => {
    expect(getDiagnosisStatusMeta('pending')).toMatchObject({
      label: '待处理',
      tagType: 'warning',
    })
    expect(getDiagnosisStatusMeta('resolved')).toMatchObject({
      label: '已解决',
      tagType: 'success',
    })
    expect(getDiagnosisStatusMeta('ignored')).toMatchObject({ label: '已忽略', tagType: 'info' })
    expect(getDiagnosisStatusMeta('weird').label).toBe('weird')

    expect(getDiagnosisSourceMeta('grafana')).toMatchObject({
      label: 'Grafana 告警',
      tagType: 'warning',
    })
    expect(getDiagnosisSourceMeta('manual')).toMatchObject({ label: '手动诊断' })

    expect(getTriggerTypeMeta('scheduled')).toMatchObject({ label: '定时', tagType: 'warning' })
    expect(getTriggerTypeMeta('unknown').label).toBe('unknown')

    expect(getScenarioSourceMeta('api_suite')).toMatchObject({ label: 'API 套件' })
    expect(getScenarioSourceMeta('api_case')).toMatchObject({ label: 'API 用例' })
    expect(getScenarioSourceMeta('custom_script')).toMatchObject({ label: '自定义脚本' })
  })

  it('Grafana 严重级别：critical/warning/info 与未知值', () => {
    expect(getSeverityMeta('critical')).toMatchObject({
      label: '严重',
      tagType: 'danger',
      level: 4,
    })
    expect(getSeverityMeta('WARNING')).toMatchObject({ label: '警告', tagType: 'warning' })
    expect(getSeverityMeta('info')).toMatchObject({ label: '提示', tagType: 'info' })
    expect(getSeverityMeta('high')).toMatchObject({ label: '高', tagType: 'danger' })
    expect(getSeverityMeta('')).toMatchObject({ label: '未分级', tagType: 'info' })
    expect(getSeverityMeta('custom-sev')).toMatchObject({
      label: 'custom-sev',
      tagType: 'info',
    })
  })

  it('执行进度估算与边界收敛', () => {
    expect(progressFromExecution({ status: 'passed' })).toBe(100)
    expect(progressFromExecution({ status: 'running' })).toBe(55)
    expect(progressFromExecution({ status: 'pending' })).toBe(5)
    expect(progressFromExecution(null)).toBe(0)
    expect(progressFromExecution({ status: 'unknown' })).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// 2. TPS / P95 / 错误率格式化
// ---------------------------------------------------------------------------
describe('TPS / P95 / 错误率格式化', () => {
  it('TPS 保留两位小数，非法输入按 0 展示', () => {
    expect(formatTps(97.566)).toBe('97.57')
    expect(formatTps(0)).toBe('0.00')
    expect(formatTps(1234.5)).toBe('1,234.50')
    expect(formatTps(null)).toBe('0.00')
    expect(formatTps('abc')).toBe('0.00')
  })

  it('P95 延迟四舍五入并带毫秒单位，负数收敛为 0', () => {
    expect(formatLatency(228.4)).toBe('228 ms')
    expect(formatLatency(228.6)).toBe('229 ms')
    expect(formatLatency(1234.6)).toBe('1,235 ms')
    expect(formatLatency(-10)).toBe('0 ms')
    expect(formatLatency(null)).toBe('0 ms')
  })

  it('错误率（0..1 小数）转百分数并处理边界值', () => {
    expect(formatErrorRate(0.0021)).toBe('0.21%')
    expect(formatErrorRate(0)).toBe('0.00%')
    expect(formatErrorRate(1)).toBe('100.00%')
    expect(formatErrorRate(1.5)).toBe('100.00%')
    expect(formatErrorRate(-1)).toBe('0.00%')
    expect(formatErrorRate(null)).toBe('0.00%')
    expect(normalizeErrorRate('0.5')).toBe(0.5)
    expect(normalizeErrorRate('bad')).toBe(0)

    expect(errorRatePercent(0.0021)).toBe(0.21)
  })
})

// ---------------------------------------------------------------------------
// 3. 成功率 / 错误率边界
// ---------------------------------------------------------------------------
describe('成功率 / 错误率边界', () => {
  it('成功率为 100 - 错误率，且始终落在 0..100', () => {
    expect(successRatePercent(0)).toBe(100)
    expect(successRatePercent(0.0021)).toBe(99.79)
    expect(successRatePercent(0.3)).toBe(70)
    expect(successRatePercent(1)).toBe(0)
    expect(successRatePercent(1.5)).toBe(0)
    expect(successRatePercent(-0.5)).toBe(100)
    expect(successRatePercent(null)).toBe(100)
  })

  it('成功率文案保留两位小数', () => {
    expect(formatSuccessRate(0)).toBe('100.00%')
    expect(formatSuccessRate(0.0021)).toBe('99.79%')
    expect(formatSuccessRate(0.5)).toBe('50.00%')
    expect(formatSuccessRate(2)).toBe('0.00%')
  })
})

// ---------------------------------------------------------------------------
// 4. dashboard 数据转换
// ---------------------------------------------------------------------------
describe('dashboard 数据转换（summary / trend / recent / diagnosis）', () => {
  const payload = {
    days: 7,
    range: { start: '2026-10-13T10:00:00+00:00', end: '2026-10-20T10:00:00+00:00' },
    summary: {
      executions: 3,
      passed: 2,
      failed: 1,
      error: 0,
      cancelled: 0,
      running: 0,
      pending: 0,
      avg_tps: 97.566,
      avg_p95: 228.4,
      avg_p99: 300,
      avg_error_rate: 0.0021,
      total_requests: 5854,
    },
    trend: [
      {
        date: '2026-10-19',
        executions: 0,
        passed: 0,
        failed: 0,
        avg_tps: 0,
        avg_p95: 0,
        avg_error_rate: 0,
      },
      {
        date: '2026-10-20',
        executions: 3,
        passed: 0,
        failed: 1,
        avg_tps: 97.566,
        avg_p95: 228.4,
        avg_error_rate: 0.0021,
      },
    ],
    recent_executions: [
      {
        id: 4,
        name: '商品列表压测 20261020-173603',
        status: 'passed',
        status_label: '通过',
        scenario_id: 4,
        scenario_name: '商品列表压测',
        trigger_type: 'manual',
        avg_tps: 97.57,
        p95_response_time: 228,
        error_rate: 0.0021,
        total_requests: 5854,
        created_at: '2026-10-20T09:36:03.167561+00:00',
      },
    ],
    diagnosis: { total: 4, pending: 1, resolved: 2, ignored: 1, by_severity: { critical: 1, warning: 3 } },
  }

  it('summary 字段转换为 camelCase，失败数包含 error', () => {
    const result = normalizeDashboard(payload)
    expect(result.days).toBe(7)
    expect(result.summary).toMatchObject({
      executions: 3,
      passed: 2,
      failed: 1,
      error: 0,
      failedTotal: 1,
      avgTps: 97.566,
      avgP95: 228.4,
      avgP99: 300,
      avgErrorRate: 0.0021,
      totalRequests: 5854,
    })
    expect(result.hasData).toBe(true)
  })

  it('trend 用 executions - failed 推导通过数，并保留后端指标', () => {
    const result = normalizeDashboard(payload)
    expect(result.trend).toHaveLength(2)
    expect(result.trend[0]).toMatchObject({ date: '2026-10-19', executions: 0, passed: 0 })
    expect(result.trend[1]).toMatchObject({
      date: '2026-10-20',
      executions: 3,
      passed: 2,
      failed: 1,
      avgTps: 97.566,
      avgP95: 228.4,
      avgErrorRate: 0.0021,
    })
  })

  it('recent_executions 补充状态 / 触发的展示元信息', () => {
    const result = normalizeDashboard(payload)
    expect(result.recentExecutions[0]).toMatchObject({
      id: 4,
      name: '商品列表压测 20261020-173603',
      status: 'passed',
      statusLabel: '通过',
      statusTagType: 'success',
      triggerLabel: '手动',
      avgTps: 97.57,
      p95: 228,
      errorRate: 0.0021,
      totalRequests: 5854,
    })
  })

  it('diagnosis 统计与严重级别分布转换', () => {
    const result = normalizeDashboard(payload)
    expect(result.diagnosis).toMatchObject({
      total: 4,
      pending: 1,
      resolved: 2,
      ignored: 1,
    })
    expect(result.diagnosis.bySeverity).toEqual({ critical: 1, warning: 3 })
  })

  it('空响应 / 异常结构降级为 0 与空数组，不抛错', () => {
    const empty = normalizeDashboard({})
    expect(empty.summary.executions).toBe(0)
    expect(empty.summary.failedTotal).toBe(0)
    expect(empty.trend).toEqual([])
    expect(empty.recentExecutions).toEqual([])
    expect(empty.diagnosis).toEqual({
      total: 0,
      pending: 0,
      resolved: 0,
      ignored: 0,
      bySeverity: {},
    })
    expect(empty.hasData).toBe(false)

    const nullResult = normalizeDashboard(null)
    expect(nullResult.summary.executions).toBe(0)
    expect(nullResult.days).toBe(7)
  })

  it('单条执行记录转换兼容 snake_case 与状态兜底', () => {
    const row = normalizeExecutionRow({
      id: 9,
      name: '',
      status: 'error',
      trigger_type: 'api',
      avg_tps: '12.345',
      p95_response_time: '88.8',
      error_rate: 0.2,
      total_requests: 30,
      created_at: '2026-10-20 17:36:03',
    })
    expect(row).toMatchObject({
      id: 9,
      name: '未命名执行',
      status: 'error',
      statusLabel: '错误',
      triggerLabel: 'API 调用',
      avgTps: 12.345,
      p95: 88.8,
      errorRate: 0.2,
      totalRequests: 30,
    })
  })
})

// ---------------------------------------------------------------------------
// 5. 场景来源 / 脚本 / 表单校验
// ---------------------------------------------------------------------------
describe('性能场景来源与脚本校验', () => {
  const validSuiteForm = {
    name: '商品列表压测',
    description: '核心链路',
    source_type: 'api_suite',
    source_suite: 6,
    source_case: null,
    custom_script: '',
    endpoint_count: 16,
    config: 4,
    variablesText: '{"host": "https://demo.aits.local"}',
    is_active: true,
  }

  it('api_suite 必须选择来源套件，payload 归一化', () => {
    const valid = validateScenarioForm(validSuiteForm)
    expect(valid.valid).toBe(true)
    expect(valid.payload).toMatchObject({
      name: '商品列表压测',
      source_type: 'api_suite',
      source_suite: 6,
      source_case: null,
      config: 4,
      endpoint_count: 16,
      variables: { host: 'https://demo.aits.local' },
      is_active: true,
    })
    expect(buildScenarioPayload(validSuiteForm).custom_script).toBe('')

    const missing = validateScenarioForm({ ...validSuiteForm, source_suite: null })
    expect(missing.valid).toBe(false)
    expect(missing.fieldErrors.source_suite).toContain('API 套件')

    const blankName = validateScenarioForm({ ...validSuiteForm, name: '  ' })
    expect(blankName.valid).toBe(false)
    expect(blankName.fieldErrors.name).toContain('场景名称')
  })

  it('api_case 必须选择来源用例，source_suite 置空', () => {
    const form = {
      ...validSuiteForm,
      source_type: 'api_case',
      source_suite: 6,
      source_case: 49,
    }
    const result = validateScenarioForm(form)
    expect(result.valid).toBe(true)
    expect(result.payload.source_case).toBe(49)
    expect(result.payload.source_suite).toBeNull()

    const missing = validateScenarioForm({ ...form, source_case: null })
    expect(missing.valid).toBe(false)
    expect(missing.fieldErrors.source_case).toContain('API 用例')
  })

  it('custom_script 必填、必须包含 HttpUser，其他来源忽略脚本', () => {
    expect(validateCustomScript('')).toMatchObject({ valid: false, hasHttpUser: false })
    expect(validateCustomScript('   ').message).toContain('不能为空')
    expect(validateCustomScript('class Demo: pass').valid).toBe(false)
    expect(validateCustomScript('class Demo: pass').message).toContain('HttpUser')

    const script = 'from locust import HttpUser, task\n\nclass DemoUser(HttpUser):\n    @task\n    def index(self):\n        self.client.get("/")'
    expect(validateCustomScript(script)).toMatchObject({ valid: true, hasHttpUser: true })

    const form = {
      ...validSuiteForm,
      source_type: 'custom_script',
      source_suite: null,
      custom_script: '',
    }
    expect(validateScenarioForm(form).valid).toBe(false)
    expect(validateScenarioForm({ ...form, custom_script: script }).valid).toBe(true)
    expect(validateScenarioForm({ ...form, custom_script: script }).payload.custom_script).toBe(script)

    // 非 custom_script 来源不会把脚本提交给后端
    expect(buildScenarioPayload({ ...validSuiteForm, custom_script: script }).custom_script).toBe('')
  })

  it('变量必须为 JSON 对象，接口数量必须为非负整数', () => {
    const badVariables = validateScenarioForm({ ...validSuiteForm, variablesText: '[]' })
    expect(badVariables.valid).toBe(false)
    expect(badVariables.fieldErrors.variablesText).toContain('JSON 对象')

    const badCount = validateScenarioForm({ ...validSuiteForm, endpoint_count: -1 })
    expect(badCount.valid).toBe(false)
    expect(badCount.fieldErrors.endpoint_count).toContain('非负整数')

    const unknownSource = validateScenarioForm({ ...validSuiteForm, source_type: 'script' })
    expect(unknownSource.valid).toBe(false)
    expect(unknownSource.fieldErrors.source_type).toContain('来源类型')
  })

  it('脚本下载文件名与来源文案', () => {
    expect(buildScriptFilename({ name: '商品列表压测' })).toBe('locustfile-商品列表压测.py')
    expect(buildScriptFilename({ name: '商品/列表 压测' })).toBe('locustfile-商品-列表-压测.py')
    expect(buildScriptFilename({})).toBe('locustfile-scenario.py')
    expect(buildReportFilename({ id: 4 })).toBe('performance-report-4.json')
    expect(buildReportFilename({})).toBe('performance-report-unknown.json')

    expect(describeScenarioSource({ source_type: 'api_suite', source_suite_name: '商品回归' })).toBe(
      '商品回归',
    )
    expect(describeScenarioSource({ source_type: 'api_case', source_case: 49 })).toBe('用例 #49')
    expect(
      describeScenarioSource({ source_type: 'custom_script', custom_script: 'class U(HttpUser): pass' }),
    ).toBe('自定义 Locust 脚本')
  })

  it('编辑行 ↔ 表单模型互转', () => {
    const form = scenarioToForm({
      name: '商品压测',
      source_type: 'custom_script',
      variables: { host: 'https://a.b' },
      is_active: false,
    })
    expect(form.variablesText).toContain('"host"')
    expect(form.source_type).toBe('custom_script')
    expect(form.is_active).toBe(false)

    const configForm = loadConfigToForm({ users: 50, spawn_rate: 5, config: { users: 100 } })
    expect(configForm.users).toBe(50)
    expect(configForm.configText).toContain('"users": 100')
    expect(loadConfigToForm({}).configText).toBe('{}')
  })
})

// ---------------------------------------------------------------------------
// 6. 负载配置 / JSON 校验
// ---------------------------------------------------------------------------
describe('负载配置与 JSON 校验', () => {
  const validForm = {
    name: '基线 50 并发',
    users: 50,
    spawn_rate: 5,
    duration_seconds: 60,
    host: 'https://demo.aits.local',
    configText: '{"users": 100}',
    description: '演示',
  }

  it('合法配置生成后端 payload', () => {
    const result = validateLoadConfig(validForm)
    expect(result.valid).toBe(true)
    expect(result.payload).toEqual({
      name: '基线 50 并发',
      users: 50,
      spawn_rate: 5,
      duration_seconds: 60,
      host: 'https://demo.aits.local',
      config: { users: 100 },
      description: '演示',
    })
    expect(buildLoadConfigPayload({ ...validForm, configText: '' }).config).toEqual({})
  })

  it('users / duration 为正整数，spawn_rate 必须大于 0', () => {
    expect(validateLoadConfig({ ...validForm, users: 0 }).fieldErrors.users).toContain('正整数')
    expect(validateLoadConfig({ ...validForm, users: 1.5 }).fieldErrors.users).toContain('正整数')
    expect(validateLoadConfig({ ...validForm, duration_seconds: 0 }).fieldErrors.duration_seconds)
      .toContain('正整数')
    expect(validateLoadConfig({ ...validForm, spawn_rate: 0 }).fieldErrors.spawn_rate)
      .toContain('大于 0')
    expect(validateLoadConfig({ ...validForm, spawn_rate: -1 }).valid).toBe(false)
  })

  it('host 必须为 http(s) URL（留空允许），JSON 必须为对象', () => {
    expect(validateLoadConfig({ ...validForm, host: '' }).valid).toBe(true)
    expect(validateLoadConfig({ ...validForm, host: 'demo.local' }).fieldErrors.host)
      .toContain('http(s)')
    expect(validateLoadConfig({ ...validForm, configText: '[1, 2]' }).fieldErrors.configText)
      .toContain('JSON 对象')
    expect(validateLoadConfig({ ...validForm, configText: '{oops}' }).valid).toBe(false)
    expect(validateLoadConfig({ ...validForm, name: ' ' }).fieldErrors.name).toContain('不能为空')
  })

  it('validateJsonObject 区分空值 / 合法对象 / 数组 / 非法 JSON', () => {
    expect(validateJsonObject('').valid).toBe(true)
    expect(validateJsonObject('').value).toEqual({})
    expect(validateJsonObject('', { allowEmpty: false }).valid).toBe(false)
    expect(validateJsonObject('{"a": 1}')).toMatchObject({
      valid: true,
      value: { a: 1 },
      empty: false,
    })
    expect(validateJsonObject('[]').valid).toBe(false)
    expect(validateJsonObject('[]').message).toContain('JSON 对象')
    expect(validateJsonObject('{bad').message).toContain('不是合法 JSON')
  })
})

// ---------------------------------------------------------------------------
// 7. 状态码分布
// ---------------------------------------------------------------------------
describe('状态码分布转换', () => {
  it('按状态码升序并计算占比', () => {
    const rows = normalizeStatusCodeDist({ 500: 1, 200: 9, 302: 2 }, 12)
    expect(rows.map((row) => row.code)).toEqual(['200', '302', '500'])
    expect(rows[0]).toMatchObject({ code: '200', count: 9, percent: 75 })
    expect(rows[1].percent).toBeCloseTo(16.67, 2)
    expect(rows[2].percent).toBeCloseTo(8.33, 2)
  })

  it('总数为 0 时占比为 0，非法输入返回空数组', () => {
    expect(normalizeStatusCodeDist({}, 0)).toEqual([])
    expect(normalizeStatusCodeDist(null, 10)).toEqual([])
    expect(normalizeStatusCodeDist({ 200: 0 }, 0)).toEqual([
      { code: '200', count: 0, percent: 0 },
    ])
  })
})

// ---------------------------------------------------------------------------
// 8. 监控时间范围与趋势分桶
// ---------------------------------------------------------------------------
describe('监控大盘时间范围与前端趋势分桶', () => {
  const now = new Date(2026, 9, 20, 12, 0, 0).getTime()

  it('时间范围映射到 dashboard days，未知 key 兜底 24h', () => {
    expect(RANGE_OPTIONS.map((option) => option.key)).toEqual(['1h', '6h', '24h', '7d'])
    expect(getRangeOption('1h')).toMatchObject({ days: 1, hours: 1, buckets: 12 })
    expect(getRangeOption('7d')).toMatchObject({ days: 7, hours: 0 })
    expect(getRangeOption('unknown').key).toBe('24h')
    expect(rangeToDays('7d')).toBe(7)
    expect(rangeToDays('6h')).toBe(1)
  })

  it('按时间窗口过滤执行记录', () => {
    const executions = [
      { id: 1, createdAt: '2026-10-20 11:30:00', status: 'passed' },
      { id: 2, createdAt: '2026-10-20 09:00:00', status: 'failed' },
      { id: 3, createdAt: 'not-a-date', status: 'passed' },
    ]
    const filtered = filterExecutionsByRange(executions, '1h', now)
    expect(filtered.map((row) => row.id)).toEqual([1])
    expect(filterExecutionsByRange(executions, '24h', now).map((row) => row.id)).toEqual([1, 2])
    expect(filterExecutionsByRange(executions, '7d', now)).toHaveLength(3)
    expect(executionTimestamp(executions[0])).toBeLessThan(now)
    expect(executionTimestamp({})).toBeNull()
  })

  it('buildTrendFromExecutions 生成 12 个小时桶并聚合通过 / 失败 / TPS / P95', () => {
    const executions = [
      {
        id: 1,
        status: 'passed',
        avgTps: 100,
        p95: 200,
        errorRate: 0.01,
        createdAt: '2026-10-20 11:58:00',
      },
      {
        id: 2,
        status: 'failed',
        avgTps: 50,
        p95: 400,
        errorRate: 0.05,
        createdAt: '2026-10-20 11:22:00',
      },
      {
        id: 3,
        status: 'passed',
        avgTps: 999,
        p95: 999,
        errorRate: 0.99,
        createdAt: '2026-10-20 06:00:00',
      },
    ]
    const trend = buildTrendFromExecutions(executions, '1h', now)
    expect(trend).toHaveLength(12)
    expect(trend[0].label).toMatch(/^\d{2}:\d{2}$/)
    expect(buildTrendFromExecutions([], '24h', now)[0].label).toMatch(
      /^\d{2}-\d{2} \d{2}:\d{2}$/,
    )
    expect(trend.reduce((acc, row) => acc + row.executions, 0)).toBe(2)

    const last = trend[11]
    expect(last).toMatchObject({
      executions: 1,
      passed: 1,
      failed: 0,
      avgTps: 100,
      avgP95: 200,
      avgErrorRate: 0.01,
    })
    const failedBucket = trend.find((row) => row.failed === 1)
    expect(failedBucket).toMatchObject({
      executions: 1,
      passed: 0,
      failed: 1,
      avgTps: 50,
      avgP95: 400,
      avgErrorRate: 0.05,
    })
  })

  it('normalizeExecutionRows 统一转换并按时间倒序', () => {
    const rows = normalizeExecutionRows([
      { id: 1, status: 'passed', created_at: '2026-10-20 10:00:00', avg_tps: 10 },
      { id: 2, status: 'failed', created_at: '2026-10-20 11:00:00', avg_tps: 20 },
      null,
    ])
    expect(rows.map((row) => row.id)).toEqual([2, 1])
    expect(rows[0]).toMatchObject({ status: 'failed', statusLabel: '失败', avgTps: 20 })
  })
})

// ---------------------------------------------------------------------------
// 9. 监控图表 option
// ---------------------------------------------------------------------------
describe('监控大盘图表 option 结构', () => {
  const trend = [
    { date: '2026-10-19', executions: 0, passed: 0, failed: 0, avgTps: 0, avgP95: 0, avgErrorRate: 0 },
    { date: '2026-10-20', executions: 3, passed: 2, failed: 1, avgTps: 97.5, avgP95: 228, avgErrorRate: 0.0021 },
  ]

  it('执行趋势为执行数 + 通过/失败堆叠折线', () => {
    const option = buildExecutionTrendOption(trend)
    expect(option.series.map((item) => item.name)).toEqual(['执行数', '失败', '通过'])
    expect(option.series[1].stack).toBe('result')
    expect(option.series[2].stack).toBe('result')
    expect(option.series[0].data).toEqual([0, 3])
    expect(option.series[2].data).toEqual([0, 2])
    expect(option.xAxis.data).toEqual(['2026-10-19', '2026-10-20'])
  })

  it('TPS/P95 使用双 Y 轴，错误率使用百分数', () => {
    const option = buildTpsLatencyOption(trend)
    expect(Array.isArray(option.yAxis)).toBe(true)
    expect(option.yAxis).toHaveLength(2)
    expect(option.series[1].yAxisIndex).toBe(1)
    expect(option.series[0].data).toEqual([0, 97.5])

    const errorOption = buildErrorRateOption(trend)
    expect(errorOption.series[0].data).toEqual([0, 0.21])
    expect(errorOption.yAxis.axisLabel.formatter).toBe('{value}%')
    expect(errorOption.yAxis.max).toBeGreaterThanOrEqual(1)
  })

  it('诊断状态饼图包含 pending / resolved / ignored', () => {
    const option = buildDiagnosisPieOption({ pending: 1, resolved: 2, ignored: 1, total: 4 })
    expect(option.series[0].data.map((item) => item.name)).toEqual(['待处理', '已解决', '已忽略'])
    expect(option.series[0].data.map((item) => item.value)).toEqual([1, 2, 1])
  })
})

// ---------------------------------------------------------------------------
// 10. 错误信息提取
// ---------------------------------------------------------------------------
describe('可读错误信息提取', () => {
  it('优先读取后端 message / detail，最后回退 error.message', () => {
    expect(readErrorMessage({ response: { data: { message: '后端业务错误' } } })).toBe(
      '后端业务错误',
    )
    expect(readErrorMessage({ response: { data: { detail: '详情错误' } } })).toBe('详情错误')
    expect(readErrorMessage({ response: { data: '纯文本错误' } })).toBe('纯文本错误')
    expect(readErrorMessage({ message: '网络错误' })).toBe('网络错误')
    expect(readErrorMessage(null, '兜底文案')).toBe('兜底文案')
    expect(readErrorMessage(undefined)).toContain('操作失败')
  })
})
