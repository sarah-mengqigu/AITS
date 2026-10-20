<template>
  <div class="page-container monitoring-page">
    <PageHeader
      title="监控大盘"
      :subtitle="scopeLabel"
      description="性能执行趋势、TPS / P95 / 错误率、AI 诊断状态与 Prometheus / Grafana 联动"
    >
      <template #actions>
        <el-button v-if="GRAFANA_CONFIGURED" :icon="Link" @click="openGrafana">
          打开 Grafana
        </el-button>
        <el-button
          :icon="DataLine"
          tag="a"
          :href="metricsHref"
          target="_blank"
          rel="noopener noreferrer"
        >
          Prometheus 指标（/metrics）
        </el-button>
        <el-button type="primary" :icon="Refresh" :loading="loading" @click="loadAll">
          刷新
        </el-button>
      </template>
    </PageHeader>

    <div class="page-card filter-bar">
      <div class="filter-bar__left">
        <span class="filter-bar__label">时间范围</span>
        <el-radio-group v-model="rangeKey" size="small" @change="loadAll">
          <el-radio-button v-for="option in RANGE_OPTIONS" :key="option.key" :value="option.key">
            {{ option.label }}
          </el-radio-button>
        </el-radio-group>
        <span class="filter-bar__label filter-bar__label--gap">项目范围</span>
        <el-radio-group v-model="scope" size="small" @change="handleScopeChange">
          <el-radio-button value="all">全部项目</el-radio-button>
          <el-radio-button value="project" :disabled="!projectId">
            当前项目<template v-if="currentProject">（{{ currentProject.name }}）</template>
          </el-radio-button>
        </el-radio-group>
      </div>
      <div class="filter-bar__right">
        <span class="text-small text-muted">{{ trendGranularity }}</span>
        <span v-if="lastLoadedAt" class="text-small text-muted">
          更新于 {{ lastLoadedAt }}
        </span>
      </div>
    </div>

    <el-alert v-if="projectError" :title="projectError" type="warning" show-icon :closable="false" />
    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
      description="监控数据加载失败。请确认后端服务与数据库可用后点击「刷新」重试；页面已降级为 0 值展示。"
    />

    <section class="monitor-stats">
      <StatCard
        label="执行数"
        :value="formatNumber(dashboard.summary.executions)"
        :loading="loading"
        :icon="VideoPlay"
        icon-color="#2563eb"
        icon-bg="#e9effd"
        :hint="statsHint"
      />
      <StatCard
        label="通过 / 失败"
        :value="`${formatNumber(dashboard.summary.passed)} / ${formatNumber(dashboard.summary.failedTotal)}`"
        :loading="loading"
        :icon="CircleCheck"
        icon-color="#16a34a"
        icon-bg="#dcfce7"
        hint="失败含 error 状态"
      />
      <StatCard
        label="平均 TPS"
        :value="formatTps(dashboard.summary.avgTps)"
        suffix="req/s"
        :loading="loading"
        :icon="TrendCharts"
        icon-color="#d97706"
        icon-bg="#fef3c7"
        hint="所选范围内执行平均值"
      />
      <StatCard
        label="平均 P95"
        :value="formatLatency(dashboard.summary.avgP95)"
        :loading="loading"
        :icon="Timer"
        icon-color="#0284c7"
        icon-bg="#e0f2fe"
        hint="95% 请求响应时间"
      />
      <StatCard
        label="平均错误率"
        :value="formatErrorRate(dashboard.summary.avgErrorRate)"
        :loading="loading"
        :icon="Warning"
        icon-color="#dc2626"
        icon-bg="#fee2e2"
        hint="通过阈值为 1%"
      />
      <StatCard
        label="AI 诊断待处理"
        :value="formatNumber(dashboard.diagnosis.pending)"
        :loading="loading"
        :icon="MagicStick"
        icon-color="#7c3aed"
        icon-bg="#ede9fe"
        :hint="`共 ${dashboard.diagnosis.total} 条诊断记录`"
      />
    </section>

    <section class="chart-grid">
      <div class="page-card">
        <div class="card-title">
          <span>执行趋势</span>
          <span class="text-small text-muted">执行数 + 通过 / 失败堆叠</span>
        </div>
        <VChart v-if="hasTrend" class="chart" :option="trendOption" autoresize />
        <EmptyState
          v-else
          title="所选范围内暂无执行数据"
          description="运行一次性能场景后，执行数、通过/失败与 TPS 趋势会在这里展示。"
        >
          <el-button type="primary" @click="goPerformance">去运行压测</el-button>
        </EmptyState>
      </div>

      <div class="page-card">
        <div class="card-title">
          <span>诊断状态分布</span>
          <span class="text-small text-muted">pending / resolved / ignored</span>
        </div>
        <VChart v-if="hasDiagnosis" class="chart" :option="diagnosisPieOption" autoresize />
        <EmptyState
          v-else
          title="暂无 AI 诊断记录"
          description="Grafana 告警会通过 Webhook 自动生成诊断记录。"
        />
      </div>
    </section>

    <section class="chart-grid">
      <div class="page-card">
        <div class="card-title">
          <span>TPS 与 P95</span>
          <span class="text-small text-muted">双 Y 轴 · TPS / P95(ms)</span>
        </div>
        <VChart v-if="hasTrend" class="chart" :option="tpsLatencyOption" autoresize />
        <EmptyState v-else title="暂无 TPS / P95 数据" description="等待压测执行产生指标。" />
      </div>

      <div class="page-card">
        <div class="card-title">
          <span>错误率趋势</span>
          <span class="text-small text-muted">虚线为 1% 通过阈值</span>
        </div>
        <VChart v-if="hasTrend" class="chart" :option="errorRateOption" autoresize />
        <EmptyState v-else title="暂无错误率数据" description="等待压测执行产生指标。" />
      </div>
    </section>

    <div class="page-card">
      <div class="card-title">
        <span>最近执行</span>
        <div class="card-title__actions">
          <span class="text-small text-muted">最多展示 5 条</span>
          <el-button link type="primary" @click="goPerformance">查看全部</el-button>
        </div>
      </div>
      <DataTable
        :data="recentExecutions"
        :loading="loading"
        :show-pagination="false"
        empty-text="暂无执行记录"
        max-height="340"
      >
        <el-table-column label="执行名称" min-width="230" show-overflow-tooltip>
          <template #default="{ row }">{{ row.name }}</template>
        </el-table-column>
        <el-table-column label="场景" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.scenarioName || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <StatusTag :status="row.status" :text="row.statusLabel" :type="row.statusTagType" />
          </template>
        </el-table-column>
        <el-table-column label="TPS" width="100" align="right">
          <template #default="{ row }">{{ formatTps(row.avgTps) }}</template>
        </el-table-column>
        <el-table-column label="P95" width="100" align="right">
          <template #default="{ row }">{{ formatLatency(row.p95) }}</template>
        </el-table-column>
        <el-table-column label="错误率" width="92" align="right">
          <template #default="{ row }">{{ formatErrorRate(row.errorRate) }}</template>
        </el-table-column>
        <el-table-column label="请求数" width="100" align="right">
          <template #default="{ row }">{{ formatNumber(row.totalRequests) }}</template>
        </el-table-column>
        <el-table-column label="触发方式" width="96">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="row.triggerTagType">
              {{ row.triggerLabel }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" width="160">
          <template #default="{ row }">{{ formatDateTime(row.startedAt) }}</template>
        </el-table-column>
        <template #empty>
          <EmptyState
            title="暂无执行记录"
            description="切换到「全部项目」或扩大时间范围，也可以先运行一次性能压测。"
          >
            <el-button type="primary" @click="goPerformance">去性能测试</el-button>
          </EmptyState>
        </template>
      </DataTable>
    </div>

    <!-- 外部系统联动 -->
    <div class="page-card external-card">
      <div class="card-title">
        <span>外部系统联动</span>
        <span class="text-small text-muted">Grafana 面板 · Prometheus 指标抓取</span>
      </div>

      <template v-if="GRAFANA_CONFIGURED">
        <el-alert
          type="success"
          show-icon
          :closable="false"
          :title="`Grafana 已配置：${GRAFANA_URL}`"
          description="可直接打开 Grafana 查看 AITS 概览面板；Prometheus 从后端 /metrics 与 File SD 抓取压测机指标。"
        />
        <div class="external-actions">
          <el-button type="primary" :icon="Link" @click="openGrafana">打开 Grafana</el-button>
          <el-button
            :icon="DataLine"
            tag="a"
            :href="metricsHref"
            target="_blank"
            rel="noopener noreferrer"
          >
            Prometheus 指标端点（/metrics）
          </el-button>
          <el-button :icon="CopyDocument" @click="copyGuideText(MONITORING_GUIDE.composeCommand)">
            复制启动命令
          </el-button>
        </div>
        <p class="external-hint">
          Grafana 默认面板：AITS 概览（{{ MONITORING_GUIDE.dashboardFile }}）；告警 Webhook：
          <span class="mono">{{ MONITORING_GUIDE.webhookPath }}</span>
        </p>
      </template>

      <template v-else>
        <el-alert
          type="info"
          show-icon
          :closable="false"
          title="尚未配置 Grafana 地址，大盘使用 AITS 内置指标"
          description="如需在 Grafana 查看原始 Prometheus 指标与告警面板，可按下方步骤启动本地监控栈，并配置 VITE_GRAFANA_URL。"
        />
        <div class="guide-grid">
          <div class="guide-card">
            <h4>1. 启动监控栈</h4>
            <pre class="guide-code">{{ MONITORING_GUIDE.composeCommand }}</pre>
            <p>包含 Prometheus（{{ MONITORING_GUIDE.prometheusUrl }}）与 Grafana（{{ MONITORING_GUIDE.grafanaUrl }}）。</p>
          </div>
          <div class="guide-card">
            <h4>2. 登录 Grafana</h4>
            <p>
              默认地址
              <a :href="MONITORING_GUIDE.grafanaUrl" target="_blank" rel="noopener noreferrer">
                {{ MONITORING_GUIDE.grafanaUrl }}
              </a>
              ，账号 <code>{{ MONITORING_GUIDE.adminUser }}</code> /
              <code>{{ MONITORING_GUIDE.adminPassword }}</code>。
              数据源与 AITS 概览面板已通过 provisioning 自动加载。
            </p>
          </div>
          <div class="guide-card">
            <h4>3. 前端开启联动</h4>
            <p>在 <code>frontend/.env.local</code> 增加：</p>
            <pre class="guide-code">{{ MONITORING_GUIDE.envHint }}</pre>
            <p>
              重启 dev server 后，本页顶部会显示「打开 Grafana」按钮。后端指标端点：<span
                class="mono"
                >{{ metricsHref }}</span
              >
            </p>
          </div>
          <div class="guide-card">
            <h4>4. 接入告警</h4>
            <p>
              Grafana 告警 Webhook 指向
              <span class="mono">{{ MONITORING_GUIDE.webhookPath }}</span>
              ，收到告警后会自动写入 AI 诊断记录并推送通知。
            </p>
          </div>
        </div>
      </template>

      <div class="prometheus-section">
        <div class="card-title">
          <span>Prometheus 抓取说明</span>
          <span class="text-small text-muted">与 backend/aits_monitor/prometheus/prometheus.yml 一致</span>
        </div>
        <DataTable :data="PROMETHEUS_JOBS" :show-pagination="false" row-key="name">
          <el-table-column prop="name" label="job_name" width="180">
            <template #default="{ row }"><span class="mono">{{ row.name }}</span></template>
          </el-table-column>
          <el-table-column prop="target" label="抓取目标" min-width="190">
            <template #default="{ row }"><span class="mono">{{ row.target }}</span></template>
          </el-table-column>
          <el-table-column prop="metricsPath" label="metrics_path" width="130">
            <template #default="{ row }"><span class="mono">{{ row.metricsPath }}</span></template>
          </el-table-column>
          <el-table-column prop="labels" label="标签" min-width="190" show-overflow-tooltip />
          <el-table-column prop="mode" label="发现方式" min-width="180" show-overflow-tooltip />
          <el-table-column prop="description" label="说明" min-width="240" show-overflow-tooltip />
        </DataTable>
        <p class="external-hint">
          压测执行时后端会自动探测本机出口 IP 并写入 windows-exporter 的 File SD
          （<span class="mono">backend/aits_monitor/prometheus/targets.json</span>，30s 刷新），
          因此压测机无需手工维护 targets；若不需要自动注册可关闭
          <span class="mono">PROMETHEUS_SD_AUTO_UPDATE</span>。
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import {
  CircleCheck,
  CopyDocument,
  DataLine,
  Link,
  MagicStick,
  Refresh,
  Timer,
  TrendCharts,
  VideoPlay,
  Warning,
} from '@element-plus/icons-vue'

import PageHeader from '@/components/PageHeader.vue'
import StatCard from '@/components/StatCard.vue'
import DataTable from '@/components/DataTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyState from '@/components/EmptyState.vue'

import { performanceApi } from '@/api/performance'
import { useProjectStore } from '@/stores/project'
import { formatDateTime, formatNumber } from '@/utils/format'
import {
  formatErrorRate,
  formatLatency,
  formatTps,
  normalizeDashboard,
  readErrorMessage,
} from '@/views/performance/utils'
import {
  GRAFANA_CONFIGURED,
  GRAFANA_URL,
  MONITORING_GUIDE,
  PROMETHEUS_JOBS,
  RANGE_OPTIONS,
  buildDiagnosisPieOption,
  buildErrorRateOption,
  buildExecutionTrendOption,
  buildTpsLatencyOption,
  buildTrendFromExecutions,
  filterExecutionsByRange,
  getRangeOption,
  metricsEndpointUrl,
  normalizeExecutionRows,
} from './utils'

use([
  CanvasRenderer,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  MarkLineComponent,
])

const router = useRouter()
const projectStore = useProjectStore()

const rangeKey = ref('24h')
const scope = ref('all')
const loading = ref(false)
const errorMessage = ref('')
const projectError = ref('')
const dashboard = ref(normalizeDashboard({}))
const rawExecutions = ref([])
const loadedAt = ref(Date.now())
const lastLoadedAt = ref('')

const rangeOption = computed(() => getRangeOption(rangeKey.value))
const projectId = computed(() => projectStore.currentProjectId)
const currentProject = computed(() => projectStore.currentProject)
const scopeLabel = computed(() =>
  scope.value === 'project' && currentProject.value
    ? `项目：${currentProject.value.name}`
    : '全部项目',
)
const trendGranularity = computed(() =>
  rangeOption.value.hours
    ? '指标卡按天后端聚合；最近执行与趋势按所选时间窗在前端聚合'
    : '近 7 天 · 后端按天聚合',
)
const statsHint = computed(() =>
  rangeOption.value.hours
    ? `后端按天聚合（days=${rangeOption.value.days}）· ${scopeLabel.value}`
    : `${rangeOption.value.label} · ${scopeLabel.value}`,
)
const metricsHref = computed(() => metricsEndpointUrl())

const trend = computed(() => {
  if (!rangeOption.value.hours) return dashboard.value.trend
  return buildTrendFromExecutions(rawExecutions.value, rangeOption.value, loadedAt.value)
})
const recentExecutions = computed(() => {
  if (!rangeOption.value.hours) return dashboard.value.recentExecutions.slice(0, 5)
  return filterExecutionsByRange(rawExecutions.value, rangeOption.value, loadedAt.value).slice(0, 5)
})
const hasTrend = computed(() => trend.value.some((row) => row.executions > 0))
const hasDiagnosis = computed(() => dashboard.value.diagnosis.total > 0)

const trendOption = computed(() => buildExecutionTrendOption(trend.value))
const tpsLatencyOption = computed(() => buildTpsLatencyOption(trend.value))
const errorRateOption = computed(() => buildErrorRateOption(trend.value))
const diagnosisPieOption = computed(() => buildDiagnosisPieOption(dashboard.value.diagnosis))

function scopeParams() {
  return scope.value === 'project' && projectId.value ? { project: projectId.value } : {}
}

async function loadAll() {
  loading.value = true
  errorMessage.value = ''
  loadedAt.value = Date.now()
  const requests = [performanceApi.dashboard({ days: rangeOption.value.days, ...scopeParams() })]
  if (rangeOption.value.hours) {
    requests.push(
      performanceApi.listExecutions({
        ...scopeParams(),
        page_size: 200,
        ordering: '-created_at',
      }),
    )
  }
  const results = await Promise.allSettled(requests)
  const dashboardResult = results[0]
  if (dashboardResult.status === 'fulfilled') {
    dashboard.value = normalizeDashboard(dashboardResult.value)
  } else {
    dashboard.value = normalizeDashboard({})
    errorMessage.value = readErrorMessage(dashboardResult.reason, '监控数据加载失败')
  }
  if (rangeOption.value.hours) {
    const executionsResult = results[1]
    if (executionsResult?.status === 'fulfilled') {
      const list = Array.isArray(executionsResult.value?.results)
        ? executionsResult.value.results
        : []
      rawExecutions.value = normalizeExecutionRows(list)
    } else {
      rawExecutions.value = []
      if (!errorMessage.value && executionsResult) {
        errorMessage.value = readErrorMessage(executionsResult.reason, '执行趋势加载失败')
      }
    }
  } else {
    rawExecutions.value = []
  }
  lastLoadedAt.value = formatDateTime(new Date())
  loading.value = false
}

function handleScopeChange(value) {
  if (value === 'project' && !projectId.value) {
    scope.value = 'all'
    ElMessage.warning('当前没有选中的项目，已切换为全部项目')
    loadAll()
    return
  }
  loadAll()
}

function openGrafana() {
  if (!GRAFANA_CONFIGURED) return
  window.open(GRAFANA_URL, '_blank', 'noopener,noreferrer')
}

function goPerformance() {
  router.push('/performance')
}

async function copyGuideText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = text
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    ElMessage.error('复制失败，请手动选择命令复制')
  }
}

