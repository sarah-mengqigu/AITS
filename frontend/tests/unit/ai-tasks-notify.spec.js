/**
 * 前端模块单测：AI 中心 / 定时任务 / 通知中心。
 *
 * 覆盖点（对应交付要求）：
 * 1. Cron 预览的中文描述与未来执行时间格式化；
 * 2. LLM API Key 掩码不回写真实密钥；
 * 3. 用量统计（by_day / by_agent / by_model）聚合数据转换；
 * 4. SMTP 密码掩码不回写；
 * 5. 通知测试发送载荷校验；
 * 6. 三个模块主要视图的挂载冒烟（模板 / 组合式逻辑运行时无异常）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import {
  buildLlmPayload,
  emptyLlmForm,
  isMaskedApiKey,
  llmRecordToForm,
  maskApiKey,
} from '@/views/ai-core/utils/llm'
import {
  buildAgentSeries,
  buildDaySeries,
  buildModelSeries,
  normalizeUsageStats,
  toNumber,
} from '@/views/ai-core/utils/usage'
import {
  AGENT_SAMPLE_PAYLOADS,
  createStreamTaskId,
  normalizeAgentSteps,
  parsePayloadText,
  samplePayloadFor,
} from '@/views/ai-core/utils/agent'
import {
  describeCronLocally,
  formatCronRun,
  normalizeCronPreview,
} from '@/views/scheduled-tasks/utils/cron'
import {
  EMAIL_PASSWORD_MASK,
  buildEmailConfigPayload,
  buildTestPayload,
  splitEmails,
} from '@/views/notifications/utils'

describe('定时任务 · Cron 预览格式化', () => {
  it('把后端时间字符串格式化为「YYYY-MM-DD HH:mm」', () => {
    expect(formatCronRun('2025-01-01 09:00:00')).toBe('2025-01-01 09:00')
    expect(formatCronRun('2025-01-01T09:30:00')).toBe('2025-01-01 09:30')
    expect(formatCronRun('')).toBe('')
  })

  it('归一化合法预览：保留中文描述，最多展示 5 次未来执行时间', () => {
    const preview = normalizeCronPreview({
      valid: true,
      expression: '0 9 * * *',
      description: '每天 09:00 执行',
      next_runs: [
        '2025-01-01 09:00:00',
        '2025-01-02 09:00:00',
        '2025-01-03 09:00:00',
        '2025-01-04 09:00:00',
        '2025-01-05 09:00:00',
        '2025-01-06 09:00:00',
      ],
      timezone: 'Asia/Shanghai',
      message: '',
    })

    expect(preview.valid).toBe(true)
    expect(preview.description).toBe('每天 09:00 执行')
    expect(preview.nextRuns).toHaveLength(5)
    expect(preview.nextRuns[0]).toBe('2025-01-01 09:00')
    expect(preview.message).toBe('')
    expect(preview.timezone).toBe('Asia/Shanghai')
  })

  it('归一化非法预览：不保留描述与执行时间，并保留错误信息', () => {
    const preview = normalizeCronPreview({
      valid: false,
      expression: 'bad cron',
      description: '',
      next_runs: [],
      message: '无效的 cron 表达式: bad cron',
    })

    expect(preview.valid).toBe(false)
    expect(preview.description).toBe('')
    expect(preview.nextRuns).toEqual([])
    expect(preview.message).toContain('无效的 cron')
  })

  it('后端描述缺失时使用本地中文兜底', () => {
    const preview = normalizeCronPreview({
      valid: true,
      expression: '*/15 * * * *',
      next_runs: ['2025-02-01 10:15:00'],
    })

    expect(preview.description).toBe('每 15 分钟执行')
    expect(describeCronLocally('0 9 * * *')).toBe('每天 09:00 执行')
    expect(describeCronLocally('0 9 * * 1')).toBe('每周一 09:00 执行')
    expect(describeCronLocally('0 2 1 * *')).toBe('每月 1 日 02:00 执行')
    expect(describeCronLocally('not a cron')).toBe('')
  })
})

