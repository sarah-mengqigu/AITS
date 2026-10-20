<template>
  <div class="overview">
    <el-alert
      v-if="errorMessage"
      class="mb-16"
      type="error"
      show-icon
      :closable="false"
      :title="errorMessage"
      description="统计相关接口暂不可用，请确认后端服务已启动。单个面板失败不影响其它面板展示。"
    />

    <div class="toolbar">
      <div class="toolbar__left">
        <span class="text-small text-muted">数据范围</span>
        <el-radio-group v-model="scope" size="small" :disabled="loading">
          <el-radio-button label="all">全部可见</el-radio-button>
          <el-radio-button label="project" :disabled="!projectStore.currentProjectId">
            当前项目
          </el-radio-button>
        </el-radio-group>
      </div>
      <div class="toolbar__right">
        <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
      </div>
    </div>

    <section class="stat-grid">
      <StatCard
        label="模型配置"
        :value="stats.models"
        :loading="loading"
        :icon="Cpu"
        icon-color="#2563eb"
        icon-bg="#e9effd"
        :hint="`启用 ${stats.activeModels} 个 · 默认 ${stats.defaultModels} 个`"
      />
      <StatCard
        label="RAG 文档数"
        :value="formatNumber(stats.ragDocuments)"
        :loading="loading"
        :icon="Search"
        icon-color="#0d9488"
        icon-bg="#ccfbf1"
        :hint="`分块 ${formatNumber(stats.ragChunks)} 个 · ${stats.ragCollection || '—'}`"
      />
      <StatCard
        label="Token 用量"
        :value="formatNumber(stats.totalTokens)"
        :loading="loading"
        :icon="DataAnalysis"
        icon-color="#7c3aed"
        icon-bg="#ede9fe"
        :hint="`${formatNumber(stats.requests)} 次请求 · 成功 ${formatNumber(stats.successRequests)} 次`"
      />
      <StatCard
        label="Agent 数量"
        :value="stats.agents"
        :loading="loading"
        :icon="MagicStick"
        icon-color="#ea580c"
        icon-bg="#ffedd5"
        hint="可用 AI Agent 总数"
      />
    </section>

    <div class="overview__grid">
      <div class="page-card">
        <div class="card-title">
          <span>最近用量趋势</span>
          <span class="text-small text-muted">按天聚合 · 最多 14 天</span>
        </div>
        <VChart v-if="hasTrend" class="chart" :option="dayOption" autoresize />
        <EmptyState
          v-else
          title="暂无用量的按天数据"
          description="调用 AI Agent 或执行 AI 生成任务后，这里会展示每日请求数与 Token 消耗"
        />
      </div>

      <div class="page-card">
        <div class="card-title">
          <span>Agent 调用分布</span>
          <span class="text-small text-muted">按请求数</span>
        </div>
        <VChart v-if="hasAgents" class="chart" :option="agentChartOption" autoresize />
        <EmptyState v-else title="暂无 Agent 调用数据" description="在 Agent 调试中运行任意 Agent 后展示" />
      </div>
    </div>

    <div class="page-card">
      <div class="card-title">
        <span>可用 Agent</span>
        <span class="text-small text-muted">点击「调试」进入在线运行</span>
      </div>
      <div v-if="agentLoading" v-loading="agentLoading" class="agent-loading" />
      <div v-else-if="!agentList.length" class="agent-empty">
        <EmptyState title="未获取到 Agent 列表" description="请确认后端 /api/ai/agents/ 接口可用" />
      </div>
      <div v-else class="agent-grid">
        <div v-for="agent in agentList" :key="agent.name" class="agent-card">
          <div class="agent-card__head">
            <span class="agent-card__name">{{ agent.name }}</span>
            <el-tag size="small" effect="plain" type="info">Agent</el-tag>
          </div>
          <p class="agent-card__desc">{{ agent.description || '暂无描述' }}</p>
          <div class="agent-card__foot">
            <el-button link type="primary" size="small" @click="openAgent(agent)">调试 →</el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { ElMessage } from 'element-plus'

import StatCard from '@/components/StatCard.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useProjectStore } from '@/stores/project'
import { aiCoreApi } from '@/api/aiCore'
import { formatNumber } from '@/utils/format'

