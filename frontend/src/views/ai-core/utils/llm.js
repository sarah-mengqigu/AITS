/**
 * LLM 配置相关的纯逻辑（便于单测）：选项字典、API Key 掩码判定、提交载荷构造。
 *
 * 与后端契约对齐（backend/apps/ai_core/serializers.py）：
 * - 读取时 `api_key` 恒为掩码 `sk-****<后 4 位>`；
 * - 提交时若把掩码原样回传，后端不会覆盖真实 key；
 * - 因此前端在编辑态应「掩码只展示、绝不回写」，留空表示不修改。
 */

export const MASK_PREFIX = 'sk-****'

export const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'qwen', label: '通义千问' },
  { value: 'huggingface', label: 'HuggingFace' },
  { value: 'azure', label: 'Azure OpenAI' },
  { value: 'mock', label: 'Mock（离线确定性）' },
]

export const MODEL_TYPE_OPTIONS = [
  { value: 'text', label: '文本模型' },
  { value: 'vision', label: '视觉模型' },
]

/** 各 provider 的默认 Base URL（新建时用于快捷填充，不会覆盖用户已填值）。 */
export const PROVIDER_BASE_URLS = {
  openai: 'https://api.openai.com/v1',
  deepseek: 'https://api.deepseek.com/v1',
  qwen: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  huggingface: 'https://api-inference.huggingface.co',
  azure: '',
  mock: '',
}

export const PROVIDER_LABELS = PROVIDER_OPTIONS.reduce((acc, item) => {
  acc[item.value] = item.label
  return acc
}, {})

export const MODEL_TYPE_LABELS = MODEL_TYPE_OPTIONS.reduce((acc, item) => {
  acc[item.value] = item.label
  return acc
}, {})

/** 是否为后端回显的掩码值（绝不当作真实 key 使用）。 */
export function isMaskedApiKey(value) {
  return typeof value === 'string' && value.startsWith(MASK_PREFIX)
}

/** 与后端 `mask_api_key` 保持一致的本地掩码实现。 */
export function maskApiKey(value) {
  const raw = typeof value === 'string' ? value : ''
  if (!raw) return ''
  const tail = raw.length >= 4 ? raw.slice(-4) : raw
  return `${MASK_PREFIX}${tail}`
}

export function providerLabel(value) {
  return PROVIDER_LABELS[value] || value || '—'
}

export function modelTypeLabel(value) {
  return MODEL_TYPE_LABELS[value] || value || '—'
}

/** 空表单（新建默认值：mock provider，便于离线环境一条命令跑通）。 */
export function emptyLlmForm(overrides = {}) {
  return {
    scope: 'global',
    project: null,
    name: '',
    provider: 'mock',
    model_name: '',
    api_key: '',
    base_url: '',
    model_type: 'text',
    temperature: 0.7,
    max_tokens: 2048,
    is_default: false,
    is_active: true,
    extraText: '{}',
    ...overrides,
  }
}

/**
 * 记录 → 表单。`apiKeyMasked` 只用于占位提示，`form.api_key` 恒为空，
 * 从结构上避免把掩码写回后端。
 */
export function llmRecordToForm(record = {}) {
  const extra = record.extra && typeof record.extra === 'object' ? record.extra : {}
  return {
    scope: record.project ? 'project' : 'global',
    project: record.project ?? null,
    name: record.name || '',
    provider: record.provider || 'mock',
    model_name: record.model_name || '',
    api_key: '',
    base_url: record.base_url || '',
    model_type: record.model_type || 'text',
    temperature: Number(record.temperature ?? 0.7),
    max_tokens: Number(record.max_tokens ?? 2048),
    is_default: Boolean(record.is_default),
    is_active: record.is_active !== false,
    extraText: JSON.stringify(extra, null, 2),
    apiKeyMasked: record.api_key || '',
  }
}

function parseJsonObject(text) {
  const raw = String(text ?? '').trim()
  if (!raw) return { value: {} }
  try {
    const parsed = JSON.parse(raw)
    if (parsed === null) return { value: {} }
    if (typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { error: '扩展参数必须是 JSON 对象' }
    }
    return { value: parsed }
  } catch (error) {
    return { error: `扩展参数不是合法 JSON：${error.message}` }
  }
}

/**
 * 表单 → 提交载荷。
 * 返回 `{ payload, error }`，`error` 非空时不应发起请求。
 */
export function buildLlmPayload(form = {}) {
  const name = String(form.name || '').trim()
  if (!name) return { payload: null, error: '配置名称不能为空' }

  const provider = form.provider || 'mock'
  const modelType = form.model_type || 'text'
  const temperature = Number(form.temperature)
  if (!Number.isFinite(temperature) || temperature < 0 || temperature > 2) {
    return { payload: null, error: 'temperature 必须在 0~2 之间' }
  }
  const maxTokens = Number(form.max_tokens)
  if (!Number.isInteger(maxTokens) || maxTokens < 1) {
    return { payload: null, error: 'max_tokens 必须为大于 0 的整数' }
  }

  const extraParsed = parseJsonObject(form.extraText)
  if (extraParsed.error) return { payload: null, error: extraParsed.error }

  const payload = {
    project: form.scope === 'project' ? form.project ?? null : null,
    name,
    provider,
    model_name: String(form.model_name || '').trim(),
    base_url: String(form.base_url || '').trim(),
    model_type: modelType,
    temperature,
    max_tokens: maxTokens,
    is_default: Boolean(form.is_default),
    is_active: form.is_active !== false,
    extra: extraParsed.value,
  }

  const apiKey = String(form.api_key || '').trim()
  // 空值 = 不修改；掩码 = 后端回显，绝不回写真实 key。
  if (apiKey && !isMaskedApiKey(apiKey)) {
    payload.api_key = apiKey
  }

  return { payload, error: '' }
}

/** 编辑态 API Key 输入框占位文案。 */
export function apiKeyPlaceholder({ isEdit = false, masked = '' } = {}) {
  if (isEdit) {
    return masked ? `已配置 ${masked}，留空表示不修改` : '未配置 API Key，填写后保存'
  }
  return '填写 API Key（provider=mock 时可留空）'
}
