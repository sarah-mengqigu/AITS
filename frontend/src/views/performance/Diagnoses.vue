<template>
  <div class="diagnoses-pane">
    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
      description="AI 诊断记录加载失败，请稍后重试或检查后端服务。"
    />

    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="filters.search"
            class="filter-input"
            placeholder="搜索告警名称 / 诊断结论"
            :prefix-icon="Search"
            clearable
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
          <el-select
            v-model="filters.source"
            class="filter-select"
            placeholder="来源"
            clearable
            @change="handleSearch"
          >
            <el-option
              v-for="option in DIAGNOSIS_SOURCE_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-select
            v-model="filters.status"
            class="filter-select"
            placeholder="处理状态"
            clearable
            @change="handleSearch"
          >
            <el-option
              v-for="option in DIAGNOSIS_STATUS_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-button :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </div>
        <div class="toolbar__right">
          <span class="text-small text-muted">共 {{ pagination.total }} 条诊断记录</span>
          <el-button :icon="Refresh" :loading="loading" @click="loadDiagnoses">刷新</el-button>
        </div>
      </div>

      <DataTable
        v-model:page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :data="rows"
        :loading="loading"
        :total="pagination.total"
        row-key="id"
        empty-text="暂无 AI 诊断记录"
        @change="loadDiagnoses"
      >
        <el-table-column label="告警 / 诊断" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" underline="never" @click="openDetail(row)">
              {{ row.alert_name || `诊断记录 #${row.id}` }}
            </el-link>
            <div v-if="row.diagnosis_content" class="row-preview">
              {{ diagnosisPreview(row.diagnosis_content) }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="130">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="getDiagnosisSourceMeta(row.source).tagType">
              {{ getDiagnosisSourceMeta(row.source).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="严重级别" width="110">
          <template #default="{ row }">
            <el-tag size="small" effect="light" :type="getSeverityMeta(row.severity).tagType">
              {{ getSeverityMeta(row.severity).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="处理状态" width="100">
          <template #default="{ row }">
            <el-tag
              size="small"
              effect="light"
              :type="getDiagnosisStatusMeta(row.status).tagType"
            >
              {{ getDiagnosisStatusMeta(row.status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="关联执行" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.execution_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="Grafana" width="96" align="center">
          <template #default="{ row }">
            <el-link
              v-if="row.grafana_url"
              type="primary"
              :href="row.grafana_url"
              target="_blank"
              rel="noopener noreferrer"
            >
              打开
            </el-link>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="通知时间" width="160">
          <template #default="{ row }">{{ formatDateTime(row.notified_at || row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button
              v-if="row.status === 'pending'"
              link
              type="success"
              :loading="updatingId === row.id"
              @click="handleQuickResolve(row)"
            >
              解决
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            title="暂无 AI 诊断记录"
            description="Grafana 告警会通过 Webhook 自动生成诊断；也可以在执行记录中发起手动诊断。"
          >
            <el-button type="primary" @click="emit('switch-tab', 'executions')">去执行记录</el-button>
          </EmptyState>
        </template>
      </DataTable>
    </div>

    <!-- 诊断详情 -->
    <el-drawer
      v-model="detailVisible"
      :title="detail ? `AI 诊断 #${detail.id}` : 'AI 诊断'"
      size="62%"
      @closed="handleDrawerClosed"
    >
      <div v-loading="detailLoading" class="detail-body">
        <el-alert v-if="detailError" :title="detailError" type="error" show-icon :closable="false" />

        <template v-if="detail">
          <div class="detail-toolbar">
            <div class="detail-toolbar__left">
              <el-tag effect="light" :type="getDiagnosisStatusMeta(detail.status).tagType">
                {{ getDiagnosisStatusMeta(detail.status).label }}
              </el-tag>
              <el-tag effect="plain" :type="getDiagnosisSourceMeta(detail.source).tagType">
                {{ getDiagnosisSourceMeta(detail.source).label }}
              </el-tag>
              <el-tag effect="light" :type="getSeverityMeta(detail.severity).tagType">
                {{ getSeverityMeta(detail.severity).label }}
              </el-tag>
            </div>
            <div class="detail-toolbar__right">
              <el-button
                v-if="detail.status !== 'resolved'"
                size="small"
                type="success"
                :loading="updatingStatus === 'resolved'"
                @click="handleUpdateStatus('resolved')"
              >
                标记已解决
              </el-button>
              <el-button
                v-if="detail.status !== 'ignored'"
                size="small"
                plain
                :loading="updatingStatus === 'ignored'"
                @click="handleUpdateStatus('ignored')"
              >
                忽略
              </el-button>
              <el-button
                v-if="detail.status !== 'pending'"
                size="small"
                link
                :loading="updatingStatus === 'pending'"
                @click="handleUpdateStatus('pending')"
              >
                恢复待处理
              </el-button>
            </div>
          </div>

          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="告警名称">{{ detail.alert_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="关联执行">
              <el-link
                v-if="detail.execution"
                type="primary"
                underline="never"
                @click="openExecution(detail.execution)"
              >
                {{ detail.execution_name || `执行 #${detail.execution}` }}
              </el-link>
              <span v-else>—</span>
            </el-descriptions-item>
            <el-descriptions-item label="严重级别">
              {{ getSeverityMeta(detail.severity).label }}
              <span v-if="detail.severity" class="text-small text-muted">（{{ detail.severity }}）</span>
            </el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatDateTime(detail.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="通知时间">{{ formatDateTime(detail.notified_at) }}</el-descriptions-item>
            <el-descriptions-item label="解决时间">{{ formatDateTime(detail.resolved_at) }}</el-descriptions-item>
            <el-descriptions-item label="Grafana 链接" :span="2">
              <el-link
                v-if="detail.grafana_url"
                type="primary"
                :href="detail.grafana_url"
                target="_blank"
                rel="noopener noreferrer"
              >
                {{ detail.grafana_url }}
              </el-link>
              <span v-else class="text-muted">未提供</span>
            </el-descriptions-item>
          </el-descriptions>

          <div class="detail-section">
            <div class="card-title">
              <span>诊断结论</span>
              <span class="text-small text-muted">AI / 规则引擎生成</span>
            </div>
            <pre class="diagnosis-content">{{ detail.diagnosis_content || '暂无诊断结论' }}</pre>
          </div>

          <div class="detail-section">
            <div class="card-title">
              <span>原始载荷（raw_payload）</span>
              <span class="text-small text-muted">Grafana Webhook / 手动诊断入参</span>
            </div>
            <JsonViewer :value="detail.raw_payload || {}" title="raw_payload" :max-height="360" />
          </div>
        </template>

        <EmptyState
          v-else-if="!detailLoading && !detailError"
          title="未选择诊断记录"
          description="从列表中选择一条诊断记录查看结论、原始载荷与处理状态。"
        />
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, RefreshLeft, Search } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import EmptyState from '@/components/EmptyState.vue'
import JsonViewer from '@/components/JsonViewer.vue'

import { performanceApi } from '@/api/performance'
import { formatDateTime } from '@/utils/format'
import {
  DIAGNOSIS_SOURCE_OPTIONS,
  DIAGNOSIS_STATUS_OPTIONS,
  getDiagnosisSourceMeta,
  getDiagnosisStatusMeta,
  getSeverityMeta,
  readErrorMessage,
} from './utils'

const props = defineProps({
  projectId: { type: [Number, String], default: null },
  refreshKey: { type: Number, default: 0 },
})

const emit = defineEmits(['changed', 'open-execution', 'switch-tab'])

const rows = ref([])
const loading = ref(false)
const errorMessage = ref('')
const filters = reactive({ search: '', source: '', status: '' })
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

const detailVisible = ref(false)
const detailId = ref(null)
const detail = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
const updatingStatus = ref('')
const updatingId = ref(null)

function diagnosisPreview(content) {
  const raw = String(content || '').replace(/\s+/g, ' ').trim()
  return raw.length > 90 ? `${raw.slice(0, 90)}…` : raw
}

async function loadDiagnoses() {
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
    if (filters.source) params.source = filters.source
    if (filters.status) params.status = filters.status
    const data = await performanceApi.listDiagnoses(params)
    rows.value = Array.isArray(data?.results) ? data.results : []
    pagination.total = Number(data?.count ?? rows.value.length)
  } catch (error) {
    rows.value = []
    pagination.total = 0
    errorMessage.value = readErrorMessage(error, 'AI 诊断记录加载失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadDiagnoses()
}

function handleReset() {
  filters.search = ''
  filters.source = ''
  filters.status = ''
  pagination.page = 1
  loadDiagnoses()
}

async function openDetail(row) {
  detailId.value = row.id
  detail.value = row
  detailError.value = ''
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await performanceApi.retrieveDiagnosis(row.id)
  } catch (error) {
    detailError.value = readErrorMessage(error, '诊断详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

function handleDrawerClosed() {
  detail.value = null
  detailError.value = ''
  detailLoading.value = false
  detailId.value = null
  updatingStatus.value = ''
}

async function patchStatus(id, status) {
  return performanceApi.updateDiagnosis(id, { status })
}

async function handleUpdateStatus(status) {
  if (!detail.value?.id) return
  updatingStatus.value = status
  try {
    const updated = await patchStatus(detail.value.id, status)
    detail.value = { ...detail.value, ...(updated || {}), status }
    ElMessage.success(
      status === 'resolved' ? '已标记为已解决' : status === 'ignored' ? '已忽略该诊断' : '已恢复为待处理',
    )
    await loadDiagnoses()
    emit('changed')
  } catch (error) {
    ElMessage.error(readErrorMessage(error, '诊断状态更新失败'))
  } finally {
    updatingStatus.value = ''
  }
}

async function handleQuickResolve(row) {
  updatingId.value = row.id
  try {
    await patchStatus(row.id, 'resolved')
    ElMessage.success(`已解决「${row.alert_name || `诊断 #${row.id}`}」`)
    await loadDiagnoses()
    emit('changed')
  } catch (error) {
    ElMessage.error(readErrorMessage(error, '诊断状态更新失败'))
  } finally {
    updatingId.value = null
  }
}

function openExecution(id) {
  if (!id) return
  detailVisible.value = false
  emit('open-execution', id)
}

watch(() => props.projectId, () => {
  pagination.page = 1
  loadDiagnoses()
})
watch(() => props.refreshKey, loadDiagnoses)

onMounted(loadDiagnoses)
</script>

<style scoped>
.diagnoses-pane {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.row-preview {
  margin-top: 2px;
  font-size: 12px;
  color: var(--aits-text-secondary);
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

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.diagnosis-content {
  margin: 0;
  padding: 14px 16px;
  overflow: auto;
  color: #1f2937;
  background: #f8fafc;
  border: 1px solid var(--aits-border);
  border-radius: 8px;
  font-family:
    'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, system-ui, -apple-system,
    sans-serif;
  font-size: 13.5px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
