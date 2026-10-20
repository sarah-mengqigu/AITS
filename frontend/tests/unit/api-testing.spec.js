import { describe, expect, it } from 'vitest'

import {
  ASSERTION_TYPE_OPTIONS,
  EXECUTION_STATUS_OPTIONS,
  METHOD_META,
  buildAssertionsPayload,
  buildReportFilename,
  buildRequestConfig,
  clampProgress,
  formatJsonText,
  getAssertionTypeForOperator,
  getCaseTypeLabel,
  getExecutionStatusLabel,
  getExecutionStatusMeta,
  getExecutionStatusTagType,
  getMethodColor,
  getMethodLabel,
  getMethodMeta,
  getMethodTagType,
  getOperatorForAssertionType,
  getPriorityMeta,
  getSpecSourceLabel,
  getSpecStatusMeta,
  getTestTypeLabel,
  getTriggerTypeMeta,
  isExecutionTerminal,
  isValidHttpUrl,
  isValidRequestUrl,
  normalizeAssertionRows,
  normalizeReport,
  normalizeReportCases,
  progressFromExecution,
  requestConfigToForm,
  summarizeGeneratedCases,
  validateAssertionRows,
  validateJsonText,
  validateSpecContent,
} from '@/views/api-testing/utils'

describe('HTTP method 标签颜色与状态映射', () => {
  it('按 method 返回 el-tag 类型与主色，大小写不敏感', () => {
    expect(getMethodTagType('get')).toBe('success')
    expect(getMethodTagType('POST')).toBe('primary')
    expect(getMethodTagType('Delete')).toBe('danger')
    expect(getMethodTagType('put')).toBe('warning')
    expect(getMethodTagType('patch')).toBe('warning')
    expect(getMethodTagType('options')).toBe('info')
    expect(getMethodColor('get')).toBe(METHOD_META.get.color)
    expect(getMethodColor('delete')).toBe('#dc2626')
    expect(getMethodLabel('get')).toBe('GET')
    expect(getMethodLabel('patch')).toBe('PATCH')
  })

  it('未知 / 空 method 兜底 info，且不抛异常', () => {
    expect(getMethodMeta('custom').tagType).toBe('info')
    expect(getMethodMeta('custom').label).toBe('CUSTOM')
    expect(getMethodMeta(undefined).label).toBe('—')
    expect(getMethodTagType(null)).toBe('info')
    expect(getMethodColor('')).toBe('#94a3b8')
  })

  it('执行状态映射覆盖终态判断与未知状态', () => {
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
    expect(getExecutionStatusLabel('failed')).toBe('失败')
    expect(getExecutionStatusTagType('cancelled')).toBe('info')
    expect(getExecutionStatusMeta('custom_status')).toMatchObject({
      label: 'custom_status',
      tagType: 'info',
      terminal: false,
    })
    expect(EXECUTION_STATUS_OPTIONS.map((item) => item.value)).not.toContain('skipped')
    expect(isExecutionTerminal('passed')).toBe(true)
    expect(isExecutionTerminal('failed')).toBe(true)
    expect(isExecutionTerminal('pending')).toBe(false)
  })

  it('进度估算：终态 100，执行中按已执行数量，避免提前 100%', () => {
    expect(progressFromExecution({ status: 'passed', total: 4 })).toBe(100)
    expect(progressFromExecution({ status: 'running', total: 10, passed: 3, failed: 2 })).toBe(50)
    expect(progressFromExecution({ status: 'running', total: 0 })).toBe(10)
    expect(progressFromExecution({ status: 'pending', total: 0 })).toBe(0)
    expect(progressFromExecution(null)).toBe(0)
    expect(progressFromExecution({ status: 'running', total: 1, passed: 1 })).toBe(99)
    expect(clampProgress(120)).toBe(100)
    expect(clampProgress(-5)).toBe(0)
    expect(clampProgress('42.6')).toBe(43)
    expect(clampProgress('abc')).toBe(0)
  })

  it('触发方式、用例类型、优先级等枚举映射', () => {
    expect(getTriggerTypeMeta('scheduled')).toMatchObject({ label: '定时', tagType: 'warning' })
    expect(getTriggerTypeMeta('unknown').label).toBe('unknown')
    expect(getCaseTypeLabel('scenario')).toBe('场景')
    expect(getCaseTypeLabel('endpoint')).toBe('单接口')
    expect(getTestTypeLabel('security')).toBe('安全')
    expect(getPriorityMeta(1)).toMatchObject({ label: 'P1 高', tagType: 'danger' })
    expect(getPriorityMeta(9).label).toBe('P9')
  })
})