describe('AI 中心 · 模型配置 API Key 掩码', () => {
  it('掩码生成与判定与后端保持一致', () => {
    expect(maskApiKey('sk-1234567890abcd')).toBe('sk-****abcd')
    expect(maskApiKey('')).toBe('')
    expect(isMaskedApiKey('sk-****abcd')).toBe(true)
    expect(isMaskedApiKey('sk-real-key')).toBe(false)
  })

  it('掩码值绝不回写：提交载荷不包含 api_key', () => {
    const form = {
      ...emptyLlmForm({
        scope: 'project',
        project: 7,
        name: '主模型',
        provider: 'deepseek',
        api_key: 'sk-****abcd',
        extraText: '{"top_p":0.9}',
      }),
    }
    const { payload, error } = buildLlmPayload(form)

    expect(error).toBe('')
    expect(payload).not.toHaveProperty('api_key')
    expect(payload.project).toBe(7)
    expect(payload.extra).toEqual({ top_p: 0.9 })
  })

  it('留空 api_key 表示不修改；填写真实值时才提交', () => {
    const blank = buildLlmPayload({ ...emptyLlmForm({ name: '模型' }) })
    expect(blank.error).toBe('')
    expect(blank.payload).not.toHaveProperty('api_key')
    expect(blank.payload.project).toBeNull()

    const filled = buildLlmPayload({
      ...emptyLlmForm({ name: '模型', api_key: 'sk-live-key-0001' }),
    })
    expect(filled.payload.api_key).toBe('sk-live-key-0001')
  })

  it('编辑记录转表单时 api_key 恒为空，掩码只做占位提示', () => {
    const values = llmRecordToForm({
      id: 3,
      project: null,
      name: '全局模型',
      provider: 'openai',
      api_key: 'sk-****wxyz',
      model_type: 'text',
      extra: { a: 1 },
    })

    expect(values.api_key).toBe('')
    expect(values.apiKeyMasked).toBe('sk-****wxyz')
    expect(values.scope).toBe('global')
    expect(JSON.parse(values.extraText)).toEqual({ a: 1 })
  })

  it('非法配置返回可读错误而不是抛出异常', () => {
    expect(buildLlmPayload({ ...emptyLlmForm({ name: '   ' }) }).error).toBe('配置名称不能为空')
    expect(
      buildLlmPayload({ ...emptyLlmForm({ name: '模型', temperature: 5 }) }).error,
    ).toContain('temperature')
    expect(buildLlmPayload({ ...emptyLlmForm({ name: '模型', extraText: '[1,2]' }) }).error).toContain(
      'JSON 对象',
    )
  })
})

describe('AI 中心 · 用量聚合数据转换', () => {
  const stats = {
    total: {
      requests: 12,
      success: 10,
      failed: 2,
      prompt_tokens: 100,
      completion_tokens: 200,
      total_tokens: 300,
      avg_response_time_ms: 45.6,
    },
    by_day: [
      { date: '2025-01-01', requests: 2, success: 2, failed: 0, total_tokens: 50 },
      { date: '2025-01-02', requests: '3', success: '3', failed: '0', total_tokens: '80' },
      { date: '2025-01-03', requests: 7, success: 5, failed: 2, total_tokens: '170' },
    ],
    by_model: [
      { model: 'deepseek-chat', provider: 'deepseek', requests: 5, total_tokens: 120 },
      { model: 'mock', provider: 'mock', requests: '7', total_tokens: '180' },
    ],
    by_agent: [
      { agent: 'api_testcase', requests: 2, total_tokens: 40 },
      { agent: 'webui_testcase', requests: '9', total_tokens: '260' },
    ],
  }

  it('归一化 total 并把字符串数值转成数字', () => {
    const normalized = normalizeUsageStats(stats)
    expect(normalized.total.requests).toBe(12)
    expect(normalized.total.totalTokens).toBe(300)
    expect(normalized.total.avgResponseTimeMs).toBe(45.6)
    expect(normalizeUsageStats({}).total.totalTokens).toBe(0)
    expect(toNumber('abc')).toBe(0)
  })

  it('按天序列保持日期升序并支持截断', () => {
    const series = buildDaySeries(stats.by_day)
    expect(series.dates).toEqual(['2025-01-01', '2025-01-02', '2025-01-03'])
    expect(series.requests).toEqual([2, 3, 7])
    expect(series.failed).toEqual([0, 0, 2])
    expect(series.tokens).toEqual([50, 80, 170])

    const limited = buildDaySeries(stats.by_day, { limit: 2 })
    expect(limited.dates).toEqual(['2025-01-02', '2025-01-03'])
  })

  it('按 Agent / 模型序列按请求数降序并限制条数', () => {
    const agents = buildAgentSeries(stats.by_agent)
    expect(agents.names).toEqual(['webui_testcase', 'api_testcase'])
    expect(agents.requests).toEqual([9, 2])
    expect(agents.tokens).toEqual([260, 40])

    const models = buildModelSeries(stats.by_model, { limit: 1 })
    expect(models.models).toEqual(['mock'])
    expect(models.requests).toEqual([7])
  })
})

