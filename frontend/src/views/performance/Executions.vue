<template>
  <div class="executions-pane">
    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
      description="执行记录加载失败，请稍后重试或检查后端服务。"
    />

    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="filters.search"
            class="filter-input"
            placeholder="搜索执行名称 / 错误信息"
            :prefix-icon="Search"
            clearable
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
          <el-select
            v-model="filters.status"
            class="filter-select"
            placeholder="执行状态"
            clearable
            @change="handleSearch"
          >
            <el-option
              v-for="option in EXECUTION_STATUS_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-select
            v-model="filters.trigger_type"
            class="filter-select"
            placeholder="触发方式"
            clearable
            @change="handleSearch"
          >
            <el-option
              v-for="option in TRIGGER_TYPE_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-button :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </div>
        <div class="toolbar__right">
          <span class="text-small text-muted">共 {{ pagination.total }} 条执行记录</span>
          <el-button :icon="Refresh" :loading="loading" @click="loadExecutions">刷新</el-button>
        </div>
      </div>

      <DataTable
        v-model:page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :data="rows"
        :loading="loading"
        :total="pagination.total"
        row-key="id"
        empty-text="暂无执行记录"
        @change="loadExecutions"
      >
        <el-table-column label="执行名称" min-width="230" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" underline="never" @click="openDetailById(row.id)">
              {{ row.name }}
            </el-link>
            <div v-if="row.error_message" class="row-error">{{ row.error_message }}</div>
          </template>
        </el-table-column>
        <el-table-column label="场景" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.scenario_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <StatusTag :status="row.status" :text="getExecutionStatusLabel(row.status)" />
          </template>
        </el-table-column>
        <el-table-column label="TPS" width="100" align="right">
          <template #default="{ row }">{{ formatTps(row.avg_tps) }}</template>
        </el-table-column>
        <el-table-column label="P95" width="100" align="right">
          <template #default="{ row }">{{ formatLatency(row.p95_response_time) }}</template>
        </el-table-column>
        <el-table-column label="错误率" width="92" align="right">
          <template #default="{ row }">{{ formatErrorRate(row.error_rate) }}</template>
        </el-table-column>
        <el-table-column label="请求数" width="100" align="right">
          <template #default="{ row }">{{ formatNumber(row.total_requests) }}</template>
        </el-table-column>
        <el-table-column label="耗时" width="100">
          <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
        </el-table-column>
        <el-table-column label="触发方式" width="96">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="getTriggerTypeMeta(row.trigger_type).tagType">
              {{ getTriggerTypeMeta(row.trigger_type).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" width="160">
          <template #default="{ row }">{{ formatDateTime(row.started_at || row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetailById(row.id)">详情</el-button>
            <el-button
              v-if="!isExecutionTerminal(row.status)"
              link
              type="danger"
              @click="handleQuickCancel(row)"
            >
              取消
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            title="暂无执行记录"
            description="在「测试场景」中选择负载配置并运行压测后，TPS、P50/P95/P99、错误率与报告会在这里展示。"
          >
            <el-button type="primary" @click="emit('switch-tab', 'scenarios')">去运行场景</el-button>
          </EmptyState>
        </template>
      </DataTable>
    </div>

    <!-- 执行详情 -->
    <el-drawer
      v-model="detailVisible"
      :title="drawerTitle"
      size="72%"
      @closed="handleDrawerClosed"
    >
      <div v-loading="detailLoading" class="detail-body">
        <el-alert v-if="detailError" :title="detailError" type="error" show-icon :closable="false" />

        <template v-if="detail">
          <div class="detail-toolbar">
            <div class="detail-toolbar__left">
              <StatusTag
                :status="detail.status"
                :text="getExecutionStatusLabel(detail.status)"
              />
              <span class="text-small text-muted">
                触发方式：{{ getTriggerTypeMeta(detail.trigger_type).label }}
                <template v-if="detail.scenario_name"> · 场景：{{ detail.scenario_name }}</template>
              </span>
            </div>
            <div class="detail-toolbar__right">
              <el-button size="small" :icon="Refresh" :loading="detailLoading" @click="loadDetail">
                刷新
              </el-button>
              <el-button
                size="small"
                :icon="Download"
                :loading="reportDownloading"
                @click="handleDownloadReport"
              >
                下载报告
              </el-button>
              <ConfirmButton
                v-if="!isExecutionTerminal(detail.status)"
                size="small"
                type="danger"
                plain
                text="取消执行"
                title="取消压测执行"
                content="确定取消本次压测执行吗？执行器会尽快停止，已产生的指标仍会保留。"
                confirm-button-text="取消执行"
                cancel-button-text="继续等待"
                :loading="cancelLoading"
                @confirm="handleCancel"
              />
            </div>
          </div>

          <section class="detail-stats">
            <StatCard label="总请求数" :value="formatNumber(detail.total_requests)" />
            <StatCard label="平均 TPS" :value="formatTps(detail.avg_tps)" suffix="req/s" />
            <StatCard label="P50" :value="formatLatency(detail.p50_response_time)" />
            <StatCard label="P95" :value="formatLatency(detail.p95_response_time)" />
            <StatCard label="P99" :value="formatLatency(detail.p99_response_time)" />
            <StatCard
              label="错误率"
              :value="formatErrorRate(detail.error_rate)"
              :color="normalizeErrorRate(detail.error_rate) > 0.01 ? '#dc2626' : '#16a34a'"
            />
          </section>

          <el-descriptions :column="2" size="small" border class="mt-16">
            <el-descriptions-item label="执行名称">{{ detail.name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="场景">{{ detail.scenario_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="负载配置">{{ detail.config_name || '平台默认负载' }}</el-descriptions-item>
            <el-descriptions-item label="耗时">{{ formatDuration(detail.duration_ms) }}</el-descriptions-item>
            <el-descriptions-item label="开始时间">{{ formatDateTime(detail.started_at) }}</el-descriptions-item>
            <el-descriptions-item label="结束时间">{{ formatDateTime(detail.finished_at) }}</el-descriptions-item>
            <el-descriptions-item label="报告路径（服务器）" :span="2">
              <span class="mono">{{ detail.report_path || '—' }}</span>
            </el-descriptions-item>
          </el-descriptions>

          <el-alert
            v-if="detail.error_message"
            :title="detail.error_message"
            type="warning"
            show-icon
            :closable="false"
            class="mt-16"
            description="该执行在运行过程中出现错误或被取消，以下指标可能不完整。"
          />

          <div class="detail-section">
            <div class="card-title">
              <span>状态码分布</span>
              <span class="text-small text-muted">共 {{ statusCodeRows.length }} 类状态码</span>
            </div>
            <DataTable
              :data="statusCodeRows"
              :show-pagination="false"
              empty-text="暂无状态码分布数据"
              max-height="260"
            >
              <el-table-column prop="code" label="状态码" width="120">
                <template #default="{ row }">
                  <el-tag
                    size="small"
                    effect="plain"
                    :type="statusCodeTagType(row.code)"
                  >
                    {{ row.code }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="count" label="请求数" width="140" align="right">
                <template #default="{ row }">{{ formatNumber(row.count) }}</template>
              </el-table-column>
              <el-table-column label="占比" min-width="200">
                <template #default="{ row }">
                  <div class="percent-cell">
                    <el-progress
                      :percentage="Math.min(100, Math.max(0, row.percent))"
                      :stroke-width="6"
                      :show-text="false"
                    />
                    <span class="text-small">{{ row.percent.toFixed(2) }}%</span>
                  </div>
                </template>
              </el-table-column>
            </DataTable>
          </div>

          <div class="detail-section">
            <div class="card-title">
              <span>执行摘要（summary）</span>
              <span class="text-small text-muted">后端记录的原始指标</span>
            </div>
            <JsonViewer :value="detail.summary || {}" title="summary JSON" :max-height="320" />
          </div>

          <div class="detail-section">
            <div class="card-title">
              <span>执行报告</span>
              <div class="card-title__actions">
                <el-button link :icon="Refresh" :loading="reportLoading" @click="loadReport">
                  刷新报告
                </el-button>
                <el-button link :icon="Download" :loading="reportDownloading" @click="handleDownloadReport">
                  下载 JSON
                </el-button>
              </div>
            </div>
            <el-alert v-if="reportError" :title="reportError" type="warning" show-icon :closable="false" />
            <div v-else v-loading="reportLoading">
              <JsonViewer :value="report || {}" title="报告 JSON（/report/）" :max-height="420" />
            </div>
          </div>
        </template>

        <EmptyState
          v-else-if="!detailLoading && !detailError"
          title="未选择执行记录"
          description="从列表中选择一条执行记录查看指标、状态码分布与报告。"
        />
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Refresh, RefreshLeft, Search } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import EmptyState from '@/components/EmptyState.vue'
import JsonViewer from '@/components/JsonViewer.vue'
import StatCard from '@/components/StatCard.vue'
import StatusTag from '@/components/StatusTag.vue'
import ConfirmButton from '@/components/ConfirmButton.vue'

import { performanceApi } from '@/api/performance'
import { downloadResponse } from '@/utils/download'
import { formatDateTime, formatDuration, formatNumber } from '@/utils/format'
import {
  EXECUTION_STATUS_OPTIONS,
  TRIGGER_TYPE_OPTIONS,
  buildReportFilename,
  formatErrorRate,
  formatLatency,
  formatTps,
  getExecutionStatusLabel,
  getTriggerTypeMeta,
  isExecutionTerminal,
  normalizeErrorRate,
  normalizeStatusCodeDist,
  readErrorMessage,
} from './utils'

const props = defineProps({
  projectId: { type: [Number, String], default: null },
  refreshKey: { type: Number, default: 0 },
  initialExecutionId: { type: [Number, String], default: null },
})

const emit = defineEmits(['changed', 'switch-tab', 'initial-consumed'])

const rows = ref([])
const loading = ref(false)
const errorMessage = ref('')
const filters = reactive({ search: '', status: '', trigger_type: '' })
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

const detailVisible = ref(false)
const detailId = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
const detail = ref(null)
const report = ref(null)
const reportLoading = ref(false)
const reportError = ref('')
const reportDownloading = ref(false)
const cancelLoading = ref(false)

const drawerTitle = computed(() => {
  if (!detailId.value) return '执行详情'
  return `执行详情 #${detailId.value}`
})

const statusCodeRows = computed(() =>
  normalizeStatusCodeDist(detail.value?.status_code_dist, detail.value?.total_requests),
)

function statusCodeTagType(code) {
  const text = String(code || '')
  if (text.startsWith('2')) return 'success'
  if (text.startsWith('3')) return 'info'
  if (text.startsWith('4')) return 'warning'
  if (text.startsWith('5')) return 'danger'
  return 'info'
}

async function loadExecutions() {
  if (!props.projectId) {
    rows.value = []
    pagination.total = 0
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const params = {
      project: props.projectId,
      page: pagination.page,
      page_size: pagination.pageSize,
      ordering: '-created_at',
    }
    if (filters.search.trim()) params.search = filters.search.trim()
    if (filters.status) params.status = filters.status
    if (filters.trigger_type) params.trigger_type = filters.trigger_type
    const data = await performanceApi.listExecutions(params)
    rows.value = Array.isArray(data?.results) ? data.results : []
    pagination.total = Number(data?.count ?? rows.value.length)
  } catch (error) {
    rows.value = []
    pagination.total = 0
    errorMessage.value = readErrorMessage(error, '执行记录加载失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadExecutions()
}

function handleReset() {
  filters.search = ''
  filters.status = ''
  filters.trigger_type = ''
  pagination.page = 1
  loadExecutions()
}

async function loadReport() {
  if (!detailId.value) return
  reportLoading.value = true
  reportError.value = ''
  try {
    report.value = await performanceApi.executionReport(detailId.value)
  } catch (error) {
    report.value = null
    reportError.value = readErrorMessage(error, '执行报告加载失败')
  } finally {
    reportLoading.value = false
  }
}

async function loadDetail() {
  if (!detailId.value) return
  detailLoading.value = true
  detailError.value = ''
  const id = detailId.value
  const [detailResult] = await Promise.allSettled([
    performanceApi.retrieveExecution(id),
    loadReport(),
  ])
  if (detailResult.status === 'fulfilled') {
    detail.value = detailResult.value
  } else {
    detail.value = null
    detailError.value = readErrorMessage(detailResult.reason, '执行详情加载失败')
  }
  detailLoading.value = false
}

function openDetailById(id) {
  if (!id) return
  detailId.value = id
  detail.value = null
  report.value = null
  reportError.value = ''
  detailError.value = ''
  detailVisible.value = true
  loadDetail()
}

function handleDrawerClosed() {
  detail.value = null
  report.value = null
  detailError.value = ''
  reportError.value = ''
  detailLoading.value = false
  reportLoading.value = false
  detailId.value = null
}

async function handleDownloadReport() {
  const id = detail.value?.id || detailId.value
  if (!id) return
  reportDownloading.value = true
  try {
    const response = await performanceApi.downloadExecutionReport(id)
    downloadResponse(response, buildReportFilename({ id }))
    ElMessage.success('报告下载已开始')
  } catch (error) {
    ElMessage.error(readErrorMessage(error, '报告下载失败'))
  } finally {
    reportDownloading.value = false
  }
}

async function handleCancel() {
  if (!detailId.value) return
  cancelLoading.value = true
  try {
    await performanceApi.cancelExecution(detailId.value, { reason: '用户在页面取消执行' })
    ElMessage.success('已提交取消请求')
    await loadDetail()
    await loadExecutions()
    emit('changed')
  } catch (error) {
    ElMessage.error(readErrorMessage(error, '取消执行失败'))
  } finally {
    cancelLoading.value = false
  }
}

async function handleQuickCancel(row) {
  cancelLoading.value = true
  try {
    await performanceApi.cancelExecution(row.id, { reason: '用户在页面取消执行' })
    ElMessage.success(`已取消执行「${row.name}」`)
    await loadExecutions()
    if (detailId.value === row.id) await loadDetail()
    emit('changed')
  } catch (error) {
    ElMessage.error(readErrorMessage(error, '取消执行失败'))
  } finally {
    cancelLoading.value = false
  }
}

watch(
  () => props.initialExecutionId,
  (id) => {
    if (!id) return
    openDetailById(id)
    emit('initial-consumed')
  },
  { immediate: true },
)
watch(() => props.projectId, () => {
  pagination.page = 1
  loadExecutions()
})
watch(() => props.refreshKey, loadExecutions)

onMounted(loadExecutions)
</script>

<style scoped>
.executions-pane {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.row-error {
  margin-top: 2px;
  font-size: 12px;
  color: #dc2626;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.detail-toolbar__left,
.detail-toolbar__right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.detail-stats {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.card-title__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.percent-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.percent-cell :deep(.el-progress) {
  flex: 1;
  min-width: 80px;
}

@media (max-width: 1280px) {
  .detail-stats {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