describe('请求配置 JSON 校验函数', () => {
  it('validateJsonText 区分合法 / 非法 / 空值', () => {
    const valid = validateJsonText('{"a": 1, "b": [2]}')
    expect(valid).toMatchObject({ valid: true, empty: false, message: '' })
    expect(valid.value).toEqual({ a: 1, b: [2] })

    const invalid = validateJsonText('{a: 1}')
    expect(invalid.valid).toBe(false)
    expect(invalid.message).toContain('不是合法 JSON')

    expect(validateJsonText('').valid).toBe(true)
    expect(validateJsonText('   ').empty).toBe(true)
    expect(validateJsonText('', { allowEmpty: false }).valid).toBe(false)
  })

  it('formatJsonText 格式化成功，失败时保留原文', () => {
    const ok = formatJsonText('{"a":1}')
    expect(ok.ok).toBe(true)
    expect(ok.text).toContain('"a": 1')
    const bad = formatJsonText('{oops}')
    expect(bad.ok).toBe(false)
    expect(bad.text).toBe('{oops}')
    expect(bad.message).toContain('JSON 格式不合法')
  })

  it('URL 校验允许相对路径与 http(s) 完整地址', () => {
    expect(isValidRequestUrl('/api/users')).toBe(true)
    expect(isValidRequestUrl('https://api.example.com/users')).toBe(true)
    expect(isValidRequestUrl('api/users')).toBe(false)
    expect(isValidRequestUrl('ftp://api.example.com')).toBe(false)
    expect(isValidRequestUrl('')).toBe(false)
    expect(isValidHttpUrl('http://127.0.0.1:8000/api')).toBe(true)
    expect(isValidHttpUrl('/api')).toBe(false)
  })

  it('buildRequestConfig 构建后端 request_config，并返回字段级错误', () => {
    const result = buildRequestConfig({
      method: 'post',
      url: '/api/users',
      paramsText: '{"page": 1}',
      headersText: '{"Content-Type": "application/json"}',
      bodyText: '{"name": "demo"}',
    })
    expect(result.ok).toBe(true)
    expect(result.config).toEqual({
      method: 'POST',
      url: '/api/users',
      params: { page: 1 },
      headers: { 'Content-Type': 'application/json' },
      body: { mode: 'raw', json: { name: 'demo' } },
    })

    const badJson = buildRequestConfig({
      method: 'GET',
      url: '/api/users',
      paramsText: '{bad}',
      headersText: '[]',
      bodyText: '{}',
    })
    expect(badJson.ok).toBe(false)
    expect(badJson.fieldErrors.params).toContain('不是合法 JSON')
    expect(badJson.fieldErrors.headers).toContain('必须是 JSON 对象')
    expect(badJson.errors.length).toBeGreaterThanOrEqual(2)

    const missingUrl = buildRequestConfig({ method: 'GET', url: '' })
    expect(missingUrl.ok).toBe(false)
    expect(missingUrl.errors[0]).toContain('URL 不能为空')

    const invalidUrl = buildRequestConfig({ method: 'GET', url: 'api/users' })
    expect(invalidUrl.ok).toBe(false)
    expect(invalidUrl.errors[0]).toContain('需以 / 开头')

    const empty = buildRequestConfig({ method: 'get', url: '/api/health' })
    expect(empty.config).toEqual({ method: 'GET', url: '/api/health' })
    expect(empty.config.params).toBeUndefined()
    expect(empty.config.body).toBeUndefined()
  })

  it('requestConfigToForm 与 buildRequestConfig 可往返', () => {
    const form = requestConfigToForm({
      method: 'put',
      url: '/api/orders/1',
      params: { debug: true },
      headers: { 'X-Token': '${token}' },
      body: { mode: 'raw', json: { qty: 2 } },
    })
    expect(form.method).toBe('PUT')
    expect(form.url).toBe('/api/orders/1')
    expect(JSON.parse(form.paramsText)).toEqual({ debug: true })
    expect(JSON.parse(form.bodyText)).toEqual({ qty: 2 })

    const rebuilt = buildRequestConfig(form)
    expect(rebuilt.ok).toBe(true)
    expect(rebuilt.config.body).toEqual({ mode: 'raw', json: { qty: 2 } })

    const empty = requestConfigToForm({})
    expect(empty).toMatchObject({
      method: 'GET',
      url: '',
      paramsText: '',
      headersText: '',
      bodyText: '',
    })
  })
})

