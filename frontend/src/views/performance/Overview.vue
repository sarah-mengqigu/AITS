<template>
  <div class="overview-pane">
    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="warning"
      show-icon
      :closable="false"
      description="部分数据加载失败，可点击「刷新总览」重试；已加载的数据仍可正常使用。"
    />

    <div class="overview-actions">
      <span class="text-small text-muted">统计范围：当前项目近 7 天的负载配置、场景与执行记录</span>
      <el-button size="small" :icon="Refresh" :loading="loading" @click="loadAll">刷新总览</el-button>
    </div>

    <section class="overview-stats">
      <StatCard
        label="负载配置"
        :value="stats.configs"
        :loading="loading"
        :icon="SetUp"
        icon-color="#2563eb"
        icon-bg="#e9effd"
        hint="并发用户 / 加压速率 / 持续时间"
      />
      <StatCard
        label="测试场景"
        :value="stats.scenarios"
        :loading="loading"
        :icon="Aim"
        icon-color="#0d9488"
        icon-bg="#ccfbf1"
        hint="API 套件 / 用例 / 自定义脚本"
      />
      <StatCard
        label="执行数（近 7 天）"
        :value="stats.executions"
        :loading="loading"
        :icon="VideoPlay"
        icon-color="#7c3aed"
        icon-bg="#ede9fe"
        hint="手动 / 定时 / API 触发"
      />
      <StatCard
        label="平均 TPS"
        :value="formatTps(dashboard.summary.avgTps)"
        suffix="req/s"
        :loading="loading"
        :icon="TrendCharts"
        icon-color="#d97706"
        icon-bg="#fef3c7"
        hint="近 7 天执行平均值"
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
        hint="后端通过阈值为 1%"
      />
    </section>

    <section class="overview-grid">
      <div class="page-card">
        <div class="card-title">
          <span>最近执行</span>
          <div class="card-title__actions">
            <el-button link type="primary" @click="emit('switch-tab', 'executions')">
              查看全部
            </el-button>
            <el-button link :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
          </div>
        </div>
        <DataTable
          :data="dashboard.recentExecutions"
          :loading="loading"
          :show-pagination="false"
          empty-text="暂无执行记录"
          max-height="360"
        >
          <el-table-column label="执行名称" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">{{ row.name || '未命名执行' }}</template>
          </el-table-column>
          <el-table-column label="场景" min-width="140" show-overflow-tooltip>
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
          <el-table-column label="错误率" width="90" align="right">
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
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="emit('open-execution', row.id)">查看</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <EmptyState
              title="暂无执行记录"
              description="在「测试场景」中选择负载配置并运行压测后，这里会展示 TPS、P95 与错误率。"
            >
              <el-button type="primary" @click="emit('switch-tab', 'scenarios')">
                去运行场景
              </el-button>
              <el-button @click="emit('switch-tab', 'configs')">先建负载配置</el-button>
            </EmptyState>
          </template>
        </DataTable>
      </div>

      <div class="page-card">
        <div class="card-title">
          <span>快捷入口</span>
          <span class="text-small text-muted">常用性能测试工作流</span>
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
import { useRouter } from 'vue-router'
import {
  Aim,
  ArrowRight,
  DataLine,
  MagicStick,
  Refresh,
  SetUp,
  Timer,
  TrendCharts,
  VideoPlay,
  Warning,
} from '@element-plus/icons-vue'

import StatCard from '@/components/StatCard.vue'
import DataTable from '@/components/DataTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyState from '@/components/EmptyState.vue'

import { performanceApi } from '@/api/performance'
import { formatDateTime, formatNumber } from '@/utils/format'
import {
  formatErrorRate,
  formatLatency,
  formatTps,
  normalizeDashboard,
  readErrorMessage,
} from './utils'

const props = defineProps({
  projectId: { type: [Number, String], default: null },
  refreshKey: { type: Number, default: 0 },
})

const emit = defineEmits(['switch-tab', 'open-execution'])

const router = useRouter()

const loading = ref(false)
const errorMessage = ref('')
const dashboard = ref(normalizeDashboard({}))
const stats = reactive({ configs: null, scenarios: null, executions: null })

const quickLinks = [
  {
    key: 'configs',
    title: '管理负载配置',
    description: '设置并发用户、加压速率、持续时间与目标 Host',
    icon: SetUp,
    color: '#2563eb',
    bg: '#e9effd',
    action: 'tab',
    tab: 'configs',
  },
  {
    key: 'scenarios',
    title: '创建压测场景',
    description: '基于 API 套件、单个用例或自定义 locustfile',
    icon: Aim,
    color: '#0d9488',
    bg: '#ccfbf1',
    action: 'tab',
    tab: 'scenarios',
  },
  {
    key: 'executions',
    title: '查看执行报告',
    description: 'TPS、P50/P95/P99、错误率与状态码分布',
    icon: VideoPlay,
    color: '#7c3aed',
    bg: '#ede9fe',
    action: 'tab',
    tab: 'executions',
  },
  {
    key: 'diagnoses',
    title: 'AI 性能诊断',
    description: 'Grafana 告警与手动诊断结论、处理状态',
    icon: MagicStick,
    color: '#d97706',
    bg: '#fef3c7',
    action: 'tab',
    tab: 'diagnoses',
  },
  {
    key: 'monitoring',
    title: '打开监控大盘',
    description: 'Prometheus 指标、趋势图与 Grafana 联动',
    icon: DataLine,
    color: '#0284c7',
    bg: '#e0f2fe',
    action: 'route',
    to: '/monitoring',
  },
]

function handleQuickLink(link) {
  if (link.action === 'route' && link.to) {
    router.push(link.to)
    return
  }
  emit('switch-tab', link.tab)
}

function resetStats() {
  stats.configs = null
  stats.scenarios = null
  stats.executions = null
  dashboard.value = normalizeDashboard({})
}

async function loadAll() {
  if (!props.projectId) {
    resetStats()
    return
  }
  loading.value = true
  errorMessage.value = ''
  const project = props.projectId
  const requests = [
    ['configs', () => performanceApi.listConfigs({ project, page_size: 1 })],
    ['scenarios', () => performanceApi.listScenarios({ project, page_size: 1 })],
    ['dashboard', () => performanceApi.dashboard({ days: 7, project })],
  ]
  const results = await Promise.allSettled(requests.map(([, loader]) => loader()))
  const failures = []
  results.forEach((result, index) => {
    const key = requests[index][0]
    if (result.status !== 'fulfilled') {
      failures.push(readErrorMessage(result.reason, '总览数据加载失败'))
      return
    }
    if (key === 'dashboard') {
      dashboard.value = normalizeDashboard(result.value)
      stats.executions = dashboard.value.summary.executions
    } else {
      stats[key] = Number(result.value?.count ?? 0)
    }
  })
  if (failures.length) {
    errorMessage.value = `总览加载失败：${failures[0]}`
  }
  loading.value = false
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

.overview-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.overview-stats {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
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