describe('AI 中心 · Agent 调试辅助逻辑', () => {
  it('示例 payload 深拷贝，不污染原始常量', () => {
    const sample = samplePayloadFor('api_testcase')
    sample.endpoint.method = 'GET'
    expect(AGENT_SAMPLE_PAYLOADS.api_testcase.endpoint.method).toBe('POST')
    expect(samplePayloadFor('unknown-agent')).toEqual({})
  })

  it('JSON 编辑器解析失败给出可读错误', () => {
    expect(parsePayloadText('').value).toEqual({})
    expect(parsePayloadText('{"a":1}').value).toEqual({ a: 1 })
    expect(parsePayloadText('[1,2]').error).toContain('JSON 对象')
    expect(parsePayloadText('{invalid').error).toContain('JSON 解析失败')
  })

  it('流式任务 ID 唯一且带前缀；步骤时间线容错归一化', () => {
    const first = createStreamTaskId('api_testcase')
    const second = createStreamTaskId('api_testcase')
    expect(first).not.toBe(second)
    expect(first.startsWith('api_testcase-')).toBe(true)

    const steps = normalizeAgentSteps([
      { node: 'plan', status: 'success', message: '规划完成' },
      { name: 'generate', output: { content: 'x'.repeat(200) } },
      'raw-step',
    ])
    expect(steps[0]).toMatchObject({ index: 1, node: 'plan', status: 'success' })
    expect(steps[1].node).toBe('generate')
    expect(steps[1].summary.endsWith('…')).toBe(true)
    expect(steps[2].summary).toBe('raw-step')
    expect(normalizeAgentSteps(null)).toEqual([])
  })
})

