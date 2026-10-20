/**
 * 监控大盘内部纯逻辑工具：时间范围映射、执行趋势前端分桶、ECharts option、
 * Prometheus / Grafana 外部系统说明。不依赖 Vue / Element Plus，便于单测。
 */

import dayjs from 'dayjs'

import { normalizeExecutionRow } from '@/views/performance/utils'

/** 时间范围选项：短区间映射 days=1，并在前端按小时桶聚合趋势。 */
export const RANGE_OPTIONS = [
  { key: '1h', label: '最近 1h', days: 1, hours: 1, bucketMs: 5 * 60 * 1000, buckets: 12 },
  { key: '6h', label: '最近 6h', days: 1, hours: 6, bucketMs: 30 * 60 * 1000, buckets: 12 },
  { key: '24h', label: '最近 24h', days: 1, hours: 24, bucketMs: 2 * 60 * 60 * 1000, buckets: 12 },
  { key: '7d', label: '最近 7d', days: 7, hours: 0, bucketMs: 24 * 60 * 60 * 1000, buckets: 7 },
]

const DEFAULT_RANGE_KEY = '24h'

/** 取时间范围选项；未知 key 兜底 24h。 */
export function getRangeOption(key) {
  return RANGE_OPTIONS.find((item) => item.key === key) || RANGE_OPTIONS.find((item) => item.key === DEFAULT_RANGE_KEY)
}

/** 时间范围 → dashboard 接口 days 参数。 */
export function rangeToDays(key) {
  return getRangeOption(key).days
}

function round(value, digits = 2) {
  const number = Number(value)
  if (!Number.isFinite(number)) return 0
  return Number(number.toFixed(digits))
}

/** 执行记录时间戳（毫秒）；兼容 created_at / started_at / camelCase。 */
export function executionTimestamp(row) {
  if (!row || typeof row !== 'object') return null
  const value = row.createdAt ?? row.created_at ?? row.startedAt ?? row.started_at
  if (!value) return null
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.valueOf() : null
}

/** 按所选时间范围过滤执行记录（仅短区间需要，7d 直接使用后端 trend）。 */
export function filterExecutionsByRange(executions = [], range, now = Date.now()) {
  const option = typeof range === 'string' ? getRangeOption(range) : range || getRangeOption(DEFAULT_RANGE_KEY)
  if (!Array.isArray(executions)) return []
  if (!option.hours) return executions.slice()
  const cutoff = now - option.hours * 60 * 60 * 1000
  return executions.filter((row) => {
    const timestamp = executionTimestamp(row)
    return timestamp !== null && timestamp >= cutoff && timestamp <= now
  })
}

/**
 * 用执行记录在前端构建趋势（短区间按小时桶，弥补 dashboard 只按天聚合）。
 * 返回 { label, date, executions, passed, failed, avgTps, avgP95, avgErrorRate }。
 */
export function buildTrendFromExecutions(executions = [], range, now = Date.now()) {
  const option = typeof range === 'string' ? getRangeOption(range) : range || getRangeOption(DEFAULT_RANGE_KEY)
  const bucketMs = option.bucketMs
  const buckets = option.buckets
  // 24h 窗口会跨天，x 轴补上日期避免 “18:10 → 20:10” 这类歧义。
  const labelFormat = option.hours >= 24 ? 'MM-DD HH:mm' : 'HH:mm'
  const rows = Array.from({ length: buckets }, (_, index) => {
    const bucketStart = now - (buckets - index) * bucketMs
    return {
      label: dayjs(bucketStart).format(labelFormat),
      date: dayjs(bucketStart).format('YYYY-MM-DD HH:mm'),
      executions: 0,
      passed: 0,
      failed: 0,
      _tps: 0,
      _p95: 0,
      _errorRate: 0,
      _samples: 0,
    }
  })

  if (Array.isArray(executions)) {
    executions.forEach((row) => {
      const timestamp = executionTimestamp(row)
      if (timestamp === null || timestamp > now || timestamp < now - buckets * bucketMs) return
      const indexFromEnd = Math.floor((now - timestamp) / bucketMs)
      const index = buckets - 1 - Math.min(Math.max(indexFromEnd, 0), buckets - 1)
      const bucket = rows[index]
      if (!bucket) return
      bucket.executions += 1
      const status = String(row.status || '').toLowerCase()
      if (status === 'passed') bucket.passed += 1
      else if (status === 'failed' || status === 'error') bucket.failed += 1
      bucket._samples += 1
      bucket._tps += Number(row.avgTps ?? row.avg_tps ?? 0) || 0
      bucket._p95 += Number(row.p95 ?? row.p95_response_time ?? 0) || 0
      bucket._errorRate += Number(row.errorRate ?? row.error_rate ?? 0) || 0
    })
  }

  return rows.map(({ _tps, _p95, _errorRate, _samples, ...bucket }) => ({
    ...bucket,
    avgTps: _samples ? round(_tps / _samples) : 0,
    avgP95: _samples ? round(_p95 / _samples) : 0,
    avgErrorRate: _samples ? round(_errorRate / _samples, 4) : 0,
  }))
}

