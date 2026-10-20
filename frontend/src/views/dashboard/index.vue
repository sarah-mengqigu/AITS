<template>
  <div class="page-container">
    <PageHeader title="仪表盘" :subtitle="todayLabel" description="平台质量概览与近期执行动态">
      <template #actions>
        <el-button :loading="loading" :icon="Refresh" @click="loadAll">刷新</el-button>
      </template>
    </PageHeader>

    <el-alert
      v-if="backendUnavailable"
      title="后端接口暂不可用"
      type="warning"
      show-icon
      :closable="false"
      description="统计与执行数据无法加载，请确认后端服务已在 127.0.0.1:8000 启动。页面会在接口恢复后自动展示数据。"
    />

    <section class="stat-grid">
      <StatCard
        label="项目总数"
        :value="stats.projects"
        :loading="loading"
        :icon="Folder"
        icon-color="#2563eb"
        icon-bg="#e9effd"
      />
      <StatCard
        label="用例总数"
        :value="stats.cases"
        :loading="loading"
        :icon="Tickets"
        icon-color="#0d9488"
        icon-bg="#ccfbf1"
        hint="API / Web / App 用例合计"
      />
      <StatCard
        label="执行总数"
        :value="stats.executions"
        :loading="loading"
        :icon="VideoPlay"
        icon-color="#7c3aed"
        icon-bg="#ede9fe"
        hint="API / Web / App / 性能执行合计"
      />
      <StatCard
        label="整体通过率"
        :value="stats.passRate"
        suffix="%"
        :loading="loading"
        :icon="TrendCharts"
        icon-color="#16a34a"
        icon-bg="#dcfce7"
        hint="基于最近执行记录计算"
      />
    </section>

    <section class="chart-grid">
      <div class="page-card">
        <div class="card-title">
          <span>近 7 天执行趋势</span>
          <span class="text-small text-muted">按执行开始时间统计</span>
        </div>
        <VChart v-if="hasTrendData" class="chart" :option="trendOption" autoresize />
        <EmptyState
          v-else
          title="暂无执行趋势"
          description="执行测试后，这里会展示最近 7 天的执行数量变化"
        />
      </div>

      <div class="page-card">
        <div class="card-title">
          <span>执行状态分布</span>
          <span class="text-small text-muted">最近 {{ recentExecutions.length }} 条</span>
        </div>
        <VChart v-if="hasStatusData" class="chart" :option="pieOption" autoresize />
        <EmptyState
          v-else
          title="暂无状态数据"
          description="创建并执行测试套件后展示通过 / 失败分布"
        />
      </div>
    </section>

    <section class="content-grid">
      <div class="page-card">
        <div class="card-title">
          <span>近期执行</span>
          <el-button link type="primary" @click="router.push('/api-testing/executions')">
            查看全部
          </el-button>
        </div>
        <DataTable
          :data="recentExecutions"
          :loading="recentLoading"
          :show-pagination="false"
          empty-text="暂无执行记录"
          max-height="360"
        >
          <el-table-column prop="module" label="模块" width="90">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ row.module }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="执行名称" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ row.name || '未命名执行' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="96">
            <template #default="{ row }">
              <StatusTag :status="row.status" />
            </template>
          </el-table-column>
          <el-table-column label="通过率" width="90">
            <template #default="{ row }">{{ formatPercent(row.pass_rate) }}</template>
          </el-table-column>
          <el-table-column label="耗时" width="96">
            <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
          </el-table-column>
          <el-table-column label="开始时间" width="160">
            <template #default="{ row }">{{ formatDateTime(row.started_at) }}</template>
          </el-table-column>
        </DataTable>
      </div>

      <div class="page-card">
        <div class="card-title">
          <span>快捷入口</span>
          <span class="text-small text-muted">常用测试工作流</span>
        </div>
        <div class="quick-links">
          <button
            v-for="link in quickLinks"
            :key="link.path"
            type="button"
            class="quick-link"
            @click="router.push(link.path)"
          >
            <span class="quick-link__icon" :style="{ backgroundColor: link.bg, color: link.color }">
              <el-icon :size="20"><component :is="link.icon" /></el-icon>
            </span>
            <span class="quick-link__text">
              <strong>{{ link.title }}</strong>
              <span>{{ link.description }}</span>
            </span>
            <el-icon class="quick-link__arrow"><ArrowRight /></el-icon>
          </button>
        </div>

        <div class="backend-hint">
          <el-icon><InfoFilled /></el-icon>
          <span>
            当前项目：
            <strong>{{ projectStore.currentProjectName || '未选择项目' }}</strong>
            <template v-if="lastUpdated"> · 更新于 {{ lastUpdated }}</template>
          </span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import dayjs from 'dayjs'
import {
  ArrowRight,
  Connection,
  Folder,
  InfoFilled,
  Iphone,
  MagicStick,
  Monitor,
  Refresh,
  Tickets,
  Timer,
  TrendCharts,
  VideoPlay,
} from '@element-plus/icons-vue'

