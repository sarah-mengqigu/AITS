import { describe, expect, it } from 'vitest'

import {
  EXECUTION_STATUS_TEXT,
  buildAlternatives,
  buildStepsPayload,
  computePassRate as computeWebPassRate,
  emptyStep,
  flattenTree,
  formatStep,
  getCaseStatusText,
  getExecutionStatusTagType,
  getExecutionStatusText,
  getProgressPercent,
  getScriptTypeText,
  isTerminalStatus,
  normalizeElementList,
  normalizeListPayload,
  normalizeSteps,
  normalizeTaskStatus,
  normalizeSteps as normalizeWebSteps,
  parseBulkElements,
  parseJsonText,
  summarizeExecutions,
  summarizeSteps,
  validateSteps,
} from '@/views/web-testing/utils'

import {
  APP_STEP_ACTION_KEYS,
  SONIC_GUIDANCE,
  SONIC_NOT_CONFIGURED,
  applicationIdentifier,
  buildAppStepsPayload,
  buildApplicationPayload,
  buildDeviceConfig,
  computePassRate as computeAppPassRate,
  describeDeviceConfig,
  describeSonicError,
  formatAppStep,
  formatDevice,
  getPlatformText,
  getRunStatusTagType,
  getRunStatusText,
  isSonicNotConfigured,
  normalizeAppSteps,
  normalizeDeviceList,
  normalizeElementPageList,
  normalizeRemoteInfo,
  normalizeRunCases,
  summarizeRuns,
  summarizeSonicSteps,
  validateAppSteps,
  validateApplicationForm,
} from '@/views/app-testing/utils'

