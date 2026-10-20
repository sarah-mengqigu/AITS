/** Agent 调试相关纯逻辑：示例 payload、流式通道映射、任务 ID 生成。 */

/** Agent → 流式 WS 通道（与后端 `stream_channel` 保持一致）。 */
export const AGENT_STREAM_CHANNELS = {
  api_testcase: 'api_testcase_generation',
  api_scenario: 'scenario_generation',
  postman_translator: 'postman_translation',
  webui_testcase: 'webui_test_generation',
  webui_playwright: 'webui_auto_test',
  midscene: 'midscene_script_generation',
  midscene_script: 'midscene_script_generation',
}

/** 每个 Agent 的示例请求体（点击「填充示例」时写入 JSON 编辑器）。 */
export const AGENT_SAMPLE_PAYLOADS = {
  api_testcase: {
    endpoint: {
      method: 'POST',
      path: '/api/users/login/',
      summary: '用户登录',
      parameters: [
        { name: 'username', in: 'body', required: true, schema: { type: 'string' } },
        { name: 'password', in: 'body', required: true, schema: { type: 'string' } },
      ],
      request_body: {
        type: 'object',
        required: ['username', 'password'],
        properties: {
          username: { type: 'string', example: 'admin' },
          password: { type: 'string', example: 'admin123' },
        },
      },
      responses: { 200: { description: '登录成功' }, 401: { description: '账号或密码错误' } },
    },
    context: '登录接口需要覆盖空密码、超长用户名、SQL 注入等异常场景',
  },
  api_scenario: {
    requirement: '用户登录后创建项目、邀请成员并执行一次接口测试的完整业务链路',
    endpoints: [
      { method: 'POST', path: '/api/auth/login/', summary: '登录' },
      { method: 'POST', path: '/api/projects/', summary: '创建项目' },
      { method: 'POST', path: '/api/projects/{id}/members/add/', summary: '添加成员' },
    ],
  },
  postman_translator: {
    script: "pm.test('status is 200', function () { pm.response.to.have.status(200); });\npm.environment.set('token', pm.response.json().access);",
  },
  webui_testcase: {
    requirement: '登录页支持用户名密码登录，密码错误时提示「账号或密码错误」',
    base_url: 'https://example.com',
  },
  webui_playwright: {
    requirement: '登录流程自动化',
    base_url: 'https://example.com',
    case: {
      name: '正常登录',
      steps: [
        { action: 'goto', target: '/login' },
        { action: 'fill', selector: '#username', value: 'admin' },
        { action: 'fill', selector: '#password', value: 'admin123' },
        { action: 'click', selector: 'button[type=submit]' },
        { action: 'assert_text', selector: '.welcome', value: '欢迎' },
      ],
    },
    pom: { loginPage: { username: '#username', password: '#password', submit: 'button[type=submit]' } },
  },
  midscene: {
    requirement: '打开登录页并完成登录，校验欢迎语',
    url: 'https://example.com/login',
  },
  midscene_script: {
    requirement: '打开登录页并完成登录，校验欢迎语',
    url: 'https://example.com/login',
    steps: ['打开登录页', '输入用户名 admin', '输入密码 admin123', '点击登录', '断言页面出现「欢迎」'],
  },
}

/** 默认（未选中具体 Agent 时）的通用 payload。 */
export function samplePayloadFor(agentName) {
  const sample = AGENT_SAMPLE_PAYLOADS[agentName]
  if (!sample) return {}
  return JSON.parse(JSON.stringify(sample))
}

export function stringifyPayload(payload) {
  try {
    return JSON.stringify(payload ?? {}, null, 2)
  } catch (error) {
    return '{}'
  }
}

/** 解析 JSON 编辑器内容，返回 `{ value, error }`。 */
export function parsePayloadText(text) {
  const raw = String(text ?? '').trim()
  if (!raw) return { value: {}, error: '' }
  try {
    const parsed = JSON.parse(raw)
    if (parsed === null) return { value: {}, error: '' }
    if (typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { value: null, error: '请求体必须是 JSON 对象' }
    }
    return { value: parsed, error: '' }
  } catch (error) {
    return { value: null, error: `JSON 解析失败：${error.message}` }
  }
}

/** 生成前端侧流式任务 ID（用于 `POST agents/{name}/run/` 的 stream_task_id）。 */
export function createStreamTaskId(prefix = 'agent') {
  const random =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
  return `${prefix}-${random}`
}

/** Agent 结果的步骤时间线 → 统一结构（容错各种后端 step 形状）。 */
export function normalizeAgentSteps(steps) {
  if (!Array.isArray(steps)) return []
  return steps.map((step, index) => {
    if (!step || typeof step !== 'object') {
      return { index: index + 1, node: '', status: '', summary: String(step ?? '') }
    }
    const node = step.node || step.name || step.stage || `step-${index + 1}`
    const status = step.status || (step.error ? 'error' : 'success')
    let summary = step.message || step.summary || step.detail || ''
    if (!summary && step.output !== undefined) {
      try {
        const text = typeof step.output === 'string' ? step.output : JSON.stringify(step.output)
        summary = text.length > 160 ? `${text.slice(0, 160)}…` : text
      } catch (error) {
        summary = ''
      }
    }
    return {
      index: index + 1,
      node: String(node),
      status: String(status),
      summary: String(summary || ''),
      raw: step,
    }
  })
}