describe('断言配置映射与校验', () => {
  it('operator 与后端断言 type 双向映射', () => {
    expect(getOperatorForAssertionType('status_code')).toBe('equals')
    expect(getOperatorForAssertionType('contains')).toBe('contains')
    expect(getOperatorForAssertionType('len_gte')).toBe('gte')
    expect(getOperatorForAssertionType('response_time_lt')).toBe('lt')
    expect(getOperatorForAssertionType('unknown')).toBe('equals')
    expect(getAssertionTypeForOperator('equals')).toBe('json_path')
    expect(getAssertionTypeForOperator('contains')).toBe('contains')
    expect(getAssertionTypeForOperator('gte')).toBe('len_gte')
    expect(getAssertionTypeForOperator('lt')).toBe('response_time_lt')
  })

  it('normalizeAssertionRows / buildAssertionsPayload 往返兼容后端字段别名', () => {
    const rows = normalizeAssertionRows([
      { type: 'status_code', expected: 200 },
      { type: 'json_path', path: 'data.list[0].id', expected: 1 },
      { type: 'len_gte', json_path: 'data.list', value: 3 },
      { type: 'header_present', expected: 'X-Request-Id' },
      'invalid-row',
    ])
    expect(rows).toHaveLength(4)
    expect(rows[1]).toMatchObject({ type: 'json_path', json_path: 'data.list[0].id', operator: 'equals' })
    expect(rows[2]).toMatchObject({ operator: 'gte', expected: 3 })
    expect(normalizeAssertionRows(null)).toEqual([])

    const payload = buildAssertionsPayload(rows)
    expect(payload[0]).toEqual({ type: 'status_code', operator: 'equals', expected: 200 })
    expect(payload[1]).toMatchObject({ type: 'json_path', json_path: 'data.list[0].id' })
    expect(buildAssertionsPayload([{ type: '' }, null])).toEqual([])
  })

  it('validateAssertionRows 报告缺失的必填项', () => {
    expect(validateAssertionRows([])).toEqual([])
    expect(
      validateAssertionRows([
        { type: 'status_code', expected: '200' },
        { type: 'json_path', json_path: 'data.id', expected: 1 },
      ]),
    ).toEqual([])

    const errors = validateAssertionRows([
      { type: 'status_code', expected: '' },
      { type: 'json_path', json_path: '', expected: 1 },
    ])
    expect(errors).toHaveLength(2)
    expect(errors[0]).toContain('缺少期望状态码')
    expect(errors[1]).toContain('缺少 JSON 路径')
  })

  it('断言类型选项包含后端支持的全部类型', () => {
    const values = ASSERTION_TYPE_OPTIONS.map((item) => item.value)
    expect(values).toEqual(
      expect.arrayContaining([
        'status_code',
        'json_path',
        'contains',
        'len_gte',
        'response_time_lt',
        'header_present',
      ]),
    )
  })
})

