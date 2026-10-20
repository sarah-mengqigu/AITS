/**
 * 用量统计的纯逻辑转换：`GET /api/ai/usage-stats/` 的响应 →
 * ECharts 可直接消费的序列数据。
 *
 * 后端返回结构（backend/apps/ai_core/views.py::UsageStatsView）：
 * {
 *   total: {requests, success, failed, prompt_tokens, completion_tokens,
 *           total_tokens, avg_response_time_ms},
 *   by_day:   [{date, requests, success, failed, total_tokens}],
 *   by_model: [{model, provider, requests, total_tokens}],
 *   by_agent: [{agent, requests, total_tokens}],
 * }
 */

export function toNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

export function normalizeUsageStats(raw = {}) {
  const total = raw && typeof raw.total === 'object' && raw.total ? raw.total : {}
  return {
    total: {
      requests: toNumber(total.requests),
      success: toNumber(total.success),
      failed: toNumber(total.failed),
      promptTokens: toNumber(total.prompt_tokens),
      completionTokens: toNumber(total.completion_tokens),
      totalTokens: toNumber(total.total_tokens),
      avgResponseTimeMs: toNumber(total.avg_response_time_ms),
    },
    byDay: Array.isArray(raw?.by_day) ? raw.by_day : [],
    byModel: Array.isArray(raw?.by_model) ? raw.by_model : [],
    byAgent: Array.isArray(raw?.by_agent) ? raw.by_agent : [],
  }
}

/** 按天序列（默认取最近 N 天，后端已按日期升序）。 */
export function buildDaySeries(byDay = [], { limit = 14 } = {}) {
  const rows = Array.isArray(byDay) ? byDay.filter(Boolean) : []
  const sliced = limit > 0 ? rows.slice(-limit) : rows
  return {
    dates: sliced.map((row) => String(row.date || '')),
    requests: sliced.map((row) => toNumber(row.requests)),
    success: sliced.map((row) => toNumber(row.success)),
    failed: sliced.map((row) => toNumber(row.failed)),
    tokens: sliced.map((row) => toNumber(row.total_tokens)),
  }
}

/** 按 Agent 序列：请求数降序，取前 N 个。 */
export function buildAgentSeries(byAgent = [], { limit = 8 } = {}) {
  const rows = (Array.isArray(byAgent) ? byAgent.filter(Boolean) : [])
    .map((row) => ({
      name: String(row.agent || 'unknown'),
      requests: toNumber(row.requests),
      tokens: toNumber(row.total_tokens),
    }))
    .sort((a, b) => b.requests - a.requests || b.tokens - a.tokens)
  const sliced = limit > 0 ? rows.slice(0, limit) : rows
  return {
    names: sliced.map((row) => row.name),
    requests: sliced.map((row) => row.requests),
    tokens: sliced.map((row) => row.tokens),
  }
}

/** 按模型序列：请求数降序，取前 N 个。 */
export function buildModelSeries(byModel = [], { limit = 8 } = {}) {
  const rows = (Array.isArray(byModel) ? byModel.filter(Boolean) : [])
    .map((row) => ({
      name: String(row.model || 'mock'),
      provider: String(row.provider || ''),
      requests: toNumber(row.requests),
      tokens: toNumber(row.total_tokens),
    }))
    .sort((a, b) => b.requests - a.requests || b.tokens - a.tokens)
  const sliced = limit > 0 ? rows.slice(0, limit) : rows
  return {
    models: sliced.map((row) => row.name),
    providers: sliced.map((row) => row.provider),
    requests: sliced.map((row) => row.requests),
    tokens: sliced.map((row) => row.tokens),
  }
}

export function hasDayData(series) {
  return Boolean(series && series.dates && series.dates.length)
}

/** 用量趋势折线图 option（请求数 / Token 双 Y 轴）。 */
export function buildDayChartOption(series) {
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['请求数', 'Token 用量'], right: 0, top: 0 },
    grid: { left: 8, right: 8, top: 40, bottom: 4, containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: series?.dates || [],
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisLabel: { color: '#64748b' },
    },
    yAxis: [
      {
        type: 'value',
        name: '请求数',
        minInterval: 1,
        splitLine: { lineStyle: { color: '#f1f5f9' } },
        axisLabel: { color: '#64748b' },
      },
      {
        type: 'value',
        name: 'Token',
        splitLine: { show: false },
        axisLabel: { color: '#64748b' },
      },
    ],
    series: [
      {
        name: '请求数',
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.12 },
        itemStyle: { color: '#2563eb' },
        data: series?.requests || [],
      },
      {
        name: 'Token 用量',
        type: 'line',
        smooth: true,
        yAxisIndex: 1,
        itemStyle: { color: '#7c3aed' },
        data: series?.tokens || [],
      },
    ],
  }
}

/** 按 Agent 聚合柱状图 option。 */
export function buildAgentChartOption(series) {
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 8, right: 12, top: 20, bottom: 4, containLabel: true },
    xAxis: {
      type: 'category',
      data: series?.names || [],
      axisLabel: { color: '#64748b', interval: 0, rotate: 20 },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: '#f1f5f9' } },
      axisLabel: { color: '#64748b' },
    },
    series: [
      {
        name: '请求数',
        type: 'bar',
        barMaxWidth: 28,
        itemStyle: { color: '#0d9488', borderRadius: [4, 4, 0, 0] },
        data: series?.requests || [],
      },
    ],
  }
}

/** 按模型聚合圆环图 option。 */
export function buildModelChartOption(series) {
  const names = series?.models || []
  const values = (series?.requests || []).map((count, index) => ({
    name: names[index],
    value: count,
  }))
  return {
    tooltip: { trigger: 'item', formatter: '{b}<br/>请求数：{c}（{d}%）' },
    legend: { orient: 'vertical', right: 8, top: 'center', type: 'scroll' },
    series: [
      {
        name: '模型请求数',
        type: 'pie',
        radius: ['46%', '70%'],
        center: ['38%', '50%'],
        avoidLabelOverlap: true,
        label: { show: false },
        data: values,
      },
    ],
  }
}
