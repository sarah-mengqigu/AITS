<template>
  <div class="executions-pane">
    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
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
        :data="executions"
        :loading="loading"
        :total="pagination.total"
        row-key="id"
        empty-text="暂无执行记录"
        @change="loadExecutions"
      >
        <el-table-column label="执行名称" min-width="230" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" :underline="false" @click="openDetailById(row.id)">
              {{ row.name || '未命名执行' }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column label="套件" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.suite_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <StatusTag :status="row.status" :text="getExecutionStatusLabel(row.status)" />
          </template>
        </el-table-column>
        <el-table-column label="通过率" width="160">
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
        <el-table-column label="通过 / 失败 / 总数" width="140">
          <template #default="{ row }">
            <span class="text-small">
              <span class="count-passed">{{ row.passed ?? 0 }}</span>
              /
              <span class="count-failed">{{ row.failed ?? 0 }}</span>
              /
              {{ row.total ?? 0 }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="100">
          <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
        </el-table-column>
        <el-table-column label="触发方式" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="getTriggerTypeMeta(row.trigger_type).tagType">
              {{ getTriggerTypeMeta(row.trigger_type).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="触发人" width="100" show-overflow-tooltip>
          <template #default="{ row }">{{ row.triggered_by_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="开始时间" width="160">
          <template #default="{ row }">{{ formatDateTime(row.started_at || row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
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
            description="运行测试套件或单个用例后，执行结果、用例明细与报告会在这里展示。"
          >
            <el-button type="primary" @click="emit('switch-tab', 'suites')">去运行套件</el-button>
          </EmptyState>
        </template>
      </DataTable>
    </div>

    <!-- 执行详情 -->
    <el-drawer v-model="detailVisible" :title="drawerTitle" size="68%" @closed="handleDrawerClosed">
      <div v-loading="detailLoading" class="detail-body">
        <el-alert
          v-if="detailError"
          :title="detailError"
          type="error"
          show-icon
          :closable="false"
        />

        <template v-if="detail">
          <div class="detail-toolbar">
            <div class="detail-toolbar__left">
              <el-tag :type="getExecutionStatusMeta(detail.status).tagType" effect="light">
                {{ getExecutionStatusMeta(detail.status).label }}
              </el-tag>
              <span class="text-small text-muted">
                触发方式：{{ getTriggerTypeMeta(detail.trigger_type).label }}
                <template v-if="detail.triggered_by_name"> · {{ detail.triggered_by_name }}</template>
              </span>
            </div>
            <div class="detail-toolbar__right">
              <el-button size="small" :icon="Refresh" :loading="detailLoading" @click="reloadDetail">
                刷新
              </el-button>
              <el-button
                v-if="!isExecutionTerminal(detail.status)"
                size="small"
                type="danger"
                plain
                :loading="cancelling"
                @click="handleCancel"
              >
                取消执行
              </el-button>
            </div>
          </div>

          <section class="detail-stats">
            <StatCard label="用例总数" :value="detail.total ?? 0" />
            <StatCard label="通过" :value="detail.passed ?? 0" color="#16a34a" />
            <StatCard label="失败" :value="detail.failed ?? 0" color="#dc2626" />
            <StatCard label="通过率" :value="formatPercent(detail.pass_rate)" />
            <StatCard label="耗时" :value="formatDuration(detail.duration_ms)" />
          </section>

          <el-descriptions :column="2" size="small" border class="mt-16">
            <el-descriptions-item label="执行名称">{{ detail.name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="套件">{{ detail.suite_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="执行环境">{{ detail.environment_name || '项目默认环境' }}</el-descriptions-item>
            <el-descriptions-item label="开始时间">{{ formatDateTime(detail.started_at) }}</el-descriptions-item>
            <el-descriptions-item label="结束时间">{{ formatDateTime(detail.finished_at) }}</el-descriptions-item>
            <el-descriptions-item label="报告路径">
              <span class="mono">{{ detail.report_path || '—' }}</span>
              <el-link
                v-if="reportPathUrl"
                class="ml-8"
                type="primary"
                :underline="false"
                :href="reportPathUrl"
                target="_blank"
              >
                打开
              </el-link>
            </el-descriptions-item>
            <el-descriptions-item v-if="detail.error_message" label="错误信息" :span="2">
              <span class="error-text">{{ detail.error_message }}</span>
            </el-descriptions-item>
          </el-descriptions>

          <el-tabs v-model="detailTab" class="detail-tabs">
            <el-tab-pane label="执行明细" name="details">
              <template v-if="detail.suite_details?.length">
                <div class="card-title"><span>套件明细</span></div>
                <el-table :data="detail.suite_details" size="small" border>
                  <el-table-column prop="suite_name" label="套件名称" min-width="180" show-overflow-tooltip />
                  <el-table-column label="状态" width="90">
                    <template #default="{ row }">
                      <StatusTag :status="row.status" :text="getExecutionStatusLabel(row.status)" size="small" />
                    </template>
                  </el-table-column>
                  <el-table-column label="通过 / 失败 / 总数" width="140">
                    <template #default="{ row }">{{ row.passed }} / {{ row.failed }} / {{ row.total }}</template>
                  </el-table-column>
                  <el-table-column label="耗时" width="100">
                    <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
                  </el-table-column>
                </el-table>
              </template>

              <div class="card-title mt-16">
                <span>用例明细</span>
                <span class="text-small text-muted">共 {{ caseDetails.length }} 条</span>
              </div>
              <el-table :data="caseDetails" size="small" border empty-text="暂无用例明细">
                <el-table-column type="expand">
                  <template #default="{ row }">
                    <div class="case-expand">
                      <div class="case-expand__block">
                        <JsonViewer :value="row.request" title="请求" :max-height="200" />
                      </div>
                      <div class="case-expand__block">
                        <JsonViewer :value="row.response" title="响应" :max-height="200" />
                      </div>
                      <div class="case-expand__block">
                        <JsonViewer :value="row.assertions" title="断言结果" :max-height="200" />
                      </div>
                      <div v-if="row.step_log?.length" class="case-expand__block">
                        <JsonViewer :value="row.step_log" title="步骤日志" :max-height="200" />
                      </div>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column prop="case_name" label="用例名称" min-width="220" show-overflow-tooltip />
                <el-table-column label="状态" width="90">
                  <template #default="{ row }">
                    <StatusTag :status="row.status" :text="getExecutionStatusLabel(row.status)" size="small" />
                  </template>
                </el-table-column>
                <el-table-column label="耗时" width="100">
                  <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
                </el-table-column>
                <el-table-column label="错误信息" min-width="260" show-overflow-tooltip>
                  <template #default="{ row }">
                    <span :class="{ 'error-text': row.error_message }">{{ row.error_message || '—' }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="执行报告" name="report">
              <div class="report-toolbar">
                <span class="text-small text-muted">
                  报告来源：{{ detail.report_path ? '报告文件' : '内联兜底报告' }}
                  <template v-if="reportView.generatedAt"> · 生成于 {{ reportView.generatedAt }}</template>
                </span>
                <div>
                  <el-button size="small" :icon="Refresh" :loading="reportLoading" @click="loadReport(detail.id)">
                    刷新报告
                  </el-button>
                  <el-button
                    size="small"
                    type="primary"
                    plain
                    :icon="Download"
                    :disabled="!report"
                    @click="downloadReport"
                  >
                    下载报告 JSON
                  </el-button>
                </div>
              </div>

              <el-alert
                v-if="reportError"
                :title="reportError"
                type="error"
                show-icon
                :closable="false"
                class="mb-16"
              />

              <div v-if="report" class="report-body">
                <el-descriptions :column="2" size="small" border>
                  <el-descriptions-item label="报告状态">
                    <el-tag :type="reportView.summary.status.tagType" size="small">
                      {{ reportView.summary.status.label }}
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="执行模式">{{ reportView.summary.mode || '—' }}</el-descriptions-item>
                  <el-descriptions-item label="用例总数">{{ reportView.summary.total }}</el-descriptions-item>
                  <el-descriptions-item label="通过率">{{ reportView.summary.passRateText }}</el-descriptions-item>
                  <el-descriptions-item label="通过 / 失败">{{ reportView.summary.passed }} / {{ reportView.summary.failed }}</el-descriptions-item>
                  <el-descriptions-item label="耗时">{{ reportView.summary.durationText }}</el-descriptions-item>
                </el-descriptions>

                <el-table :data="reportView.cases" size="small" border class="mt-16" empty-text="报告中没有用例明细">
                  <el-table-column prop="name" label="用例名称" min-width="200" show-overflow-tooltip />
                  <el-table-column label="状态" width="90">
                    <template #default="{ row }">
                      <el-tag :type="row.tagType" size="small" effect="light">{{ row.statusLabel }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="durationText" label="耗时" width="100" />
                  <el-table-column prop="errorMessage" label="错误信息" min-width="220" show-overflow-tooltip />
                </el-table>

                <el-collapse class="mt-16">
                  <el-collapse-item title="查看完整报告 JSON" name="json">
                    <JsonViewer :value="report" title="执行报告" :max-height="420" />
                  </el-collapse-item>
                </el-collapse>
              </div>
              <EmptyState
                v-else-if="!reportLoading"
                title="暂无报告"
                description="该执行尚未生成报告，完成执行后点击「刷新报告」重试。"
              />
            </el-tab-pane>
          </el-tabs>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Refresh, RefreshLeft, Search } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import EmptyState from '@/components/EmptyState.vue'
import StatusTag from '@/components/StatusTag.vue'
import StatCard from '@/components/StatCard.vue'
import JsonViewer from '@/components/JsonViewer.vue'

import { apiTestingApi } from '@/api/apiTesting'
import { downloadJson } from '@/utils/download'
import { formatDateTime, formatDuration, formatPercent } from '@/utils/format'
import { useExecutionWatcher } from './useExecutionWatcher'
import {
  EXECUTION_STATUS_OPTIONS,
  TRIGGER_TYPE_OPTIONS,
  buildReportFilename,
  getExecutionStatusLabel,
  getExecutionStatusMeta,
  getTriggerTypeMeta,
  isExecutionTerminal,
  normalizeReport,
} from './utils'

const props = defineProps({
  projectId: { type: [Number, String], default: null },
  refreshKey: { type: Number, default: 0 },
  initialExecutionId: { type: [Number, String], default: null },
})

const emit = defineEmits(['initial-consumed', 'changed', 'switch-tab'])

const executions = ref([])
const loading = ref(false)
const errorMessage = ref('')
const filters = reactive({ search: '', status: '', trigger_type: '' })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

const detailVisible = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const detail = ref(null)
const detailTab = ref('details')
const cancelling = ref(false)

const report = ref(null)
const reportLoading = ref(false)
const reportError = ref('')

let listTimer = null
let currentDetailId = null

const drawerTitle = computed(() =>
  detail.value?.name ? `执行详情 · ${detail.value.name}` : '执行详情',
)

const caseDetails = computed(() => {
  const list = detail.value?.case_details
  return Array.isArray(list) ? list : []
})

const reportView = computed(() => normalizeReport(report.value))

const reportPathUrl = computed(() => {
  const path = String(detail.value?.report_path || '').trim()
  if (!path) return ''
  if (/^https?:\/\//i.test(path)) return path
  if (path.startsWith('/media/') || path.startsWith('/reports/')) return path
  return ''
})

const watcher = useExecutionWatcher({
  onFinish: async (execution) => {
    const id = execution?.id || currentDetailId
    if (id && detailVisible.value) {
      await Promise.all([loadDetail(id, { quiet: true }), loadReport(id, { quiet: true })])
    }
    await loadExecutions({ quiet: true })
    emit('changed')
  },
})

function clampRate(value) {
  const number = Number(value)
  return Number.isFinite(number) ? Math.min(100, Math.max(0, number)) : 0
}

function buildParams() {
  const params = {
    project: props.projectId,
    page: pagination.page,
    page_size: pagination.pageSize,
  }
  if (filters.search.trim()) params.search = filters.search.trim()
  if (filters.status) params.status = filters.status
  if (filters.trigger_type) params.trigger_type = filters.trigger_type
  return params
}

function scheduleListRefresh() {
  if (listTimer) {
    clearInterval(listTimer)
    listTimer = null
  }
  const hasActive = executions.value.some((item) => !isExecutionTerminal(item.status))
  if (!hasActive) return
  listTimer = setInterval(() => loadExecutions({ quiet: true }), 5000)
}

async function loadExecutions({ quiet = false } = {}) {
  if (!props.projectId) {
    executions.value = []
    pagination.total = 0
    return
  }
  if (!quiet) loading.value = true
  if (!quiet) errorMessage.value = ''
  try {
    const data = await apiTestingApi.listExecutions(buildParams())
    executions.value = Array.isArray(data?.results) ? data.results : []
    pagination.total = Number(data?.count ?? executions.value.length)
    scheduleListRefresh()
  } catch (error) {
    if (!quiet) {
      executions.value = []
      pagination.total = 0
      errorMessage.value = error?.message || '执行记录加载失败'
    }
  } finally {
    if (!quiet) loading.value = false
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

async function loadDetail(id, { quiet = false } = {}) {
  if (!id) return null
  if (!quiet) detailLoading.value = true
  detailError.value = ''
  try {
    const data = await apiTestingApi.retrieveExecution(id)
    detail.value = data
    return data
  } catch (error) {
    if (!quiet) detailError.value = error?.message || '执行详情加载失败'
    return null
  } finally {
    if (!quiet) detailLoading.value = false
  }
}

async function loadReport(id, { quiet = false } = {}) {
  if (!id) return null
  if (!quiet) reportLoading.value = true
  reportError.value = ''
  try {
    const data = await apiTestingApi.executionReport(id)
    report.value = data
    return data
  } catch (error) {
    reportError.value = error?.message || '执行报告加载失败'
    return null
  } finally {
    if (!quiet) reportLoading.value = false
  }
}

async function openDetailById(id) {
  if (!id) return
  currentDetailId = id
  detailVisible.value = true
  detailTab.value = 'details'
  detail.value = null
  report.value = null
  reportError.value = ''
  await Promise.all([loadDetail(id), loadReport(id)])
  if (detail.value && !isExecutionTerminal(detail.value.status)) {
    watcher.start(id)
  } else {
    watcher.stop()
  }
}

async function reloadDetail() {
  if (!currentDetailId) return
  await Promise.all([loadDetail(currentDetailId), loadReport(currentDetailId)])
  if (detail.value && !isExecutionTerminal(detail.value.status)) {
    watcher.start(currentDetailId)
  }
}

function handleDrawerClosed() {
  watcher.stop()
  currentDetailId = null
  detail.value = null
  report.value = null
  reportError.value = ''
}

async function handleCancel() {
  if (!detail.value?.id) return
  cancelling.value = true
  try {
    await apiTestingApi.cancelExecution(detail.value.id, { reason: '用户在页面取消执行' })
    ElMessage.success('执行已取消')
    await Promise.all([loadDetail(detail.value.id, { quiet: true }), loadReport(detail.value.id, { quiet: true })])
    await loadExecutions({ quiet: true })
    emit('changed')
  } catch (error) {
    ElMessage.error(error?.message || '取消执行失败')
  } finally {
    cancelling.value = false
  }
}

async function handleQuickCancel(row) {
  try {
    await apiTestingApi.cancelExecution(row.id, { reason: '用户在列表页取消执行' })
    ElMessage.success('执行已取消')
    await loadExecutions({ quiet: true })
    if (currentDetailId === row.id) await loadDetail(row.id, { quiet: true })
    emit('changed')
  } catch (error) {
    ElMessage.error(error?.message || '取消执行失败')
  }
}

function downloadReport() {
  if (!report.value) return
  downloadJson(report.value, buildReportFilename(detail.value || { id: currentDetailId }))
}

watch(
  () => props.projectId,
  () => {
    pagination.page = 1
    detailVisible.value = false
    watcher.stop()
    loadExecutions()
  },
)

watch(
  () => props.refreshKey,
  () => loadExecutions(),
)

watch(
  () => props.initialExecutionId,
  (id) => {
    if (!id) return
    openDetailById(id).finally(() => emit('initial-consumed'))
  },
  { immediate: true },
)

watch(detailTab, (tab) => {
  if (tab === 'report' && detail.value?.id && !report.value) loadReport(detail.value.id)
})

onBeforeUnmount(() => {
  if (listTimer) clearInterval(listTimer)
  listTimer = null
  watcher.stop()
})

onMounted(() => loadExecutions())
</script>

<style scoped>
.executions-pane {
  display: flex;
  flex-direction: column;
  gap: 14px;
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

.count-passed {
  color: #16a34a;
  font-weight: 600;
}

.count-failed {
  color: #dc2626;
  font-weight: 600;
}

.detail-body {
  min-height: 200px;
}

.detail-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.detail-toolbar__left,
.detail-toolbar__right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.detail-stats {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.detail-stats :deep(.stat-card) {
  padding: 12px 14px;
}

.detail-stats :deep(.stat-card__value) {
  font-size: 22px;
}

.detail-tabs {
  margin-top: 8px;
}

.case-expand {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 8px 12px;
}

.case-expand__block {
  min-width: 0;
}

.report-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.report-body {
  min-height: 120px;
}

.error-text {
  color: #dc2626;
}

.ml-8 {
  margin-left: 8px;
}

.mt-16 {
  margin-top: 16px;
}

@media (max-width: 1440px) {
  .detail-stats {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .case-expand {
    grid-template-columns: 1fr;
  }
}
</style>