onMounted(async () => {
  if (!projectStore.loaded) {
    try {
      await projectStore.fetchProjects()
    } catch (error) {
      projectError.value = `项目列表加载失败：${readErrorMessage(error)}`
    }
  }
  await loadAll()
})

// 顶部项目切换后，若当前处于「当前项目」范围则自动刷新。
watch(
  () => projectStore.currentProjectId,
  () => {
    if (scope.value === 'project') loadAll()
  },
)
</script>

<style scoped>
.monitoring-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 18px;
}

.filter-bar__left,
.filter-bar__right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-bar__label {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.filter-bar__label--gap {
  margin-left: 10px;
}

.monitor-stats {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 14px;
}

.chart-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(320px, 1fr);
  gap: 16px;
}

.chart {
  width: 100%;
  height: 280px;
}

.card-title__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.external-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.external-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.external-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--aits-text-secondary);
}

.guide-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.guide-card {
  padding: 12px 14px;
  background: #f8fafc;
  border: 1px solid var(--aits-border);
  border-radius: 10px;
}

.guide-card h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: #0f172a;
}

.guide-card p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--aits-text-secondary);
}

.guide-card p + p {
  margin-top: 6px;
}

.guide-code {
  margin: 0 0 8px;
  padding: 8px 10px;
  overflow-x: auto;
  color: #e2e8f0;
  background: #0f172a;
  border-radius: 6px;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.guide-card code {
  padding: 1px 5px;
  color: #1e293b;
  background: #e2e8f0;
  border-radius: 4px;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12px;
}

.prometheus-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

@media (max-width: 1440px) {
  .monitor-stats {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 1100px) {
  .chart-grid {
    grid-template-columns: 1fr;
  }

  .guide-grid {
    grid-template-columns: 1fr;
  }
}
</style>