import PageHeader from '@/components/PageHeader.vue'
import StatCard from '@/components/StatCard.vue'
import DataTable from '@/components/DataTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyState from '@/components/EmptyState.vue'

import { projectsApi } from '@/api/projects'
import { apiTestingApi } from '@/api/apiTesting'
import { webTestingApi } from '@/api/webTesting'
import { appTestingApi } from '@/api/appTesting'
import { performanceApi } from '@/api/performance'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'
import {
  formatDate,
  formatDateTime,
  formatDuration,
  formatNumber,
  formatPercent,
  getStatusColor,
  getStatusText,
} from '@/utils/format'

use([CanvasRenderer, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent])

const router = useRouter()
const authStore = useAuthStore()
const projectStore = useProjectStore()

const loading = ref(true)
const recentLoading = ref(true)
const backendUnavailable = ref(false)
const lastUpdated = ref('')
const recentExecutions = ref([])

const stats = reactive({
  projects: '—',
  cases: '—',
  executions: '—',
  passRate: null,
})

const todayLabel = computed(() => {
  const name = authStore.displayName
  const date = dayjs().format('YYYY年MM月DD日')
  return `${name}，${date}`
})

const quickLinks = [
  {
    title: 'API 测试',
    description: '接口规范、用例与套件执行',
    path: '/api-testing',
    icon: Connection,
    color: '#2563eb',
    bg: '#e9effd',
  },
  {
    title: 'Web 测试',
    description: 'Playwright / MidScene UI 自动化',
    path: '/web-testing',
    icon: Monitor,
    color: '#0d9488',
    bg: '#ccfbf1',
  },
  {
    title: 'App 测试',
    description: 'Sonic 设备与移动端用例',
    path: '/app-testing',
    icon: Iphone,
    color: '#b45309',
    bg: '#fef3c7',
  },
  {
    title: '性能测试',
    description: '压测场景、报告与 AI 诊断',
    path: '/performance',
    icon: TrendCharts,
    color: '#7c3aed',
    bg: '#ede9fe',
  },
  {
    title: 'AI 中心',
    description: '模型、RAG、MCP 与 Agent 调试',
    path: '/ai-core',
    icon: MagicStick,
    color: '#db2777',
    bg: '#fce7f3',
  },
  {
    title: '定时任务',
    description: 'Cron 调度与执行日志',
    path: '/scheduled-tasks',
    icon: Timer,
    color: '#475569',
    bg: '#f1f5f9',
  },
]

function countOf(result) {
  if (result.status !== 'fulfilled') return null
  const count = result.value?.count
  return typeof count === 'number' ? count : null
}

function normalizeExecution(item, module, index) {
  return {
    id: `${module}-${item.id ?? index}`,
    module,
    name: item.name || item.suite_name || `#${item.id ?? index + 1}`,
    status: item.status || 'pending',
    pass_rate: typeof item.pass_rate === 'number' ? item.pass_rate : null,
    duration_ms: item.duration_ms ?? null,
    started_at: item.started_at || item.created_at || null,
  }
}

function extractResults(result, module) {
  if (result.status !== 'fulfilled') return []
  const results = result.value?.results
  if (!Array.isArray(results)) return []
  return results.map((item, index) => normalizeExecution(item, module, index))
}

async function loadStats() {
  const [projects, apiCases, webCases, appCases, apiRuns, webRuns, appRuns, perfRuns] =
    await Promise.allSettled([
      projectsApi.list({ page_size: 1 }),
      apiTestingApi.listCases({ page_size: 1 }),
      webTestingApi.listCases({ page_size: 1 }),
      appTestingApi.listCases({ page_size: 1 }),
      apiTestingApi.listExecutions({ page_size: 1 }),
      webTestingApi.listExecutions({ page_size: 1 }),
      appTestingApi.listRuns({ page_size: 1 }),
      performanceApi.listExecutions({ page_size: 1 }),
    ])

  const projectCount = countOf(projects)
  stats.projects = projectCount === null ? '—' : formatNumber(projectCount)

  const caseCounts = [countOf(apiCases), countOf(webCases), countOf(appCases)].filter(
    (value) => value !== null,
  )
  stats.cases = caseCounts.length ? formatNumber(caseCounts.reduce((sum, value) => sum + value, 0)) : '—'

  const runCounts = [countOf(apiRuns), countOf(webRuns), countOf(appRuns), countOf(perfRuns)].filter(
    (value) => value !== null,
  )
  stats.executions = runCounts.length
    ? formatNumber(runCounts.reduce((sum, value) => sum + value, 0))
    : '—'

  backendUnavailable.value = [projects, apiCases, apiRuns].every(
    (result) => result.status === 'rejected',
  )
}

