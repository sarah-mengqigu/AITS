<template>
  <div class="tab-panel">
    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-select
            v-model="filters.status"
            class="filter-select"
            placeholder="执行状态"
            clearable
            @change="handleSearch"
          >
            <el-option
              v-for="(label, value) in EXECUTION_STATUS_TEXT"
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
          <el-button :icon="Refresh" @click="loadExecutions">刷新</el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </div>
        <div class="toolbar__right">
          <span class="text-small text-muted">共 {{ pagination.total }} 次执行</span>
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
        :data="executions"
        :loading="loading"
        :total="pagination.total"
        row-key="id"
        empty-text="暂无执行记录，可在测试套件或单用例中触发执行"
        @change="loadExecutions"
      >
        <el-table-column label="执行名称" min-width="210" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" underline="never" @click="openDetail(row)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="套件" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.suite_name || '单用例执行' }}</template>
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
        <el-table-column label="浏览器" width="110">
          <template #default="{ row }">{{ BROWSER_TEXT[row.browser] || row.browser || '—' }}</template>
        </el-table-column>
        <el-table-column label="耗时" width="110" align="right">
          <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
        </el-table-column>
        <el-table-column label="触发方式" width="110">
          <template #default="{ row }">{{ TRIGGER_TYPE_TEXT[row.trigger_type] || row.trigger_type || '—' }}</template>
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

    <el-drawer v-model="detailVisible" :title="detail?.name || '执行详情'" size="880px">
      <template v-if="detail">
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="状态">
            <StatusTag :status="detail.status" />
          </el-descriptions-item>
          <el-descriptions-item label="通过率">{{ formatPercent(computePassRate(detail)) }}</el-descriptions-item>
          <el-descriptions-item label="浏览器">{{ BROWSER_TEXT[detail.browser] || detail.browser || '—' }}</el-descriptions-item>
          <el-descriptions-item label="用例总数">{{ detail.total ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="通过">{{ detail.passed ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="失败">{{ detail.failed ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="跳过">{{ detail.skipped ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ formatDuration(detail.duration_ms) }}</el-descriptions-item>
          <el-descriptions-item label="触发人">{{ detail.triggered_by_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatDateTime(detail.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ formatDateTime(detail.finished_at) }}</el-descriptions-item>
          <el-descriptions-item label="套件">{{ detail.suite_name || '单用例执行' }}</el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="detail.error_message"
          class="mt-16"
          type="error"
          show-icon
          :closable="false"
          title="执行错误"
          :description="detail.error_message"
        />

        <h4 class="section-title">用例明细（{{ details.length }}）</h4>
        <DataTable
          :data="details"
          :loading="detailLoading"
          :show-pagination="false"
          empty-text="暂无用例明细"
        >
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="expand-body">
                <div class="expand-block">
                  <div class="expand-block__title">步骤结果</div>
                  <JsonViewer :value="row.steps" :max-height="220" :copyable="false" />
                </div>
                <div class="expand-block">
                  <div class="expand-block__title">步骤日志</div>
                  <JsonViewer :value="row.step_log" :max-height="220" :copyable="false" />
                </div>
                <div class="expand-block">
                  <div class="expand-block__title">截图</div>
                  <div v-if="!(row.screenshots || []).length" class="text-small text-muted">
                    暂无截图（simulated 模式不产出截图）
                  </div>
                  <div v-else class="shot-list">
                    <div v-for="(shot, index) in row.screenshots" :key="index" class="shot-item">
                      <el-image
                        v-if="isImageUrl(shot)"
                        :src="shot"
                        :preview-src-list="[shot]"
                        fit="cover"
                        class="shot-image"
                      />
                      <span v-else class="mono text-small">{{ shot }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="case_name" label="用例名称" min-width="200" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <StatusTag :status="row.status" />
            </template>
          </el-table-column>
          <el-table-column label="耗时" width="110" align="right">
            <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
          </el-table-column>
          <el-table-column label="错误信息" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">{{ row.error_message || '—' }}</template>
          </el-table-column>
        </DataTable>

        <h4 class="section-title">产物</h4>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="Allure 结果路径">
            <span class="mono">{{ detail.allure_results_path || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="HTML 报告路径">
            <span class="mono">{{ detail.report_path || '—' }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </template>
      <el-empty v-else description="暂无执行详情" />
    </el-drawer>

    <el-dialog v-model="reportVisible" title="执行报告" width="920px" top="6vh">
      <div class="report-toolbar">
        <StatusTag v-if="report?.status" :status="report.status" />
        <span class="text-small text-muted">执行 ID：{{ report?.execution_id ?? '—' }}</span>
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
          <el-descriptions-item label="HTML 报告">
            <span class="mono">{{ report.report_path || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="报告可用">
            <el-tag size="small" :type="report.report_available ? 'success' : 'info'" effect="light">
              {{ report.report_available ? '已生成' : '未生成' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="Allure 结果">
            <span class="mono">{{ report.allure_results_path || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="报告地址">
            <el-link v-if="report.report_url" type="primary" :href="report.report_url" target="_blank">
              {{ report.report_url }}
            </el-link>
            <span v-else class="text-muted">—</span>
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="report.report_url" class="report-frame">
          <iframe :src="report.report_url" title="执行报告" />
        </div>
        <el-alert
          v-else-if="report.report_available"
          class="mt-16"
          type="info"
          show-icon
          :closable="false"
          title="报告为服务端 HTML 文件"
          description="后端仅通过「下载报告」暴露文件流；此处展示报告 JSON 与产物路径。"
        />

        <h4 class="section-title">报告 JSON</h4>
        <JsonViewer :value="report.report || report.summary" :max-height="360" />

        <h4 class="section-title">用例明细</h4>
        <DataTable :data="report.details || []" :show-pagination="false" empty-text="暂无用例明细">
          <el-table-column prop="case_name" label="用例" min-width="200" show-overflow-tooltip />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <StatusTag :status="row.status" />
            </template>
          </el-table-column>
          <el-table-column label="耗时" width="100" align="right">
            <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
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

import { webTestingApi } from '@/api/webTesting'
import { downloadResponse } from '@/utils/download'
import { formatDateTime, formatDuration, formatPercent } from '@/utils/format'
import {
  BROWSER_TEXT,
  EXECUTION_STATUS_TEXT,
  TRIGGER_TYPE_TEXT,
  computePassRate,
  isTerminalStatus,
  normalizeListPayload,
} from './utils'

const props = defineProps({
  projectId: { type: Number, default: null },
})

const filters = reactive({ status: '', trigger_type: '' })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

const executions = ref([])
const loading = ref(false)
const errorMessage = ref('')
const cancellingId = ref(null)

const detailVisible = ref(false)
const detail = ref(null)
const details = ref([])
const detailLoading = ref(false)

const reportVisible = ref(false)
const report = ref(null)
const reportLoading = ref(false)
const reportError = ref('')
const downloading = ref(false)
const reportExecutionId = ref(null)

async function loadExecutions() {
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
    const data = await webTestingApi.listExecutions(params)
    const { results, count } = normalizeListPayload(data)
    executions.value = results
    pagination.total = count
  } catch (error) {
    executions.value = []
    pagination.total = 0
    errorMessage.value = error?.message || '执行记录加载失败'
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadExecutions()
}

function handleReset() {
  filters.status = ''
  filters.trigger_type = ''
  pagination.page = 1
  loadExecutions()
}

async function openDetail(row) {
  detail.value = row
  details.value = []
  detailVisible.value = true
  detailLoading.value = true
  try {
    const data = await webTestingApi.retrieveExecution(row.id)
    detail.value = { ...row, ...data }
    details.value = Array.isArray(data.details) ? data.details : []
  } catch (error) {
    ElMessage.error(error?.message || '执行详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

async function handleCancel(row) {
  try {
    await ElMessageBox.confirm(
      `确定取消执行「${row.name}」吗？已开始的用例结果不会被回滚。`,
      '取消执行',
      { type: 'warning', confirmButtonText: '取消执行', cancelButtonText: '返回' },
    )
  } catch {
    return
  }
  cancellingId.value = row.id
  try {
    await webTestingApi.cancelExecution(row.id)
    ElMessage.success('已取消执行')
    await loadExecutions()
    if (detail.value?.id === row.id) await openDetail(row)
  } catch (error) {
    ElMessage.error(error?.message || '取消执行失败')
  } finally {
    cancellingId.value = null
  }
}

async function openReport(row) {
  reportVisible.value = true
  reportExecutionId.value = row.id
  report.value = null
  reportError.value = ''
  await loadReport()
}

async function loadReport() {
  if (!reportExecutionId.value) return
  reportLoading.value = true
  reportError.value = ''
  try {
    const data = await webTestingApi.executionReport(reportExecutionId.value)
    report.value = data
  } catch (error) {
    reportError.value = error?.message || '报告加载失败'
  } finally {
    reportLoading.value = false
  }
}

async function downloadReport() {
  if (!reportExecutionId.value) return
  downloading.value = true
  try {
    const response = await webTestingApi.downloadExecutionReport(reportExecutionId.value)
    downloadResponse(response, `web-testing-report-${reportExecutionId.value}.html`)
    ElMessage.success('报告已开始下载')
  } catch (error) {
    ElMessage.error(error?.message || '报告下载失败')
  } finally {
    downloading.value = false
  }
}

function isImageUrl(value) {
  if (typeof value !== 'string') return false
  return /^(https?:|\/media\/|\/assets\/|data:image\/)/.test(value)
}

watch(
  () => props.projectId,
  () => {
    filters.status = ''
    filters.trigger_type = ''
    pagination.page = 1
    loadExecutions()
  },
)

onMounted(loadExecutions)
</script>

<style scoped>
.section-title {
  margin: 18px 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.expand-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  padding: 8px 12px;
}

.expand-block__title {
  margin-bottom: 6px;
  color: var(--aits-text-secondary);
  font-size: 12px;
}

.shot-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.shot-item {
  max-width: 260px;
}

.shot-image {
  width: 180px;
  height: 110px;
  border-radius: 6px;
  border: 1px solid var(--aits-border);
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

.report-frame {
  margin-top: 12px;
  border: 1px solid var(--aits-border);
  border-radius: 8px;
  overflow: hidden;
}

.report-frame iframe {
  width: 100%;
  height: 460px;
  border: 0;
}

@media (max-width: 1440px) {
  .expand-body {
    grid-template-columns: 1fr;
  }
}
</style>
