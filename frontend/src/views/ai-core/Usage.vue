<template>
  <div class="usage">
    <el-alert
      v-if="pageError"
      type="error"
      show-icon
      :closable="false"
      :title="pageError"
      description="用量接口加载失败，请确认后端服务已启动。"
    />

    <section class="stat-grid">
      <StatCard
        label="请求总数"
        :value="formatNumber(summary.requests)"
        :loading="statsLoading"
        :icon="DataLine"
        icon-color="#2563eb"
        icon-bg="#e9effd"
        :hint="`成功 ${formatNumber(summary.success)} · 失败 ${formatNumber(summary.failed)}`"
      />
      <StatCard
        label="Token 总量"
        :value="formatNumber(summary.totalTokens)"
        :loading="statsLoading"
        :icon="Coin"
        icon-color="#7c3aed"
        icon-bg="#ede9fe"
        :hint="`Prompt ${formatNumber(summary.promptTokens)} · Completion ${formatNumber(summary.completionTokens)}`"
      />
      <StatCard
        label="平均响应耗时"
        :value="formatNumber(summary.avgResponseTimeMs)"
        suffix="ms"
        :loading="statsLoading"
        :icon="Timer"
        icon-color="#0d9488"
        icon-bg="#ccfbf1"
      />
      <StatCard
        label="成功率"
        :value="successRate"
        suffix="%"
        :loading="statsLoading"
        :icon="TrendCharts"
        icon-color="#16a34a"
        icon-bg="#dcfce7"
      />
    </section>

    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-select v-model="filters.scope" class="filter-select" @change="loadAll">
            <el-option label="全部可见" value="all" />
            <el-option label="当前项目" value="project" :disabled="!projectStore.currentProjectId" />
          </el-select>
          <el-select v-model="filters.agent" class="filter-select" clearable filterable placeholder="Agent" @change="loadAll">
            <el-option v-for="agent in agents" :key="agent.name" :label="agent.name" :value="agent.name" />
          </el-select>
          <el-select v-model="filters.success" class="filter-select" clearable placeholder="调用结果" @change="loadAll">
            <el-option label="成功" value="true" />
            <el-option label="失败" value="false" />
          </el-select>
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            unlink-panels
            @change="loadAll"
          />
          <el-select v-model="filters.days" class="filter-select" placeholder="时间范围" clearable @change="loadAll">
            <el-option label="最近 7 天" :value="7" />
            <el-option label="最近 30 天" :value="30" />
            <el-option label="最近 90 天" :value="90" />
          </el-select>
        </div>
        <div class="toolbar__right">
          <el-button :icon="Refresh" :loading="loading || statsLoading" @click="loadAll">刷新</el-button>
        </div>
      </div>

      <div class="chart-grid">
        <div class="chart-card">
          <div class="chart-card__title">按天用量趋势</div>
          <VChart v-if="hasDay" class="chart" :option="dayOption" autoresize />
          <EmptyState v-else title="暂无按天数据" description="调整筛选条件或先运行 AI 任务" />
        </div>
        <div class="chart-card">
          <div class="chart-card__title">按模型分布</div>
          <VChart v-if="hasModel" class="chart" :option="modelOption" autoresize />
          <EmptyState v-else title="暂无模型数据" />
        </div>
      </div>

      <div class="chart-card mt-16">
        <div class="chart-card__title">按 Agent 聚合（请求数）</div>
        <VChart v-if="hasAgent" class="chart chart--short" :option="agentOption" autoresize />
        <EmptyState v-else title="暂无 Agent 数据" />
      </div>
    </div>

    <div class="page-card">
      <div class="card-title">
        <span>调用日志</span>
        <span class="text-small text-muted">共 {{ total }} 条</span>
      </div>
      <DataTable
        :data="rows"
        :loading="loading"
        :total="total"
        :page="page"
        :page-size="pageSize"
        empty-text="暂无用量日志"
        @update:page="handlePageChange"
        @update:page-size="handleSizeChange"
      >
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="Agent" width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.agent_name || 'unknown' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="任务类型" width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.task_type || '—' }}</template>
        </el-table-column>
        <el-table-column label="模型" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.model_name || 'mock' }}</template>
        </el-table-column>
        <el-table-column label="Token（P/C/总）" width="160">
          <template #default="{ row }">
            {{ formatNumber(row.prompt_tokens) }} / {{ formatNumber(row.completion_tokens) }} /
            <strong>{{ formatNumber(row.total_tokens) }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="110">
          <template #default="{ row }">{{ formatDuration(row.response_time_ms) }}</template>
        </el-table-column>
        <el-table-column label="结果" width="100">
          <template #default="{ row }">
            <StatusTag :status="row.success ? 'success' : 'failed'" :text="row.success ? '成功' : '失败'" />
          </template>
        </el-table-column>
        <el-table-column label="错误 / 预览" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="{ 'text-danger': !row.success }">{{ row.error_message || row.response_preview || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <el-drawer v-model="detailVisible" title="调用详情" size="620px">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="时间">{{ formatDateTime(detail.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="Agent">{{ detail.agent_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="任务类型">{{ detail.task_type || '—' }}</el-descriptions-item>
          <el-descriptions-item label="任务 ID">{{ detail.task_id || '—' }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ detail.model_name || 'mock' }}</el-descriptions-item>
          <el-descriptions-item label="提供商">{{ detail.provider || '—' }}</el-descriptions-item>
          <el-descriptions-item label="Token">
            {{ formatNumber(detail.prompt_tokens) }} / {{ formatNumber(detail.completion_tokens) }} /
            {{ formatNumber(detail.total_tokens) }}
          </el-descriptions-item>
          <el-descriptions-item label="耗时">{{ formatDuration(detail.response_time_ms) }}</el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="!detail.success && detail.error_message"
          class="mt-16"
          type="error"
          show-icon
          :closable="false"
          :title="detail.error_message"
        />

        <div class="mt-16">
          <JsonViewer title="请求预览" :value="detail.request_preview || '（空）'" :max-height="220" />
        </div>
        <div class="mt-16">
          <JsonViewer title="响应预览" :value="detail.response_preview || '（空）'" :max-height="260" />
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { Coin, DataLine, Refresh, Timer, TrendCharts } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import StatCard from '@/components/StatCard.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyState from '@/components/EmptyState.vue'
import JsonViewer from '@/components/JsonViewer.vue'
import { useProjectStore } from '@/stores/project'
import { aiCoreApi } from '@/api/aiCore'
import { formatDateTime, formatDuration, formatNumber } from '@/utils/format'

import {
  buildAgentChartOption,
  buildAgentSeries,
  buildDayChartOption,
  buildDaySeries,
  buildModelChartOption,
  buildModelSeries,
  normalizeUsageStats,
} from './utils/usage'

use([
  CanvasRenderer,
  LineChart,
  BarChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
])

const projectStore = useProjectStore()

const filters = reactive({ scope: 'all', agent: '', success: '', days: 30 })
const dateRange = ref(null)

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const pageError = ref('')

const statsLoading = ref(false)
const summary = reactive({
  requests: 0,
  success: 0,
  failed: 0,
  totalTokens: 0,
  promptTokens: 0,
  completionTokens: 0,
  avgResponseTimeMs: 0,
})
const daySeries = ref(buildDaySeries([]))
const agentSeries = ref(buildAgentSeries([]))
const modelSeries = ref(buildModelSeries([]))
const agents = ref([])

const detailVisible = ref(false)
const detail = ref(null)

const hasDay = computed(() => daySeries.value.dates.length > 0)
const hasAgent = computed(() => agentSeries.value.names.length > 0)
const hasModel = computed(() => modelSeries.value.models.length > 0)
const dayOption = computed(() => buildDayChartOption(daySeries.value))
const agentOption = computed(() => buildAgentChartOption(agentSeries.value))
const modelOption = computed(() => buildModelChartOption(modelSeries.value))

const successRate = computed(() => {
  if (!summary.requests) return '0.0'
  return ((summary.success / summary.requests) * 100).toFixed(1)
})

const scopeParams = computed(() =>
  filters.scope === 'project' && projectStore.currentProjectId
    ? { project: projectStore.currentProjectId }
    : {},
)

function baseParams() {
  const params = { ...scopeParams.value }
  if (filters.agent) params.agent = filters.agent
  if (filters.success !== '') params.success = filters.success
  if (Array.isArray(dateRange.value) && dateRange.value.length === 2) {
    params.date_from = dateRange.value[0]
    params.date_to = dateRange.value[1]
  } else if (filters.days) {
    params.days = filters.days
  }
  return params
}

async function loadLogs() {
  loading.value = true
  pageError.value = ''
  try {
    const data = await aiCoreApi.listUsageLogs({
      page: page.value,
      page_size: pageSize.value,
      ...baseParams(),
    })
    rows.value = Array.isArray(data?.results) ? data.results : []
    total.value = Number(data?.count ?? rows.value.length)
  } catch (error) {
    rows.value = []
    total.value = 0
    pageError.value = error?.message || '用量日志加载失败'
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  statsLoading.value = true
  try {
    const data = await aiCoreApi.usageStats(baseParams())
    const normalized = normalizeUsageStats(data)
    Object.assign(summary, normalized.total)
    daySeries.value = buildDaySeries(normalized.byDay)
    agentSeries.value = buildAgentSeries(normalized.byAgent)
    modelSeries.value = buildModelSeries(normalized.byModel)
  } catch (error) {
    daySeries.value = buildDaySeries([])
    agentSeries.value = buildAgentSeries([])
    modelSeries.value = buildModelSeries([])
  } finally {
    statsLoading.value = false
  }
}

async function loadAgents() {
  try {
    const data = await aiCoreApi.listAgents()
    agents.value = Array.isArray(data?.results) ? data.results : Array.isArray(data) ? data : []
  } catch (error) {
    agents.value = []
  }
}

async function loadAll() {
  page.value = 1
  await Promise.all([loadLogs(), loadStats()])
}

function handlePageChange(next) {
  page.value = next
  loadLogs()
}

function handleSizeChange(size) {
  pageSize.value = size
  page.value = 1
  loadLogs()
}

function openDetail(row) {
  detail.value = row
  detailVisible.value = true
}

watch(
  () => filters.scope,
  () => loadAll(),
)

onMounted(async () => {
  if (!projectStore.loaded) {
    try {
      await projectStore.fetchProjects()
    } catch (error) {
      // 忽略：无项目时仍可查看全局用量
    }
  }
  await Promise.all([loadAgents(), loadAll()])
})
</script>

<style scoped>
.usage {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chart-grid {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 16px;
}

.chart-card {
  padding: 12px 14px;
  background: #f8fafc;
  border: 1px solid var(--aits-border);
  border-radius: 10px;
}

.chart-card__title {
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.chart {
  width: 100%;
  height: 260px;
}

.chart--short {
  height: 220px;
}

.text-danger {
  color: #dc2626;
}

.mt-16 {
  margin-top: 16px;
}

@media (max-width: 1200px) {
  .chart-grid {
    grid-template-columns: 1fr;
  }
}
</style>
