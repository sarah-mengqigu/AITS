<template>
  <div class="overview-pane">
    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="warning"
      show-icon
      :closable="false"
      description="部分数据加载失败，可稍后点击「刷新总览」重试；已加载的数据仍可正常使用。"
    />

    <section class="overview-stats">
      <StatCard label="接口规范" :value="stats.specs" :loading="statsLoading" :icon="Document" icon-color="#2563eb" icon-bg="#e9effd" hint="OpenAPI / Swagger / Postman" />
      <StatCard label="接口端点" :value="stats.endpoints" :loading="statsLoading" :icon="Connection" icon-color="#0d9488" icon-bg="#ccfbf1" hint="从规范解析出的操作" />
      <StatCard label="测试用例" :value="stats.cases" :loading="statsLoading" :icon="Tickets" icon-color="#7c3aed" icon-bg="#ede9fe" hint="手工 / AI / Postman" />
      <StatCard label="测试套件" :value="stats.suites" :loading="statsLoading" :icon="Collection" icon-color="#d97706" icon-bg="#fef3c7" hint="可批量执行的用例集合" />
      <StatCard label="执行记录" :value="stats.executions" :loading="statsLoading" :icon="VideoPlay" icon-color="#16a34a" icon-bg="#dcfce7" hint="手动 / 定时 / API 触发" />
    </section>

    <section class="overview-grid">
      <div class="page-card">
        <div class="card-title">
          <span>最近执行</span>
          <div class="card-title__actions">
            <el-button link type="primary" @click="emit('switch-tab', 'executions')">查看全部</el-button>
            <el-button link :icon="Refresh" :loading="recentLoading" @click="loadRecent">刷新</el-button>
          </div>
        </div>
        <DataTable
          :data="recentExecutions"
          :loading="recentLoading"
          :show-pagination="false"
          empty-text="暂无执行记录"
          max-height="360"
        >
          <el-table-column label="执行名称" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ row.name || '未命名执行' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="套件" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.suite_name || '—' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="96">
            <template #default="{ row }">
              <StatusTag :status="row.status" :text="getExecutionStatusLabel(row.status)" />
            </template>
          </el-table-column>
          <el-table-column label="通过率" width="150">
            <template #default="{ row }">
              <div class="rate-cell">
                <el-progress
                  :percentage="clampRate(row.pass_rate)"
                  :stroke-width="6"
                  :show-text="false"
                  :status="row.status === 'failed' || row.status === 'error' ? 'exception' : undefined"
                />
                <span class="text-small">{{ formatPercent(row.pass_rate) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="耗时" width="96">
            <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
          </el-table-column>
          <el-table-column label="开始时间" width="160">
            <template #default="{ row }">{{ formatDateTime(row.started_at || row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="emit('open-execution', row.id)">查看</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <EmptyState
              title="暂无执行记录"
              description="在「测试套件」中运行套件，或在「用例管理」中执行单个用例后，这里会展示执行结果。"
            >
              <el-button type="primary" @click="emit('switch-tab', 'suites')">去运行套件</el-button>
            </EmptyState>
          </template>
        </DataTable>
      </div>

      <div class="page-card">
        <div class="card-title">
          <span>快捷入口</span>
          <span class="text-small text-muted">常用 API 测试工作流</span>
        </div>
        <div class="quick-links">
          <button
            v-for="link in quickLinks"
            :key="link.key"
            type="button"
            class="quick-link"
            @click="handleQuickLink(link)"
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
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import {
  ArrowRight,
  Collection,
  Connection,
  Document,
  Grid,
  MagicStick,
  Refresh,
  Tickets,
  Upload,
  VideoPlay,
} from '@element-plus/icons-vue'

import StatCard from '@/components/StatCard.vue'
import DataTable from '@/components/DataTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyState from '@/components/EmptyState.vue'

import { apiTestingApi } from '@/api/apiTesting'
import { getExecutionStatusLabel } from './utils'
import {
  formatDateTime,
  formatDuration,
  formatPercent,
} from '@/utils/format'

const props = defineProps({
  projectId: { type: [Number, String], default: null },
  refreshKey: { type: Number, default: 0 },
})

const emit = defineEmits(['switch-tab', 'open-postman', 'open-ai', 'open-execution'])

const stats = reactive({
  specs: null,
  endpoints: null,
  cases: null,
  suites: null,
  executions: null,
})
const statsLoading = ref(false)
const recentExecutions = ref([])
const recentLoading = ref(false)
const errorMessage = ref('')

const quickLinks = [
  {
    key: 'specs',
    title: '导入接口规范',
    description: '上传 OpenAPI / Swagger / Postman 文件并解析端点',
    icon: Upload,
    color: '#2563eb',
    bg: '#e9effd',
    action: 'tab',
    tab: 'specs',
  },
  {
    key: 'endpoints',
    title: '浏览模块与端点',
    description: '按模块树查看解析出的接口，批量生成用例',
    icon: Grid,
    color: '#0d9488',
    bg: '#ccfbf1',
    action: 'tab',
    tab: 'endpoints',
  },
  {
    key: 'cases',
    title: '管理测试用例',
    description: '编辑请求配置与断言，生成 HttpRunner 脚本',
    icon: Tickets,
    color: '#7c3aed',
    bg: '#ede9fe',
    action: 'tab',
    tab: 'cases',
  },
  {
    key: 'suites',
    title: '运行测试套件',
    description: '选择用例、环境并批量执行，实时查看进度',
    icon: Collection,
    color: '#d97706',
    bg: '#fef3c7',
    action: 'tab',
    tab: 'suites',
  },
  {
    key: 'postman',
    title: 'Postman 导入',
    description: '解析 Collection v2.1 并转换 pm.test 断言',
    icon: Upload,
    color: '#0284c7',
    bg: '#e0f2fe',
    action: 'postman',
  },
  {
    key: 'ai',
    title: 'AI 场景生成',
    description: '用自然语言描述需求，自动生成多步骤场景用例',
    icon: MagicStick,
    color: '#db2777',
    bg: '#fce7f3',
    action: 'ai',
  },
]

function clampRate(value) {
  const number = Number(value)
  return Number.isFinite(number) ? Math.min(100, Math.max(0, number)) : 0
}

function handleQuickLink(link) {
  if (link.action === 'postman') emit('open-postman')
  else if (link.action === 'ai') emit('open-ai')
  else emit('switch-tab', link.tab)
}

function resetStats() {
  stats.specs = null
  stats.endpoints = null
  stats.cases = null
  stats.suites = null
  stats.executions = null
}

async function loadStats() {
  if (!props.projectId) {
    resetStats()
    return
  }
  statsLoading.value = true
  errorMessage.value = ''
  const project = props.projectId
  const requests = [
    ['specs', () => apiTestingApi.listSpecs({ project, page_size: 1 })],
    ['endpoints', () => apiTestingApi.listEndpoints({ project, page_size: 1 })],
    ['cases', () => apiTestingApi.listCases({ project, page_size: 1 })],
    ['suites', () => apiTestingApi.listSuites({ project, page_size: 1 })],
    ['executions', () => apiTestingApi.listExecutions({ project, page_size: 1 })],
  ]
  const results = await Promise.allSettled(requests.map(([, loader]) => loader()))
  const failures = []
  results.forEach((result, index) => {
    const key = requests[index][0]
    if (result.status === 'fulfilled') {
      stats[key] = Number(result.value?.count ?? 0)
    } else {
      stats[key] = null
      failures.push(result.reason?.message || '未知错误')
    }
  })
  if (failures.length) {
    errorMessage.value = `统计加载失败：${failures[0]}`
  }
  statsLoading.value = false
}

async function loadRecent() {
  if (!props.projectId) {
    recentExecutions.value = []
    return
  }
  recentLoading.value = true
  try {
    const data = await apiTestingApi.listExecutions({
      project: props.projectId,
      page_size: 5,
      ordering: '-created_at',
    })
    recentExecutions.value = Array.isArray(data?.results) ? data.results : []
  } catch (error) {
    recentExecutions.value = []
    errorMessage.value = error?.message || '最近执行加载失败'
  } finally {
    recentLoading.value = false
  }
}

function loadAll() {
  loadStats()
  loadRecent()
}

watch(() => props.projectId, loadAll)
watch(() => props.refreshKey, loadAll)

onMounted(loadAll)
</script>

<style scoped>
.overview-pane {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.overview-stats {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
}

.overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(300px, 1fr);
  gap: 16px;
}

.card-title__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rate-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rate-cell :deep(.el-progress) {
  flex: 1;
  min-width: 60px;
}

.quick-links {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.quick-link {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--aits-border);
  border-radius: 10px;
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
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.1);
  transform: translateY(-1px);
}

.quick-link__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  flex-shrink: 0;
}

.quick-link__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.quick-link__text strong {
  font-size: 13.5px;
  color: #0f172a;
}

.quick-link__text span {
  font-size: 12px;
  color: var(--aits-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quick-link__arrow {
  color: #cbd5e1;
  flex-shrink: 0;
}

@media (max-width: 1440px) {
  .overview-stats {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .overview-grid {
    grid-template-columns: 1fr;
  }
}
</style>