// ---------------------------------------------------------------------------
// 1. 状态映射
// ---------------------------------------------------------------------------
describe('Web/App 测试状态映射', () => {
  it('Web 执行状态 → 中文文案与标签类型', () => {
    expect(EXECUTION_STATUS_TEXT).toMatchObject({
      pending: '待执行',
      running: '执行中',
      passed: '通过',
      failed: '失败',
      error: '错误',
      cancelled: '已取消',
    })
    expect(getExecutionStatusText('passed')).toBe('通过')
    expect(getExecutionStatusText('cancelled')).toBe('已取消')
    expect(getExecutionStatusText(null)).toBe('未知')
    expect(getExecutionStatusText('weird-status', '未知状态')).toBe('未知状态')

    expect(getExecutionStatusTagType('passed')).toBe('success')
    expect(getExecutionStatusTagType('failed')).toBe('danger')
    expect(getExecutionStatusTagType('error')).toBe('danger')
    expect(getExecutionStatusTagType('running')).toBe('warning')
    expect(getExecutionStatusTagType('pending')).toBe('info')
    expect(getExecutionStatusTagType('unknown')).toBe('info')

    expect(getCaseStatusText('skipped')).toBe('跳过')
    expect(getCaseStatusText('error')).toBe('错误')

    expect(isTerminalStatus('passed')).toBe(true)
    expect(isTerminalStatus('failed')).toBe(true)
    expect(isTerminalStatus('error')).toBe(true)
    expect(isTerminalStatus('cancelled')).toBe(true)
    expect(isTerminalStatus('running')).toBe(false)
    expect(isTerminalStatus('pending')).toBe(false)

    expect(getScriptTypeText('playwright')).toBe('Playwright')
    expect(getScriptTypeText('midscene')).toBe('MidScene')
    expect(getScriptTypeText('')).toBe('—')
  })

  it('App 运行状态 → 中文文案与标签类型', () => {
    expect(getRunStatusText('running')).toBe('执行中')
    expect(getRunStatusText('passed')).toBe('通过')
    expect(getRunStatusText('cancelled')).toBe('已取消')
    expect(getRunStatusText(undefined)).toBe('未知')
    expect(getRunStatusTagType('passed')).toBe('success')
    expect(getRunStatusTagType('failed')).toBe('danger')
    expect(getRunStatusTagType('error')).toBe('danger')
    expect(getRunStatusTagType('pending')).toBe('info')
    expect(getRunStatusTagType('unknown')).toBe('info')

    expect(getPlatformText('android')).toBe('Android')
    expect(getPlatformText('ios')).toBe('iOS')
    expect(getPlatformText(null)).toBe('—')
  })

  it('WS/轮询任务状态归一与进度百分比', () => {
    expect(normalizeTaskStatus({ status: 'RUNNING', progress: '45', message: '执行中' })).toEqual({
      status: 'running',
      progress: 45,
      message: '执行中',
    })
    expect(normalizeTaskStatus({ data: { status: 'passed' } })).toMatchObject({ status: 'passed' })
    expect(normalizeTaskStatus(null)).toEqual({ status: '', progress: null, message: '' })

    expect(getProgressPercent({ status: 'pending' })).toBe(5)
    expect(getProgressPercent({ status: 'running' })).toBe(60)
    expect(getProgressPercent({ status: 'passed' })).toBe(100)
    expect(getProgressPercent({ status: 'running', progress: 130 })).toBe(100)
    expect(getProgressPercent({})).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// 2. 平台字段校验（App 应用）
// ---------------------------------------------------------------------------
describe('App 应用平台字段校验', () => {
  it('Android 必填 package_name，iOS 必填 bundle_id', () => {
    expect(validateApplicationForm({ name: 'Demo', platform: 'android', package_name: '' })).toEqual({
      valid: false,
      errors: { package_name: 'Android 应用必须填写包名（package_name）' },
    })
    expect(
      validateApplicationForm({ name: 'Demo', platform: 'android', bundle_id: 'com.demo.app' }).valid,
    ).toBe(false)
    expect(
      validateApplicationForm({ name: 'Demo', platform: 'android', package_name: 'com.demo.app' }).valid,
    ).toBe(true)

    expect(validateApplicationForm({ name: 'Demo', platform: 'ios', bundle_id: '' }).errors).toHaveProperty(
      'bundle_id',
    )
    expect(
      validateApplicationForm({ name: 'Demo', platform: 'ios', package_name: 'com.demo.app' }).valid,
    ).toBe(false)
    expect(validateApplicationForm({ name: 'Demo', platform: 'ios', bundle_id: 'com.demo.app' }).valid).toBe(
      true,
    )
  })

  it('名称必填且平台只允许 android / ios', () => {
    expect(validateApplicationForm({ name: '', platform: 'android', package_name: 'a' }).errors).toEqual({
      name: '请输入应用名称',
    })
    const result = validateApplicationForm({ name: 'Demo', platform: 'hmos' })
    expect(result.valid).toBe(false)
    expect(result.errors.platform).toContain('android')
  })

  it('提交载荷按平台清理无关字段', () => {
    expect(
      buildApplicationPayload({
        name: ' Demo ',
        platform: 'android',
        package_name: ' com.demo.app ',
        bundle_id: 'should-be-dropped',
        app_version: ' 1.0.0 ',
        description: ' desc ',
      }),
    ).toEqual({
      name: 'Demo',
      platform: 'android',
      package_name: 'com.demo.app',
      bundle_id: '',
      app_version: '1.0.0',
      description: 'desc',
    })
    expect(
      buildApplicationPayload({ platform: 'ios', package_name: 'x', bundle_id: 'com.demo.ios' }),
    ).toMatchObject({ package_name: '', bundle_id: 'com.demo.ios' })

    expect(applicationIdentifier({ platform: 'android', package_name: 'com.a' })).toBe('com.a')
    expect(applicationIdentifier({ platform: 'ios', bundle_id: 'com.i' })).toBe('com.i')
    expect(applicationIdentifier({})).toBe('')
  })
})

// ---------------------------------------------------------------------------
// 3. 步骤校验与格式化
// ---------------------------------------------------------------------------
describe('Web 用例步骤校验与格式化', () => {
  it('合法步骤通过校验，非法 action / 缺失字段给出中文错误', () => {
    const valid = validateSteps([
      { action: 'goto', target: 'https://demo.example.com/login' },
      { action: 'fill', target: '#username', value: 'admin' },
      { action: 'click', target: '登录按钮' },
    ])
    expect(valid.valid).toBe(true)
    expect(valid.errors).toEqual([])
    expect(valid.steps).toHaveLength(3)

    const missingAction = validateSteps([{ target: '#username' }])
    expect(missingAction.valid).toBe(false)
    expect(missingAction.errors[0]).toBe('第 1 个步骤缺少 action')

    const badAction = validateSteps([{ action: 'jump', target: 'x' }])
    expect(badAction.valid).toBe(false)
    expect(badAction.errors[0]).toBe('第 1 个步骤 action 不支持：jump')

    const missingTarget = validateSteps([{ action: 'click' }])
    expect(missingTarget.errors[0]).toContain('需要填写 target')

    const missingValue = validateSteps([{ action: 'fill', target: '#username' }])
    expect(missingValue.errors[0]).toContain('需要填写 value')

    expect(validateSteps(null)).toEqual({ valid: true, errors: [], steps: [] })
  })

  it('步骤格式化 / 摘要 / 提交载荷', () => {
    expect(formatStep({ action: 'click', target: '登录按钮' }, 1)).toBe('1. 点击 登录按钮')
    expect(formatStep({ action: 'fill', target: '#username', value: 'admin' })).toBe(
      '输入 #username = admin',
    )
    expect(
      formatStep({ action: 'assert_text', target: 'body', value: '欢迎', expect: '包含欢迎' }),
    ).toBe('断言文本 body = 欢迎（期望：包含欢迎）')
    expect(formatStep({ action: 'unknown_action' })).toBe('unknown_action')

    expect(summarizeSteps([])).toBe('暂无步骤')
    expect(summarizeSteps([{ action: 'goto' }, { action: 'click' }])).toBe('2 个步骤：打开页面 → 点击')

    expect(buildStepsPayload([{ action: 'click', target: 'a', value: '', expect: '' }, { target: 'b' }])).toEqual([
      { action: 'click', target: 'a' },
    ])

    expect(normalizeSteps([{ action: 'click', selector: '#x' }])[0]).toMatchObject({
      action: 'click',
      target: '#x',
    })
    expect(emptyStep().action).toBe('click')
  })

  it('App 步骤校验与 Sonic 步骤快照归一', () => {
    const valid = validateAppSteps([
      { action: 'start_app' },
      { action: 'tap', target: '登录按钮' },
      { action: 'input', target: '用户名输入框', value: 'admin' },
    ])
    expect(valid.valid).toBe(true)

    expect(validateAppSteps([{ action: 'drag' }]).errors[0]).toContain('action 不支持：drag')
    expect(validateAppSteps([{ action: 'tap' }]).errors[0]).toContain('需要填写 target')
    expect(validateAppSteps([{ action: 'input', target: '用户名' }]).errors[0]).toContain(
      '需要填写 value',
    )
    expect(APP_STEP_ACTION_KEYS).toContain('start_app')
    expect(APP_STEP_ACTION_KEYS).toContain('swipe')

    expect(formatAppStep({ action: 'tap', target: '登录按钮' }, 2)).toBe('2. 点击 登录按钮')
    expect(formatAppStep({ action: 'input', target: '用户名', value: 'admin' })).toBe(
      '输入 用户名 = admin',
    )
    expect(buildAppStepsPayload([{ action: 'tap', target: 'a', value: '', expect: '' }])).toEqual([
      { action: 'tap', target: 'a' },
    ])
    expect(normalizeAppSteps([{ action: 'TAP', selector: 'btn' }])[0]).toMatchObject({
      action: 'tap',
      target: 'btn',
    })

    const sonicSteps = [
      { type: 0, content: { action: '点击', target: '登录按钮', value: '', expect: '' } },
      { type: 1, content: { action: '断言', target: '首页', value: '欢迎', expect: '欢迎' } },
      { type: 2, content: { action: '等待', target: '', value: '1000', expect: '' } },
    ]
    const rows = summarizeSonicSteps(sonicSteps)
    expect(rows).toHaveLength(3)
    expect(rows[0]).toMatchObject({ index: 1, typeLabel: '操作', action: '点击', target: '登录按钮' })
    expect(rows[1]).toMatchObject({ typeLabel: '断言', value: '欢迎' })
    expect(rows[2].typeLabel).toBe('其他')
    expect(summarizeSonicSteps(null)).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// 4. 列表 / JSON / POM / 统计等辅助逻辑
// ---------------------------------------------------------------------------
describe('列表与 JSON 解析容错', () => {
  it('normalizeListPayload 兼容分页结构与裸数组', () => {
    expect(normalizeListPayload({ count: 3, results: [{ id: 1 }] })).toEqual({
      results: [{ id: 1 }],
      count: 3,
    })
    expect(normalizeListPayload([{ id: 1 }, { id: 2 }])).toEqual({
      results: [{ id: 1 }, { id: 2 }],
      count: 2,
    })
    expect(normalizeListPayload({ detail: 'sonic_not_configured' })).toEqual({ results: [], count: 0 })
    expect(normalizeListPayload(null)).toEqual({ results: [], count: 0 })
  })

  it('parseJsonText 校验数组 / 对象与空值', () => {
    expect(parseJsonText('', { expected: 'array' })).toEqual({ ok: true, value: [] })
    expect(parseJsonText('[1,2]', { expected: 'array' })).toEqual({ ok: true, value: [1, 2] })
    expect(parseJsonText('{}', { expected: 'array' }).ok).toBe(false)
    expect(parseJsonText('[]', { expected: 'object' }).ok).toBe(false)
    expect(parseJsonText('{bad json}').ok).toBe(false)
    expect(parseJsonText('', { allowEmpty: false }).ok).toBe(false)
  })

  it('模块树扁平化 / 统计聚合 / 通过率', () => {
    const tree = [
      {
        id: 1,
        name: '根',
        children: [{ id: 2, name: '子', children: [] }],
      },
    ]
    const flat = flattenTree(tree)
    expect(flat.map((node) => node.id)).toEqual([1, 2])
    expect(flat[1].depth).toBe(1)

    const summary = summarizeExecutions([
      { status: 'passed', total: 3, passed: 3 },
      { status: 'failed', total: 2, passed: 1, failed: 1 },
      { status: 'running', total: 1, passed: 0 },
    ])
    expect(summary).toMatchObject({
      current: 3,
      passed: 1,
      failed: 1,
      running: 1,
      cases: 6,
      passedCases: 4,
      failedCases: 1,
    })
    expect(summary.passRate).toBe(50)

    expect(computeWebPassRate({ pass_rate: 87.5 })).toBe(87.5)
    expect(computeWebPassRate({ passed: 3, failed: 1 })).toBe(75)
    expect(computeWebPassRate({})).toBe(0)
    expect(computeAppPassRate({ passed: 1, failed: 1 })).toBe(50)
  })
})

describe('POM 元素与 Sonic 代理降级', () => {
  it('批量导入 JSON 校验与 alternatives 归一', () => {
    const parsed = parseBulkElements(
      JSON.stringify([
        {
          name: '用户名',
          locator_type: 'css',
          locator_value: '#username',
          alternatives: [{ locator_type: 'xpath', locator_value: '//input' }],
        },
      ]),
      9,
    )
    expect(parsed.ok).toBe(true)
    expect(parsed.value).toEqual({
      page: 9,
      elements: [
        {
          name: '用户名',
          locator_type: 'css',
          locator_value: '#username',
          description: '',
          alternatives: [{ locator_type: 'xpath', locator_value: '//input' }],
        },
      ],
    })

    expect(parseBulkElements('[{"name":"a"}]', 1)).toMatchObject({ ok: false })
    expect(parseBulkElements('[{"name":"a","locator_value":"#a"}]', null).error).toBe('请先选择页面')
    expect(parseBulkElements('[{"name":"a","locator_type":"magic","locator_value":"#a"}]', 1).ok).toBe(
      false,
    )
    expect(buildAlternatives([{ locator_type: 'css', locator_value: '' }, { locator_value: '#b' }])).toEqual([
      { locator_type: 'css', locator_value: '#b' },
    ])
    expect(normalizeElementList({ results: [{ id: 1 }] })[0].alternatives).toEqual([])
  })

  it('Sonic 未配置时降级为空列表并给出中文引导', () => {
    expect(isSonicNotConfigured({ detail: SONIC_NOT_CONFIGURED })).toBe(true)
    expect(isSonicNotConfigured({ configured: false })).toBe(true)
    expect(isSonicNotConfigured([{ udid: 'abc' }])).toBe(false)
    expect(isSonicNotConfigured(null)).toBe(false)

    expect(normalizeDeviceList([])).toEqual([])
    expect(normalizeDeviceList({ detail: SONIC_NOT_CONFIGURED })).toEqual([])
    expect(normalizeDeviceList({ results: [{ udid: 'u1' }] })).toHaveLength(1)
    expect(normalizeElementPageList({ detail: SONIC_NOT_CONFIGURED })).toEqual([])

    const device = formatDevice({ deviceUdid: 'u1', deviceName: 'Pixel', os: 'android' })
    expect(device).toMatchObject({ udid: 'u1', name: 'Pixel', platform: 'android' })
    expect(formatDevice({ udid: 'u2', platform: 'IOS', model: 'iPhone' })).toMatchObject({
      platform: 'ios',
      name: 'iPhone',
    })

    const notConfiguredError = { code: SONIC_NOT_CONFIGURED, message: '未配置 Sonic 服务' }
    expect(describeSonicError(notConfiguredError)).toBe(SONIC_GUIDANCE)
    expect(describeSonicError({ code: 'sonic_remote_unavailable' })).toContain('设备在线')
    expect(SONIC_GUIDANCE).toContain('SONIC_BASE_URL')
  })

  it('设备配置与远控信息归一', () => {
    expect(buildDeviceConfig({ device_udid: ' u1 ', device_name: 'Pixel', platform: 'android' })).toEqual({
      udid: 'u1',
      device_name: 'Pixel',
      platform: 'android',
    })
    expect(buildDeviceConfig({})).toEqual({})
    expect(describeDeviceConfig({})).toBe('未指定设备（使用默认设备）')
    expect(describeDeviceConfig({ udid: 'u1', device_name: 'Pixel' })).toContain('Pixel')

    const remote = normalizeRemoteInfo({ ws_url: 'ws://sonic/remote/1', jmuxer: { video: 'h264' } })
    expect(remote).toMatchObject({ configured: true, wsUrl: 'ws://sonic/remote/1' })
    expect(remote.jmuxer).toEqual({ video: 'h264' })
    expect(normalizeRemoteInfo({ detail: SONIC_NOT_CONFIGURED })).toMatchObject({
      configured: false,
      wsUrl: '',
    })
  })

  it('运行统计与 summary.cases 归一', () => {
    const summary = summarizeRuns([
      { status: 'passed', total: 2, passed: 2 },
      { status: 'error', total: 1, passed: 0 },
    ])
    expect(summary).toMatchObject({ passed: 1, error: 1, cases: 3 })
    expect(summary.passRate).toBe(50)

    const cases = normalizeRunCases({
      cases: [{ id: 1, name: '登录', status: 'passed', duration_ms: 1200 }],
    })
    expect(cases).toHaveLength(1)
    expect(cases[0]).toMatchObject({ key: 1, name: '登录', status: 'passed', duration: 1200 })
    expect(normalizeRunCases({})).toEqual([])
  })
})
