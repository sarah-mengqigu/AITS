<template>
  <div class="tab-panel">
    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
    />

    <div class="stat-grid stat-grid--5">
      <StatCard label="应用数" :value="stats.applications" icon="Iphone" :loading="loading" />
      <StatCard
        label="用例数"
        :value="stats.cases"
        icon="Tickets"
        icon-color="#7c3aed"
        icon-bg="#f1eafe"
        :loading="loading"
      />
      <StatCard
        label="套件数"
        :value="stats.suites"
        icon="Collection"
        icon-color="#0891b2"
        icon-bg="#e0f6fb"
        :loading="loading"
      />
      <StatCard
        label="运行次数"
        :value="stats.runs"
        icon="VideoPlay"
        icon-color="#ea580c"
        icon-bg="#fff1e6"
        :loading="loading"
      />
      <StatCard
        label="近期通过率"
        :value="formatRate(stats.passRate)"
        :hint="`基于最近 ${stats.sample} 次运行`"
        icon="TrendCharts"
        icon-color="#16a34a"
        icon-bg="#e8f7ee"
        :loading="loading"
      />
    </div>

    <div class="page-card">
      <div class="card-title">
        <span>最近运行</span>
        <div class="flex-between">
          <el-button link type="primary" :icon="Refresh" @click="loadAll">刷新</el-button>
          <el-button link type="primary" @click="goto('runs')">查看全部</el-button>
        </div>
      </div>

      <DataTable
        :data="recentRuns"
        :loading="loading"
        :show-pagination="false"
        empty-text="暂无运行记录，可先在「测试套件」中运行一次"
      >
        <el-table-column prop="name" label="运行名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="套件" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.suite_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="设备" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.device_name || row.device_udid || '未指定' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <StatusTag :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="通过率" width="100" align="right">
          <template #default="{ row }">{{ formatRate(computePassRate(row)) }}</template>
        </el-table-column>
        <el-table-column label="通过/总数" width="110" align="right">
          <template #default="{ row }">
            <span class="mono">{{ row.passed ?? 0 }}/{{ row.total ?? 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平台" width="100">
          <template #default="{ row }">{{ getPlatformText(row.platform) }}</template>
        </el-table-column>
        <el-table-column label="耗时" width="110" align="right">
          <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
        </el-table-column>
        <el-table-column label="开始时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.started_at || row.created_at) }}</template>
        </el-table-column>
      </DataTable>
    </div>

    <div class="page-card">
      <div class="card-title">快捷入口</div>
      <div class="quick-links">
        <el-button @click="goto('applications')">应用管理</el-button>
        <el-button @click="goto('cases')">用例管理</el-button>
        <el-button @click="goto('suites')">测试套件</el-button>
        <el-button @click="goto('runs')">运行记录</el-button>
        <el-button @click="goto('devices')">设备管理</el-button>
        <el-button @click="goto('element-pages')">元素页面</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { inject, onMounted, reactive, ref, watch } from 'vue'

import DataTable from '@/components/DataTable.vue'
import StatCard from '@/components/StatCard.vue'
import StatusTag from '@/components/StatusTag.vue'

import { appTestingApi } from '@/api/appTesting'
import { formatDateTime, formatDuration } from '@/utils/format'
import {
  computePassRate,
  getPlatformText,
  normalizeListPayload,
  summarizeRuns,
} from './utils'

const props = defineProps({
  projectId: { type: Number, default: null },
})

const switchTab = inject('appTestingSwitchTab', null)

const loading = ref(false)
const errorMessage = ref('')
const recentRuns = ref([])
const stats = reactive({
  applications: 0,
  cases: 0,
  suites: 0,
  runs: 0,
  passRate: 0,
  sample: 0,
})

function formatRate(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return `${number.toFixed(1)}%`
}

function goto(tab) {
  if (typeof switchTab === 'function') switchTab(tab)
}

async function loadAll() {
  if (!props.projectId) return
  loading.value = true
  errorMessage.value = ''
  const project = props.projectId
  const [appsResult, casesResult, suitesResult, runsResult] = await Promise.allSettled([
    appTestingApi.listApplications({ project, page: 1, page_size: 1 }),
    appTestingApi.listCases({ project, page: 1, page_size: 1 }),
    appTestingApi.listSuites({ project, page: 1, page_size: 1 }),
    appTestingApi.listRuns({ project, page: 1, page_size: 50, ordering: '-created_at' }),
  ])

  const errors = []

  if (appsResult.status === 'fulfilled') {
    stats.applications = normalizeListPayload(appsResult.value).count
  } else {
    stats.applications = 0
    errors.push(`应用统计失败：${appsResult.reason?.message || '未知错误'}`)
  }

  if (casesResult.status === 'fulfilled') {
    stats.cases = normalizeListPayload(casesResult.value).count
  } else {
    stats.cases = 0
    errors.push(`用例统计失败：${casesResult.reason?.message || '未知错误'}`)
  }

  if (suitesResult.status === 'fulfilled') {
    stats.suites = normalizeListPayload(suitesResult.value).count
  } else {
    stats.suites = 0
    errors.push(`套件统计失败：${suitesResult.reason?.message || '未知错误'}`)
  }

  if (runsResult.status === 'fulfilled') {
    const { results, count } = normalizeListPayload(runsResult.value)
    stats.runs = count
    const summary = summarizeRuns(results)
    stats.passRate = summary.passRate
    stats.sample = results.length
    recentRuns.value = results.slice(0, 5)
  } else {
    stats.runs = 0
    stats.passRate = 0
    stats.sample = 0
    recentRuns.value = []
    errors.push(`运行统计失败：${runsResult.reason?.message || '未知错误'}`)
  }

  errorMessage.value = errors.join('；')
  loading.value = false
}

watch(() => props.projectId, loadAll)
onMounted(loadAll)
</script>

<style scoped>
.stat-grid--5 {
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.quick-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

@media (max-width: 1440px) {
  .stat-grid--5 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