/** 原始执行列表 → 视图行（复用性能模块转换规则，按时间倒序）。 */
export function normalizeExecutionRows(rows = []) {
  if (!Array.isArray(rows)) return []
  return rows
    .filter((row) => row && typeof row === 'object')
    .map(normalizeExecutionRow)
    .sort((left, right) => {
      const leftTime = executionTimestamp(left) || 0
      const rightTime = executionTimestamp(right) || 0
      return rightTime - leftTime
    })
}

// ---------------------------------------------------------------------------
// ECharts option 构建
// ---------------------------------------------------------------------------
const AXIS_LABEL_COLOR = '#94a3b8'
const SPLIT_LINE_COLOR = '#eef2f7'

function baseGrid() {
  return { left: 48, right: 52, top: 38, bottom: 30, containLabel: true }
}

function categoryAxis(trend) {
  return {
    type: 'category',
    boundaryGap: false,
    data: trend.map((row) => row.label || row.date || ''),
    // 短区间 12 个小时桶时强制展示全部标签并旋转，避免首尾时间被自动省略。
    axisLabel: {
      color: AXIS_LABEL_COLOR,
      fontSize: trend.length > 8 ? 10 : 11,
      interval: 0,
      rotate: trend.length > 8 ? 30 : 0,
    },
    axisLine: { lineStyle: { color: '#e5e7eb' } },
    axisTick: { show: false },
  }
}

function valueAxis(name, extra = {}) {
  return {
    type: 'value',
    name,
    nameTextStyle: { color: AXIS_LABEL_COLOR, fontSize: 11 },
    axisLabel: { color: AXIS_LABEL_COLOR, fontSize: 11 },
    splitLine: { lineStyle: { color: SPLIT_LINE_COLOR, type: 'dashed' } },
    ...extra,
  }
}

/** 执行数 + 通过/失败堆叠折线。 */
export function buildExecutionTrendOption(trend = []) {
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['执行数', '通过', '失败'], top: 0, textStyle: { fontSize: 11 } },
    grid: baseGrid(),
    xAxis: categoryAxis(trend),
    yAxis: valueAxis('次', { minInterval: 1 }),
    series: [
      {
        name: '执行数',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        data: trend.map((row) => row.executions),
        lineStyle: { width: 2, color: '#2563eb', type: 'dashed' },
        itemStyle: { color: '#2563eb' },
      },
      // 堆叠顺序：失败在下、通过在上，避免无失败时红色折线覆盖绿色通过线。
      {
        name: '失败',
        type: 'line',
        stack: 'result',
        smooth: true,
        symbolSize: 5,
        data: trend.map((row) => row.failed),
        lineStyle: { color: '#dc2626' },
        itemStyle: { color: '#dc2626' },
        areaStyle: { opacity: 0.12, color: '#dc2626' },
      },
      {
        name: '通过',
        type: 'line',
        stack: 'result',
        smooth: true,
        symbolSize: 5,
        data: trend.map((row) => row.passed),
        lineStyle: { color: '#16a34a' },
        itemStyle: { color: '#16a34a' },
        areaStyle: { opacity: 0.12, color: '#16a34a' },
      },
    ],
  }
}

/** TPS 与 P95 双 Y 轴折线。 */
export function buildTpsLatencyOption(trend = []) {
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['平均 TPS', '平均 P95'], top: 0, textStyle: { fontSize: 11 } },
    grid: baseGrid(),
    xAxis: categoryAxis(trend),
    yAxis: [
      valueAxis('TPS', { min: 0 }),
      valueAxis('P95 (ms)', { min: 0, splitLine: { show: false } }),
    ],
    series: [
      {
        name: '平均 TPS',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        yAxisIndex: 0,
        data: trend.map((row) => round(row.avgTps)),
        lineStyle: { width: 2, color: '#2563eb' },
        itemStyle: { color: '#2563eb' },
        areaStyle: { opacity: 0.1, color: '#2563eb' },
      },
      {
        name: '平均 P95',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        yAxisIndex: 1,
        data: trend.map((row) => round(row.avgP95)),
        lineStyle: { width: 2, color: '#d97706', type: 'dashed' },
        itemStyle: { color: '#d97706' },
      },
    ],
  }
}