import {
  buildAgentChartOption,
  buildAgentSeries,
  buildDayChartOption,
  buildDaySeries,
} from './utils/usage'

use([CanvasRenderer, LineChart, BarChart, GridComponent, LegendComponent, TooltipComponent])

const router = useRouter()
const projectStore = useProjectStore()

const scope = ref('all')
const loading = ref(false)
const errorMessage = ref('')

const stats = reactive({
  models: 0,
  activeModels: 0,
  defaultModels: 0,
  ragDocuments: 0,
  ragChunks: 0,
  ragCollection: '',
  totalTokens: 0,
  requests: 0,
  successRequests: 0,
  agents: 0,
})

const daySeries = ref(buildDaySeries([]))
const agentSeries = ref(buildAgentSeries([]))
const agentList = ref([])
const agentLoading = ref(false)

const hasTrend = computed(() => daySeries.value.dates.length > 0)
const hasAgents = computed(() => agentSeries.value.names.length > 0)
const dayOption = computed(() => buildDayChartOption(daySeries.value))
const agentChartOption = computed(() => buildAgentChartOption(agentSeries.value))

const scopeParams = computed(() =>
  scope.value === 'project' && projectStore.currentProjectId
    ? { project: projectStore.currentProjectId }
    : {},
)

async function loadModels() {
  const data = await aiCoreApi.listLlmConfigs({ page_size: 200, ...scopeParams.value })
  const rows = Array.isArray(data?.results) ? data.results : []
  stats.models = Number(data?.count ?? rows.length)
  stats.activeModels = rows.filter((row) => row.is_active).length
  stats.defaultModels = rows.filter((row) => row.is_default).length
}

async function loadRag() {
  const data = await aiCoreApi.ragStats()
  stats.ragDocuments = Number(data?.documents ?? 0)
  stats.ragChunks = Number(data?.chunks ?? 0)
  stats.ragCollection = data?.collection || ''
}

async function loadUsage() {
  const data = await aiCoreApi.usageStats({ ...scopeParams.value })
  stats.totalTokens = Number(data?.total?.total_tokens ?? 0)
  stats.requests = Number(data?.total?.requests ?? 0)
  stats.successRequests = Number(data?.total?.success ?? 0)
  daySeries.value = buildDaySeries(data?.by_day || [])
  agentSeries.value = buildAgentSeries(data?.by_agent || [])
}

async function loadAgents() {
  agentLoading.value = true
  try {
    const data = await aiCoreApi.listAgents()
    agentList.value = Array.isArray(data?.results) ? data.results : Array.isArray(data) ? data : []
    stats.agents = Number(data?.count ?? agentList.value.length)
  } finally {
    agentLoading.value = false
  }
}

async function loadAll() {
  loading.value = true
  errorMessage.value = ''
  const tasks = [loadModels(), loadRag(), loadUsage()]
  const results = await Promise.allSettled(tasks)
  const failed = results.filter((item) => item.status === 'rejected')
  if (failed.length) {
    const first = failed[0].reason
    errorMessage.value = first?.message || '部分统计接口加载失败'
    ElMessage.error(errorMessage.value)
  }
  loading.value = false
}

function openAgent(agent) {
  router.push({ name: 'ai-core-playground', query: { agent: agent.name } })
}

watch(scope, () => loadAll())

onMounted(async () => {
  if (!projectStore.loaded) {
    try {
      await projectStore.fetchProjects()
    } catch (error) {
      // 项目列表失败不阻塞全局统计
    }
  }
  await Promise.all([loadAll(), loadAgents()])
})
</script>

<style scoped>
.overview {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.overview__grid {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 16px;
}

.chart {
  width: 100%;
  height: 280px;
}

.agent-loading {
  min-height: 120px;
}

.agent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}

.agent-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  background: #f8fafc;
  border: 1px solid var(--aits-border);
  border-radius: 10px;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}

.agent-card:hover {
  border-color: #bfdbfe;
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.08);
}

.agent-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.agent-card__name {
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
}

.agent-card__desc {
  flex: 1;
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--aits-text-secondary);
}

.agent-card__foot {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 1200px) {
  .overview__grid {
    grid-template-columns: 1fr;
  }
}
</style>
