/**
 * 通知中心纯逻辑：渠道元数据、密码掩码判定、邮件/测试载荷构造。
 *
 * 后端契约：
 * - `GET/PUT/PATCH /api/notifications/email-config/`：`password` 读取恒为 `******`，
 *   回传掩码时后端不会覆盖真实密码（serializers.EmailConfigSerializer.validate）。
 * - `POST /api/notifications/test/`：body 支持 `receiver_id` 或
 *   `channel_code`（+ `webhook_url` / `target_address`），并接受 `title`/`content`。
 */

export const EMAIL_PASSWORD_MASK = '******'

export const CHANNEL_META = {
  dingtalk: {
    label: '钉钉',
    description: '钉钉群机器人 Webhook，可在钉钉群「机器人设置」中获取',
    target: 'webhook',
  },
  wechat_work: {
    label: '企业微信',
    description: '企业微信群机器人 Webhook，支持 Markdown 消息',
    target: 'webhook',
  },
  feishu: {
    label: '飞书',
    description: '飞书自定义机器人 Webhook，支持富文本卡片',
    target: 'webhook',
  },
  email: {
    label: '邮件',
    description: 'SMTP 邮件通知，需先在「邮件配置」中完成发件服务配置',
    target: 'email',
  },
  webhook: {
    label: '通用 Webhook',
    description: '任意 HTTP 端点，以 JSON POST 形式投递通知内容',
    target: 'webhook',
  },
}

export const CHANNEL_OPTIONS = Object.entries(CHANNEL_META).map(([value, meta]) => ({
  value,
  label: meta.label,
  description: meta.description,
}))

export function channelMeta(code) {
  return CHANNEL_META[code] || { label: code || '未知渠道', description: '', target: 'webhook' }
}

export function channelLabel(code) {
  return channelMeta(code).label
}

export function isWebhookChannel(code) {
  return channelMeta(code).target === 'webhook'
}

export function isEmailChannel(code) {
  return channelMeta(code).target === 'email'
}

/** 后端回显的密码掩码（不允许写回真实密码）。 */
export function isMaskedPassword(value) {
  return typeof value === 'string' && (value === EMAIL_PASSWORD_MASK || value === '***')
}

/** SMTP 表单默认值。 */
export function emptyEmailForm(overrides = {}) {
  return {
    host: '',
    port: 465,
    username: '',
    password: '',
    from_email: '',
    use_ssl: true,
    use_tls: false,
    is_active: true,
    passwordMasked: '',
    ...overrides,
  }
}

/** 记录 → 表单：密码字段恒为空，掩码只用于占位提示。 */
export function emailRecordToForm(record = {}) {
  return {
    host: record.host || '',
    port: Number(record.port ?? 465),
    username: record.username || '',
    password: '',
    from_email: record.from_email || '',
    use_ssl: record.use_ssl !== false,
    use_tls: Boolean(record.use_tls),
    is_active: record.is_active !== false,
    passwordMasked: record.password || '',
  }
}

/**
 * 表单 → `PUT/PATCH /email-config/` 载荷。
 * 密码留空或仍为掩码时不提交该字段，避免覆盖真实密码。
 */
export function buildEmailConfigPayload(form = {}) {
  const host = String(form.host || '').trim()
  if (!host) return { payload: null, error: '请填写 SMTP 主机地址' }
  const port = Number(form.port)
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return { payload: null, error: '端口必须是 1~65535 的整数' }
  }
  const fromEmail = String(form.from_email || '').trim()
  if (fromEmail && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(fromEmail)) {
    return { payload: null, error: '发件人邮箱格式不正确' }
  }
  if (form.use_ssl && form.use_tls) {
    return { payload: null, error: 'SSL 与 TLS 不能同时启用' }
  }

  const payload = {
    host,
    port,
    username: String(form.username || '').trim(),
    from_email: fromEmail,
    use_ssl: Boolean(form.use_ssl),
    use_tls: Boolean(form.use_tls),
    is_active: form.is_active !== false,
  }

  const password = String(form.password || '')
  if (password && !isMaskedPassword(password)) {
    payload.password = password
  }

  return { payload, error: '' }
}

/** 收件人地址（逗号/分号分隔）→ 数组。 */
export function splitEmails(value) {
  return String(value || '')
    .replace(/[；;，]/g, ',')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

/**
 * 测试发送载荷：优先使用接收人；否则要求 channel_code（按渠道补充 webhook / 邮箱）。
 */
export function buildTestPayload(form = {}) {
  const title = String(form.title || '').trim() || '通知测试'
  const content = String(form.content || '').trim()
  const receiverId = form.receiverId ?? ''

  if (receiverId !== '' && receiverId !== null && receiverId !== undefined) {
    const payload = { receiver_id: Number(receiverId), title }
    if (content) payload.content = content
    return { payload, error: '' }
  }

  const channelCode = String(form.channelCode || '').trim()
  if (!channelCode) return { payload: null, error: '请选择通知接收人或通知渠道' }

  const payload = { channel_code: channelCode, title }
  if (content) payload.content = content

  const webhookUrl = String(form.webhookUrl || '').trim()
  const targetAddress = splitEmails(form.targetAddress).join(',')
  if (isWebhookChannel(channelCode)) {
    if (!webhookUrl) return { payload: null, error: '该渠道需要填写 Webhook 地址' }
    if (!/^https?:\/\//i.test(webhookUrl)) {
      return { payload: null, error: 'Webhook 地址必须以 http:// 或 https:// 开头' }
    }
    payload.webhook_url = webhookUrl
  }
  if (isEmailChannel(channelCode)) {
    if (!targetAddress) return { payload: null, error: '邮件渠道需要填写收件邮箱' }
    payload.target_address = targetAddress
  }
  if (webhookUrl) payload.webhook_url = webhookUrl
  if (targetAddress) payload.target_address = targetAddress

  return { payload, error: '' }
}

/** 接收人一行展示的目标地址。 */
export function receiverTargetLabel(receiver = {}) {
  if (receiver.channel_code === 'email') {
    return splitEmails(receiver.target_address).join('、') || '—'
  }
  return receiver.webhook_url || '—'
}

/** 通知日志状态 → 展示文案（与 utils/format 的通用状态区分：success/failed）。 */
export function notificationStatusText(status) {
  if (status === 'success') return '成功'
  if (status === 'failed') return '失败'
  return status || '—'
}