/** 错误率折线（百分数）。 */
export function buildErrorRateOption(trend = []) {
  const maxPercent = trend.reduce(
    (acc, row) => Math.max(acc, Number(row.avgErrorRate || 0) * 100),
    0,
  )
  // 至少留到 1%，保证 1% 通过阈值虚线可见。
  const yMax = Math.max(1, Math.ceil(maxPercent * 1.15))
  return {
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value) => `${Number(value).toFixed(2)}%`,
    },
    legend: { data: ['平均错误率'], top: 0, textStyle: { fontSize: 11 } },
    grid: baseGrid(),
    xAxis: categoryAxis(trend),
    yAxis: valueAxis('%', {
      min: 0,
      max: yMax,
      axisLabel: { color: AXIS_LABEL_COLOR, fontSize: 11, formatter: '{value}%' },
    }),
    series: [
      {
        name: '平均错误率',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        data: trend.map((row) => round(Number(row.avgErrorRate || 0) * 100)),
        lineStyle: { width: 2, color: '#dc2626' },
        itemStyle: { color: '#dc2626' },
        areaStyle: { opacity: 0.12, color: '#dc2626' },
        markLine: {
          silent: true,
          symbol: 'none',
          label: { formatter: '1% 阈值', fontSize: 10, color: '#94a3b8' },
          lineStyle: { color: '#f59e0b', type: 'dashed' },
          data: [{ yAxis: 1 }],
        },
      },
    ],
  }
}

/** 诊断状态分布饼图。 */
export function buildDiagnosisPieOption(diagnosis = {}) {
  const source = diagnosis && typeof diagnosis === 'object' ? diagnosis : {}
  const data = [
    { name: '待处理', value: Number(source.pending) || 0, itemStyle: { color: '#f59e0b' } },
    { name: '已解决', value: Number(source.resolved) || 0, itemStyle: { color: '#16a34a' } },
    { name: '已忽略', value: Number(source.ignored) || 0, itemStyle: { color: '#94a3b8' } },
  ]
  return {
    tooltip: { trigger: 'item', valueFormatter: (value) => `${value} 条` },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    series: [
      {
        name: '诊断状态',
        type: 'pie',
        radius: ['46%', '70%'],
        center: ['50%', '44%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        emphasis: { label: { show: true, fontSize: 13, fontWeight: 600 } },
        data,
      },
    ],
  }
}

// ---------------------------------------------------------------------------
// 外部监控系统（Grafana / Prometheus）
// ---------------------------------------------------------------------------
/** Grafana 地址：`VITE_GRAFANA_URL` 未配置时为空字符串。 */
export function readGrafanaUrl() {
  const raw = String(import.meta.env?.VITE_GRAFANA_URL || '').trim()
  return raw.replace(/\/+$/, '')
}

export const GRAFANA_URL = readGrafanaUrl()
export const GRAFANA_CONFIGURED = Boolean(GRAFANA_URL)

/** Prometheus 指标端点：开发环境直连后端 8000，生产走同源 /metrics。 */
export function metricsEndpointUrl() {
  const override = String(import.meta.env?.VITE_METRICS_URL || '').trim()
  if (override) return override
  if (import.meta.env?.DEV && typeof window !== 'undefined' && window.location?.hostname) {
    return `http://${window.location.hostname}:8000/metrics`
  }
  return '/metrics'
}

export const METRICS_PATH = '/metrics'

/** 未配置 Grafana 时的本地监控栈引导。 */
export const MONITORING_GUIDE = {
  composeCommand: 'cd backend/aits_monitor && docker-compose up -d',
  grafanaUrl: 'http://localhost:3000',
  prometheusUrl: 'http://localhost:9090',
  adminUser: 'admin',
  adminPassword: 'admin',
  envHint: 'VITE_GRAFANA_URL=http://localhost:3000',
  webhookPath: '/api/performance/grafana/webhook/',
  dashboardFile: 'backend/aits_monitor/grafana/dashboards/aits-overview.json',
}

/** Prometheus 抓取任务说明（与 backend/aits_monitor/prometheus/prometheus.yml 一致）。 */
export const PROMETHEUS_JOBS = [
  {
    name: 'aits-backend',
    target: 'host.docker.internal:8000',
    metricsPath: '/metrics',
    labels: 'instance=aits-backend · role=platform',
    description: 'AITS 后端业务 / Agent / 执行指标',
    mode: 'static_configs',
  },
  {
    name: 'locust-performance',
    target: 'host.docker.internal:8089',
    metricsPath: '/metrics',
    labels: 'instance=aits-locust · role=load-generator',
    description: '压测执行期间 Locust 暴露的实时指标',
    mode: 'static_configs',
  },
  {
    name: 'windows-exporter',
    target: 'targets.json（File SD）',
    metricsPath: '/metrics',
    labels: 'instance=<压测机> · role=load-generator',
    description: '压测机 Windows Exporter；执行时由后端自动写入 File SD',
    mode: 'file_sd_configs · 30s 刷新',
  },
]