describe('通知中心 · 载荷构造与掩码', () => {
  it('SMTP 密码掩码不回写，留空不提交 password', () => {
    const base = {
      host: 'smtp.example.com',
      port: 465,
      username: 'noreply',
      from_email: 'noreply@example.com',
      use_ssl: true,
      use_tls: false,
      is_active: true,
    }

    const masked = buildEmailConfigPayload({ ...base, password: EMAIL_PASSWORD_MASK })
    expect(masked.error).toBe('')
    expect(masked.payload).not.toHaveProperty('password')

    const blank = buildEmailConfigPayload({ ...base, password: '' })
    expect(blank.payload).not.toHaveProperty('password')

    const real = buildEmailConfigPayload({ ...base, password: 'smtp-secret' })
    expect(real.payload.password).toBe('smtp-secret')
  })

  it('SMTP 表单校验：主机必填、端口范围、SSL 与 TLS 互斥', () => {
    expect(buildEmailConfigPayload({ host: '' }).error).toBe('请填写 SMTP 主机地址')
    expect(buildEmailConfigPayload({ host: 'smtp.example.com', port: 0 }).error).toContain('端口')
    expect(
      buildEmailConfigPayload({
        host: 'smtp.example.com',
        port: 465,
        use_ssl: true,
        use_tls: true,
      }).error,
    ).toContain('不能同时启用')
    expect(
      buildEmailConfigPayload({
        host: 'smtp.example.com',
        port: 465,
        from_email: 'not-an-email',
      }).error,
    ).toContain('邮箱格式')
  })

  it('测试发送载荷：接收人优先，渠道模式按渠道类型校验地址', () => {
    const byReceiver = buildTestPayload({ receiverId: 5, title: '冒烟测试' })
    expect(byReceiver.payload).toEqual({ receiver_id: 5, title: '冒烟测试' })

    expect(buildTestPayload({ title: '' }).error).toContain('接收人或通知渠道')

    const webhook = buildTestPayload({
      channelCode: 'dingtalk',
      webhookUrl: 'https://oapi.dingtalk.com/robot/send?access_token=x',
      title: '通知',
    })
    expect(webhook.error).toBe('')
    expect(webhook.payload.webhook_url).toContain('https://')

    expect(buildTestPayload({ channelCode: 'dingtalk' }).error).toContain('Webhook')
    expect(buildTestPayload({ channelCode: 'webhook', webhookUrl: 'ftp://x' }).error).toContain(
      'http',
    )
    expect(buildTestPayload({ channelCode: 'email', targetAddress: '' }).error).toContain('收件邮箱')
  })

  it('邮箱列表分割兼容中英文分隔符', () => {
    expect(splitEmails('a@x.com, b@x.com；c@x.com')).toEqual([
      'a@x.com',
      'b@x.com',
      'c@x.com',
    ])
    expect(splitEmails('')).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// 组件挂载冒烟：真实挂载三个模块的主要视图（API 全部打桩），
// 确保模板、组合式逻辑、props 传递在运行时不会抛错或渲染空白。
// ---------------------------------------------------------------------------

vi.mock('vue-router', () => ({
  useRoute: () => ({ name: 'ai-core', path: '/ai-core', query: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

vi.mock('vue-echarts', () => ({
  default: { name: 'VChart', props: ['option'], render: () => null },
}))

vi.mock('@/api/aiCore', () => ({
  aiCoreApi: {
    listLlmConfigs: vi.fn(async () => ({ count: 0, results: [] })),
    createLlmConfig: vi.fn(async () => ({})),
    updateLlmConfig: vi.fn(async () => ({})),
    removeLlmConfig: vi.fn(async () => ({})),
    testLlmConfig: vi.fn(async () => ({ success: true })),
    setDefaultLlmConfig: vi.fn(async () => ({})),
    listRagConfigs: vi.fn(async () => ({ count: 0, results: [] })),
    createRagConfig: vi.fn(async () => ({})),
    updateRagConfig: vi.fn(async () => ({})),
    removeRagConfig: vi.fn(async () => ({})),
    setDefaultRagConfig: vi.fn(async () => ({})),
    ragStats: vi.fn(async () => ({ documents: 0, chunks: 0, collection: 'default' })),
    indexDocument: vi.fn(async () => ({ chunk_count: 1 })),
    searchRag: vi.fn(async () => ({ count: 0, results: [], top_k: 5 })),
    listMcpConfigs: vi.fn(async () => ({ count: 0, results: [] })),
    createMcpConfig: vi.fn(async () => ({})),
    updateMcpConfig: vi.fn(async () => ({})),
    removeMcpConfig: vi.fn(async () => ({})),
    refreshMcpTools: vi.fn(async () => ({ count: 0, status: 'connected' })),
    listMcpTools: vi.fn(async () => ({ count: 0, results: [] })),
    listUsageLogs: vi.fn(async () => ({ count: 0, results: [] })),
    usageStats: vi.fn(async () => ({ total: {}, by_day: [], by_model: [], by_agent: [] })),
    listAgents: vi.fn(async () => ({
      count: 1,
      results: [{ name: 'api_testcase', description: '接口用例生成' }],
    })),
    runAgent: vi.fn(async () => ({ status: 'success', result: {}, steps: [] })),
  },
}))

vi.mock('@/api/scheduledTasks', () => ({
  scheduledTasksApi: {
    listTasks: vi.fn(async () => ({ count: 0, results: [] })),
    createTask: vi.fn(async () => ({})),
    updateTask: vi.fn(async () => ({})),
    removeTask: vi.fn(async () => ({})),
    runTask: vi.fn(async () => ({ log_id: 1, status: 'passed' })),
    toggleTask: vi.fn(async () => ({})),
    listLogs: vi.fn(async () => ({ count: 0, results: [] })),
    retrieveLog: vi.fn(async () => ({})),
    cronPreview: vi.fn(async () => ({
      valid: true,
      expression: '0 9 * * *',
      description: '每天 09:00 执行',
      next_runs: ['2025-01-01 09:00:00'],
    })),
  },
}))

vi.mock('@/api/notifications', () => ({
  notificationsApi: {
    listChannels: vi.fn(async () => ({ count: 0, results: [] })),
    updateChannel: vi.fn(async () => ({})),
    listReceivers: vi.fn(async () => ({ count: 0, results: [] })),
    createReceiver: vi.fn(async () => ({})),
    updateReceiver: vi.fn(async () => ({})),
    removeReceiver: vi.fn(async () => ({})),
    emailConfig: vi.fn(async () => ({ host: '', port: 465, password: '', use_ssl: true })),
    saveEmailConfig: vi.fn(async () => ({})),
    test: vi.fn(async () => ({ sent: 1, failed: 0, results: [] })),
    listLogs: vi.fn(async () => ({ count: 0, results: [] })),
    retrieveLog: vi.fn(async () => ({})),
  },
}))

vi.mock('@/api/projects', () => ({
  projectsApi: {
    list: vi.fn(async () => ({ count: 1, results: [{ id: 1, name: '演示项目' }] })),
    listEnvironments: vi.fn(async () => ({ count: 0, results: [] })),
    listKnowledge: vi.fn(async () => ({ count: 0, results: [] })),
  },
}))

vi.mock('@/api/apiTesting', () => ({
  apiTestingApi: { listSuites: vi.fn(async () => ({ count: 0, results: [] })) },
}))
vi.mock('@/api/webTesting', () => ({
  webTestingApi: { listSuites: vi.fn(async () => ({ count: 0, results: [] })) },
}))
vi.mock('@/api/appTesting', () => ({
  appTestingApi: { listSuites: vi.fn(async () => ({ count: 0, results: [] })) },
}))

const VIEWS = {
  'AI 中心 · 能力总览': () => import('@/views/ai-core/Overview.vue'),
  'AI 中心 · 模型配置': () => import('@/views/ai-core/Models.vue'),
  'AI 中心 · RAG 配置': () => import('@/views/ai-core/Rag.vue'),
  'AI 中心 · MCP 工具': () => import('@/views/ai-core/Mcp.vue'),
  'AI 中心 · 用量统计': () => import('@/views/ai-core/Usage.vue'),
  'AI 中心 · Agent 调试': () => import('@/views/ai-core/Agents.vue'),
  '定时任务 · 任务列表': () => import('@/views/scheduled-tasks/Tasks.vue'),
  '定时任务 · 执行日志': () => import('@/views/scheduled-tasks/Logs.vue'),
  '通知中心 · 渠道配置': () => import('@/views/notifications/Channels.vue'),
  '通知中心 · 接收人': () => import('@/views/notifications/Receivers.vue'),
  '通知中心 · 邮件配置': () => import('@/views/notifications/Email.vue'),
  '通知中心 · 发送日志': () => import('@/views/notifications/Logs.vue'),
  '通知中心 · 测试发送': () => import('@/views/notifications/Test.vue'),
}

describe('视图挂载冒烟（三个模块）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  for (const [label, loader] of Object.entries(VIEWS)) {
    it(`${label} 可正常挂载且渲染非空`, async () => {
      const { default: Component } = await loader()
      const wrapper = mount(Component, {
        global: {
          plugins: [ElementPlus],
          stubs: { VChart: true },
        },
      })
      await new Promise((resolve) => setTimeout(resolve, 20))
      expect(wrapper.html().length).toBeGreaterThan(0)
      wrapper.unmount()
    })
  }
})