async function loadRecentExecutions() {
  const results = await Promise.allSettled([
    apiTestingApi.listExecutions({ page_size: 20, ordering: '-started_at' }),
    webTestingApi.listExecutions({ page_size: 20, ordering: '-started_at' }),
    appTestingApi.listRuns({ page_size: 20, ordering: '-started_at' }),
    performanceApi.listExecutions({ page_size: 20, ordering: '-started_at' }),
  ])

  const rows = [
    ...extractResults(results[0], 'API'),
    ...extractResults(results[1], 'Web'),
    ...extractResults(results[2], 'App'),
    ...extractResults(results[3], '性能'),
  ]

  rows.sort((left, right) => {
    const leftTime = left.started_at ? dayjs(left.started_at).valueOf() : 0
    const rightTime = right.started_at ? dayjs(right.started_at).valueOf() : 0
    return rightTime - leftTime
  })

  recentExecutions.value = rows.slice(0, 8)

  const finished = rows.filter((row) => ['passed', 'failed'].includes(row.status))
  if (finished.length) {
    const passed = finished.filter((row) => row.status === 'passed').length
    stats.passRate = Number(((passed / finished.length) * 100).toFixed(1))
  } else {
    stats.passRate = null
  }
}

async function loadAll() {
  loading.value = true
  recentLoading.value = true
  try {
    await Promise.all([loadStats(), loadRecentExecutions()])
    lastUpdated.value = dayjs().format('HH:mm:ss')
  } finally {
    loading.value = false
    recentLoading.value = false
  }
}

const trendData = computed(() => {
  const days = []
  for (let offset = 6; offset >= 0; offset -= 1) {
    const day = dayjs().subtract(offset, 'day')
    days.push({
      key: day.format('YYYY-MM-DD'),
      label: day.format('MM-DD'),
      count: 0,
    })
  }
  const index = new Map(days.map((day) => [day.key, day]))
  recentExecutions.value.forEach((row) => {
    if (!row.started_at) return
    const key = formatDate(row.started_at)
    const day = index.get(key)
    if (day) day.count += 1
  })
  return days
})

const hasTrendData = computed(() => trendData.value.some((day) => day.count > 0))

const trendOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 44, right: 20, top: 24, bottom: 32 },
  xAxis: {
    type: 'category',
    data: trendData.value.map((day) => day.label),
    axisLine: { lineStyle: { color: '#e2e8f0' } },
    axisLabel: { color: '#64748b' },
  },
  yAxis: {
    type: 'value',
    minInterval: 1,
    splitLine: { lineStyle: { color: '#f1f5f9' } },
    axisLabel: { color: '#64748b' },
  },
  series: [
    {
      name: '执行数',
      type: 'line',
      smooth: true,
      symbolSize: 7,
      data: trendData.value.map((day) => day.count),
      itemStyle: { color: '#2563eb' },
      lineStyle: { width: 3, color: '#2563eb' },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(37, 99, 235, 0.28)' },
            { offset: 1, color: 'rgba(37, 99, 235, 0.02)' },
          ],
        },
      },
    },
  ],
}))

const statusData = computed(() => {
  const counts = new Map()
  recentExecutions.value.forEach((row) => {
    counts.set(row.status, (counts.get(row.status) || 0) + 1)
  })
  return Array.from(counts.entries()).map(([status, count]) => ({
    name: getStatusText(status),
    value: count,
    itemStyle: { color: getStatusColor(status) },
  }))
})

const hasStatusData = computed(() => statusData.value.length > 0)

const pieOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  legend: { bottom: 0, icon: 'circle', textStyle: { color: '#64748b', fontSize: 12 } },
  series: [
    {
      name: '执行状态',
      type: 'pie',
      radius: ['46%', '70%'],
      center: ['50%', '44%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: '#fff', borderWidth: 2 },
      label: { color: '#475569', fontSize: 12 },
      data: statusData.value,
    },
  ],
}))

onMounted(loadAll)
</script>

<style scoped>
.chart {
  width: 100%;
  height: 290px;
}

.quick-links {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.quick-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--aits-border);
  border-radius: 9px;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease,
    transform 0.15s ease;
}

.quick-link:hover {
  border-color: #bfdbfe;
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.08);
  transform: translateY(-1px);
}

.quick-link__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 9px;
  flex-shrink: 0;
}

.quick-link__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.quick-link__text strong {
  font-size: 13px;
  color: #0f172a;
}

.quick-link__text span {
  margin-top: 2px;
  overflow: hidden;
  color: #94a3b8;
  font-size: 11.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quick-link__arrow {
  margin-left: auto;
  color: #cbd5e1;
  font-size: 13px;
}

.backend-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed var(--aits-border);
  color: #94a3b8;
  font-size: 12px;
}

.backend-hint strong {
  color: #475569;
  font-weight: 600;
}

@media (max-width: 1440px) {
  .quick-links {
    grid-template-columns: 1fr;
  }
}
</style>
