<template>
  <div class="tab-panel">
    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-select
            v-model="filters.status"
            class="filter-select"
            placeholder="运行状态"
            clearable
            @change="handleSearch"
          >
            <el-option
              v-for="(label, value) in RUN_STATUS_TEXT"
              :key="value"
              :label="label"
              :value="value"
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
              v-for="(label, value) in TRIGGER_TYPE_TEXT"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
          <el-button :icon="Refresh" @click="loadRuns">刷新</el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </div>
        <div class="toolbar__right">
          <span class="text-small text-muted">共 {{ pagination.total }} 次运行</span>
        </div>
      </div>

      <el-alert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        show-icon
        :closable="false"
        class="mb-16"
      />

      <DataTable
        v-model:page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :data="runs"
        :loading="loading"
        :total="pagination.total"
        row-key="id"
        empty-text="暂无运行记录，可在测试套件中触发一次运行"
        @change="loadRuns"
      >
        <el-table-column label="运行名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" underline="never" @click="openDetail(row)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="套件" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.suite_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <StatusTag :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="通过率" width="100" align="right">
          <template #default="{ row }">{{ formatPercent(computePassRate(row)) }}</template>
        </el-table-column>
        <el-table-column label="通过/总数" width="110" align="right">
          <template #default="{ row }">
            <span class="mono">{{ row.passed ?? 0 }}/{{ row.total ?? 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="设备" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.device_name || row.device_udid || '未指定' }}</template>
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
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button link type="primary" @click="openReport(row)">报告</el-button>
            <el-button
              link
              type="warning"
              :disabled="isTerminalStatus(row.status)"
              :loading="cancellingId === row.id"
              @click="handleCancel(row)"
            >
              取消
            </el-button>
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <el-drawer v-model="detailVisible" :title="detail?.name || '运行详情'" size="880px">
      <template v-if="detail">
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="状态">
            <StatusTag :status="detail.status" />
          </el-descriptions-item>
          <el-descriptions-item label="通过率">{{ formatPercent(computePassRate(detail)) }}</el-descriptions-item>
          <el-descriptions-item label="Sonic 套件">{{ detail.sonic_suite_id || '—' }}</el-descriptions-item>
          <el-descriptions-item label="用例总数">{{ detail.total ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="通过">{{ detail.passed ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="失败">{{ detail.failed ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="跳过">{{ detail.skipped ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ formatDuration(detail.duration_ms) }}</el-descriptions-item>
          <el-descriptions-item label="触发方式">{{ TRIGGER_TYPE_TEXT[detail.trigger_type] || '—' }}</el-descriptions-item>
          <el-descriptions-item label="设备">{{ detail.device_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="UDID">
            <span class="mono">{{ detail.device_udid || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="平台">{{ getPlatformText(detail.platform) }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatDateTime(detail.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ formatDateTime(detail.finished_at) }}</el-descriptions-item>
          <el-descriptions-item label="报告地址">
            <el-link v-if="detail.report_url" type="primary" :href="detail.report_url" target="_blank">
              {{ detail.report_url }}
            </el-link>
            <span v-else class="mono">{{ detail.report_path || '—' }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="detail.error_message"
          class="mt-16"
          type="error"
          show-icon
          :closable="false"
          title="运行错误"
          :description="detail.error_message"
        />

        <h4 class="section-title">用例明细（summary.cases）</h4>
        <DataTable
          :data="runCases"
          :loading="detailLoading"
          :show-pagination="false"
          empty-text="暂无用例明细"
        >
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="expand-body">
                <JsonViewer :value="row.raw" :max-height="240" :copyable="false" />
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="用例名称" min-width="200" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <StatusTag :status="row.status" />
            </template>
          </el-table-column>
          <el-table-column label="耗时" width="110" align="right">
            <template #default="{ row }">{{ formatDuration(row.duration) }}</template>
          </el-table-column>
          <el-table-column label="错误信息" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">{{ row.error || '—' }}</template>
          </el-table-column>
        </DataTable>

        <h4 class="section-title">运行 summary</h4>
        <JsonViewer :value="detail.summary" :max-height="320" />
      </template>
      <el-empty v-else description="暂无运行详情" />
    </el-drawer>

    <el-dialog v-model="reportVisible" title="运行报告" width="920px" top="6vh">
      <div class="report-toolbar">
        <StatusTag v-if="report?.status" :status="report.status" />
        <span class="text-small text-muted">运行 ID：{{ report?.run_id ?? '—' }}</span>
        <div class="report-toolbar__actions">
          <el-button :icon="Refresh" size="small" :loading="reportLoading" @click="loadReport">刷新</el-button>
          <el-button
            :icon="Download"
            size="small"
            :loading="downloading"
            :disabled="!report?.report_available"
            @click="downloadReport"
          >
            下载报告
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

      <el-skeleton v-if="reportLoading && !report" :rows="6" animated />

      <template v-else-if="report">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="报告路径">
            <span class="mono">{{ report.report_path || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="报告可用">
            <el-tag size="small" :type="report.report_available ? 'success' : 'info'" effect="light">
              {{ report.report_available ? '已生成' : '未生成' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="设备">
            {{ report.device?.device_name || report.device?.udid || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="报告地址">
            <el-link v-if="report.report_url" type="primary" :href="report.report_url" target="_blank">
              {{ report.report_url }}
            </el-link>
            <span v-else class="text-muted">—</span>
          </el-descriptions-item>
        </el-descriptions>

        <h4 class="section-title">报告 JSON</h4>
        <JsonViewer :value="report.report || report.summary" :max-height="380" />

        <h4 class="section-title">用例明细</h4>
        <DataTable
          :data="normalizeRunCases(report.summary)"
          :show-pagination="false"
          empty-text="报告中没有用例明细"
        >
          <el-table-column prop="name" label="用例" min-width="200" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <StatusTag :status="row.status" />
            </template>
          </el-table-column>
          <el-table-column label="耗时" width="110" align="right">
            <template #default="{ row }">{{ formatDuration(row.duration) }}</template>
          </el-table-column>
          <el-table-column label="错误信息" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">{{ row.error || '—' }}</template>
          </el-table-column>
        </DataTable>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Refresh, RefreshLeft } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import JsonViewer from '@/components/JsonViewer.vue'
import StatusTag from '@/components/StatusTag.vue'

import { appTestingApi } from '@/api/appTesting'
import { downloadResponse } from '@/utils/download'
import { formatDateTime, formatDuration, formatPercent } from '@/utils/format'
import {
  RUN_STATUS_TEXT,
  TRIGGER_TYPE_TEXT,
  computePassRate,
  getPlatformText,
  isTerminalStatus,
  normalizeListPayload,
  normalizeRunCases,
} from './utils'

const props = defineProps({
  projectId: { type: Number, default: null },
})

const filters = reactive({ status: '', trigger_type: '' })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

const runs = ref([])
const loading = ref(false)
const errorMessage = ref('')
const cancellingId = ref(null)

const detailVisible = ref(false)
const detail = ref(null)
const runCases = ref([])
const detailLoading = ref(false)

const reportVisible = ref(false)
const report = ref(null)
const reportLoading = ref(false)
const reportError = ref('')
const downloading = ref(false)
const reportRunId = ref(null)

async function loadRuns() {
  if (!props.projectId) return
  loading.value = true
  errorMessage.value = ''
  try {
    const params = {
      project: props.projectId,
      page: pagination.page,
      page_size: pagination.pageSize,
      ordering: '-created_at',
    }
    if (filters.status) params.status = filters.status
    if (filters.trigger_type) params.trigger_type = filters.trigger_type
    const data = await appTestingApi.listRuns(params)
    const { results, count } = normalizeListPayload(data)
    runs.value = results
    pagination.total = count
  } catch (error) {
    runs.value = []
    pagination.total = 0
    errorMessage.value = error?.message || '运行记录加载失败'
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadRuns()
}

function handleReset() {
  filters.status = ''
  filters.trigger_type = ''
  pagination.page = 1
  loadRuns()
}

async function openDetail(row) {
  detail.value = row
  runCases.value = []
  detailVisible.value = true
  detailLoading.value = true
  try {
    const data = await appTestingApi.retrieveRun(row.id)
    detail.value = { ...row, ...data }
    runCases.value = normalizeRunCases(data.summary)
  } catch (error) {
    ElMessage.error(error?.message || '运行详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

async function handleCancel(row) {
  try {
    await ElMessageBox.confirm(
      `确定取消运行「${row.name}」吗？已执行的用例结果不会被回滚。`,
      '取消运行',
      { type: 'warning', confirmButtonText: '取消运行', cancelButtonText: '返回' },
    )
  } catch {
    return
  }
  cancellingId.value = row.id
  try {
    await appTestingApi.cancelRun(row.id)
    ElMessage.success('已取消运行')
    await loadRuns()
    if (detail.value?.id === row.id) await openDetail(row)
  } catch (error) {
    ElMessage.error(error?.message || '取消运行失败')
  } finally {
    cancellingId.value = null
  }
}

async function openReport(row) {
  reportVisible.value = true
  reportRunId.value = row.id
  report.value = null
  reportError.value = ''
  await loadReport()
}

async function loadReport() {
  if (!reportRunId.value) return
  reportLoading.value = true
  reportError.value = ''
  try {
    const data = await appTestingApi.runReport(reportRunId.value)
    report.value = data
  } catch (error) {
    reportError.value = error?.message || '报告加载失败'
  } finally {
    reportLoading.value = false
  }
}

async function downloadReport() {
  if (!reportRunId.value) return
  downloading.value = true
  try {
    const response = await appTestingApi.downloadRunReport(reportRunId.value)
    downloadResponse(response, `app-testing-report-${reportRunId.value}.json`)
    ElMessage.success('报告已开始下载')
  } catch (error) {
    ElMessage.error(error?.message || '报告下载失败')
  } finally {
    downloading.value = false
  }
}

watch(
  () => props.projectId,
  () => {
    filters.status = ''
    filters.trigger_type = ''
    pagination.page = 1
    loadRuns()
  },
)

onMounted(loadRuns)
</script>

<style scoped>
.section-title {
  margin: 18px 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.expand-body {
  padding: 8px 12px;
}

.report-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.report-toolbar__actions {
  display: flex;
  gap: 6px;
  margin-left: auto;
}
</style>