describe('执行报告数据格式化', () => {
  it('normalizeReport 汇总 summary / execution 并格式化通过率与耗时', () => {
    const view = normalizeReport({
      execution: { id: 9, name: '冒烟执行', status: 'passed', total: 4, passed: 4 },
      summary: { total: 4, passed: 3, failed: 1, skipped: 0, pass_rate: 75, duration_ms: 1500 },
      cases: [
        { name: '登录成功', status: 'passed', duration_ms: 320, assertions: [{ passed: true }] },
        { name: '登录失败', status: 'failed', duration_ms: 180, error_message: '状态码不匹配' },
        { name: '跳过用例', status: 'skipped', duration_ms: 0 },
      ],
      artifacts: { mode: 'simulated' },
    })
    expect(view.ok).toBe(true)
    expect(view.summary).toMatchObject({
      total: 4,
      passed: 3,
      failed: 1,
      passRate: 75,
      passRateText: '75.0%',
      durationMs: 1500,
      durationText: '1.50 s',
      mode: 'simulated',
      status: { label: '通过', tagType: 'success', terminal: true },
    })
    expect(view.cases).toHaveLength(3)
    expect(view.cases[0]).toMatchObject({
      name: '登录成功',
      status: 'passed',
      statusLabel: '通过',
      tagType: 'success',
      durationText: '320 ms',
    })
    expect(view.cases[1]).toMatchObject({ status: 'failed', errorMessage: '状态码不匹配' })
    expect(view.cases[2]).toMatchObject({ status: 'skipped', statusLabel: '跳过', tagType: 'info' })
  })

  it('normalizeReport 对空值 / 非对象返回可渲染的兜底结构', () => {
    for (const value of [null, undefined, 'oops', [], 42]) {
      const view = normalizeReport(value)
      expect(view.ok).toBe(false)
      expect(view.summary.total).toBe(0)
      expect(view.summary.passRateText).toBe('0.0%')
      expect(view.summary.status.tagType).toBe('info')
      expect(view.cases).toEqual([])
    }

    const fallback = normalizeReport({ summary: {}, execution: { total: 2, passed: 1 } })
    expect(fallback.ok).toBe(true)
    expect(fallback.summary.total).toBe(2)
    expect(fallback.summary.passed).toBe(1)
    expect(fallback.summary.mode).toBe('')
  })

  it('normalizeReportCases 容忍脏数据并保留顺序', () => {
    const rows = normalizeReportCases([
      null,
      { case_name: '接口 A', status: 'error', duration_ms: '120' },
      { name: '', status: 'unknown' },
    ])
    expect(rows).toHaveLength(3)
    expect(rows[0].name).toBe('用例 1')
    expect(rows[1]).toMatchObject({ name: '接口 A', status: 'error', durationMs: 120 })
    expect(rows[2].name).toBe('用例 3')
    expect(rows[2].tagType).toBe('info')
    expect(normalizeReportCases(undefined)).toEqual([])
  })

  it('buildReportFilename 生成稳定的下载文件名', () => {
    expect(buildReportFilename({ id: 12 })).toBe('api-execution-report-12.json')
    expect(buildReportFilename({ execution_id: 7 })).toBe('api-execution-report-7.json')
    expect(buildReportFilename(null)).toBe('api-execution-report-unknown.json')
  })

  it('summarizeGeneratedCases 兼容预览与已生成两种返回', () => {
    const generated = summarizeGeneratedCases({
      created: 2,
      cases: [
        {
          id: 1,
          name: '正向用例',
          test_type: 'positive',
          priority: 1,
          request_config: { method: 'post', url: '/api/login' },
          assertions: [{ type: 'status_code', expected: 200 }],
        },
        { id: 2, name: '反向用例', test_type: 'negative', request_config: {} },
      ],
    })
    expect(generated.count).toBe(2)
    expect(generated.message).toBe('已生成 2 条用例')
    expect(generated.cases[0]).toMatchObject({
      name: '正向用例',
      testTypeLabel: '正向',
      priority: 'P1 高',
      method: 'POST',
      url: '/api/login',
      assertionCount: 1,
    })

    const preview = summarizeGeneratedCases({ preview: true, cases: [{ name: '预览用例' }] })
    expect(preview.count).toBe(1)
    expect(preview.preview).toBe(true)
    expect(preview.message).toBe('预览 1 条用例')
    expect(summarizeGeneratedCases(null)).toMatchObject({ count: 0, cases: [] })
  })

  it('规范来源 / 状态与内容校验', () => {
    expect(getSpecSourceLabel('openapi')).toBe('OpenAPI 3')
    expect(getSpecSourceLabel('postman')).toBe('Postman Collection')
    expect(getSpecStatusMeta('parsed')).toMatchObject({ label: '已解析', tagType: 'success' })
    expect(getSpecStatusMeta('failed').tagType).toBe('danger')
    expect(getSpecStatusMeta('weird').label).toBe('weird')

    expect(validateSpecContent('{"openapi": "3.0.0"}').valid).toBe(true)
    expect(validateSpecContent('openapi: 3.0.0').valid).toBe(true)
    expect(validateSpecContent('{"openapi": ').valid).toBe(false)
    expect(validateSpecContent('   ').valid).toBe(false)
  })
})
