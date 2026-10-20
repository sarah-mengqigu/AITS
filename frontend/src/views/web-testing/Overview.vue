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
      <StatCard label="模块数" :value="stats.modules" icon="Grid" :loading="loading" />
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
        label="执行数"
        :value="stats.executions"
        icon="VideoPlay"
        icon-color="#ea580c"
        icon-bg="#fff1e6"
        :loading="loading"
      />
      <StatCard
        label="近期通过率"
        :value="formatRate(stats.passRate)"
        :hint="`基于最近 ${stats.sample} 次执行`"
        icon="TrendCharts"
        icon-color="#16a34a"
        icon-bg="#e8f7ee"
        :loading="loading"
      />
    </div>

    <div class="page-card">
      <div class="card-title">
        <span>最近执行</span>
        <div class="flex-between">
          <el-button link type="primary" :icon="Refresh" @click="loadAll">刷新</el-button>
          <el-button link type="primary" @click="goto('executions')">查看全部</el-button>
        </div>
      </div>

      <DataTable
        :data="recentExecutions"
        :loading="loading"
        :show-pagination="false"
        empty-text="暂无执行记录，可先在「测试套件」中运行一次"
      >
        <el-table-column prop="name" label="执行名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="套件" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.suite_name || '单用例执行' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <StatusTag :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="通过率" width="100" align="right">
          <template #default="{ row }">{{ formatRate(computePassRate(row)) }}</template>
        </el-table-column>
        <el-table-column label="用例" width="110" align="right">
          <template #default="{ row }">
            <span class="mono">{{ row.passed ?? 0 }}/{{ row.total ?? 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="浏览器" width="110">
          <template #default="{ row }">{{ BROWSER_TEXT[row.browser] || row.browser || '—' }}</template>
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
        <el-button @click="goto('modules')">模块管理</el-button>
        <el-button @click="goto('cases')">用例管理</el-button>
        <el-button @click="goto('suites')">测试套件</el-button>
        <el-button @click="goto('pom')">POM 管理</el-button>
        <el-button @click="goto('midscene')">MidScene 脚本</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { inject, onMounted, reactive, ref, watch } from 'vue'

import DataTable from '@/components/DataTable.vue'
import StatCard from '@/components/StatCard.vue'
import StatusTag from '@/components/StatusTag.vue'

import { webTestingApi } from '@/api/webTesting'
import { formatDateTime, formatDuration } from '@/utils/format'
import {
  BROWSER_TEXT,
  computePassRate,
  flattenTree,
  normalizeListPayload,
  summarizeExecutions,
} from './utils'

const props = defineProps({
  projectId: { type: Number, default: null },
})

const switchTab = inject('webTestingSwitchTab', null)

const loading = ref(false)
const errorMessage = ref('')
const recentExecutions = ref([])
const stats = reactive({
  modules: 0,
  cases: 0,
  suites: 0,
  executions: 0,
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
  const [modulesResult, casesResult, suitesResult, executionsResult] = await Promise.allSettled([
    webTestingApi.moduleTree({ project }),
    webTestingApi.listCases({ project, page: 1, page_size: 1 }),
    webTestingApi.listSuites({ project, page: 1, page_size: 1 }),
    webTestingApi.listExecutions({ project, page: 1, page_size: 50, ordering: '-created_at' }),
  ])

  const errors = []

  if (modulesResult.status === 'fulfilled') {
    stats.modules = flattenTree(Array.isArray(modulesResult.value) ? modulesResult.value : []).length
  } else {
    stats.modules = 0
    errors.push(`模块统计失败：${modulesResult.reason?.message || '未知错误'}`)
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

  if (executionsResult.status === 'fulfilled') {
    const payload = executionsResult.value
    const { results, count } = normalizeListPayload(payload)
    stats.executions = count
    const summary = summarizeExecutions(results)
    stats.passRate = summary.passRate
    stats.sample = results.length
    recentExecutions.value = results.slice(0, 5)
  } else {
    stats.executions = 0
    stats.passRate = 0
    stats.sample = 0
    recentExecutions.value = []
    errors.push(`执行统计失败：${executionsResult.reason?.message || '未知错误'}`)
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
