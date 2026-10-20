<template>
  <div class="logs">
    <el-alert
      v-if="pageError"
      type="error"
      show-icon
      :closable="false"
      :title="pageError"
      description="执行日志加载失败，请确认后端服务已启动。"
    />

    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-select v-model="filters.status" class="filter-select" clearable placeholder="执行状态" @change="reload">
            <el-option v-for="item in STATUS_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select
            v-model="filters.task"
            class="filter-input"
            clearable
            filterable
            placeholder="按任务筛选"
            @change="reload"
          >
            <el-option v-for="task in tasks" :key="task.id" :label="task.name" :value="task.id" />
          </el-select>
          <el-select v-model="filters.project" class="filter-select" clearable placeholder="全部项目" @change="handleProjectChange">
            <el-option v-for="project in projectStore.projects" :key="project.id" :label="project.name" :value="project.id" />
          </el-select>
          <el-select v-model="filters.suite_type" class="filter-select" clearable placeholder="套件类型" @change="reload">
            <el-option v-for="item in SUITE_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </div>
        <div class="toolbar__right">
          <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        </div>
      </div>

      <DataTable
        :data="rows"
        :loading="loading"
        :total="total"
        :page="page"
        :page-size="pageSize"
        empty-text="暂无执行日志，可通过「立即运行」触发一次执行"
        @update:page="handlePageChange"
        @update:page-size="handleSizeChange"
      >
        <el-table-column prop="scheduled_task_name" label="任务名称" min-width="170" show-overflow-tooltip>
          <template #default="{ row }">{{ row.scheduled_task_name || row.task_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="套件类型" width="130">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ suiteTypeLabel(row.suite_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <StatusTag :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="统计（总/通过/失败/跳过）" width="190">
          <template #default="{ row }">
            {{ formatNumber(row.total) }} / <span class="text-success">{{ formatNumber(row.passed) }}</span> /
            <span class="text-danger">{{ formatNumber(row.failed) }}</span> /
            {{ formatNumber(row.skipped) }}
          </template>
        </el-table-column>
        <el-table-column label="通过率" width="100">
          <template #default="{ row }">{{ formatPercent(row.pass_rate) }}</template>
        </el-table-column>
        <el-table-column label="耗时" width="110">
          <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
        </el-table-column>
        <el-table-column label="触发人" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.triggered_by_name || '定时调度' }}</template>
        </el-table-column>
        <el-table-column label="执行时间" width="170">
          <template #default="{ row }">
            <div>{{ formatDateTime(row.started_at || row.created_at) }}</div>
            <div class="text-small text-muted">结束 {{ formatDateTime(row.finished_at) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <el-drawer v-model="detailVisible" title="执行详情" size="720px">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="任务">{{ detail.scheduled_task_name || detail.task_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <StatusTag :status="detail.status" />
          </el-descriptions-item>
          <el-descriptions-item label="套件类型">{{ suiteTypeLabel(detail.suite_type) }}</el-descriptions-item>
          <el-descriptions-item label="触发人">{{ detail.triggered_by_name || '定时调度' }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatDateTime(detail.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ formatDateTime(detail.finished_at) }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ formatDuration(detail.duration_ms) }}</el-descriptions-item>
          <el-descriptions-item label="通过率">{{ formatPercent(detail.pass_rate) }}</el-descriptions-item>
          <el-descriptions-item label="统计" :span="2">
            总 {{ formatNumber(detail.total) }} · 通过 {{ formatNumber(detail.passed) }} · 失败
            {{ formatNumber(detail.failed) }} · 跳过 {{ formatNumber(detail.skipped) }}
          </el-descriptions-item>
          <el-descriptions-item label="Celery 任务 ID" :span="2">
            <span class="mono">{{ detail.celery_task_id || '—' }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="detail.error_message"
          class="mt-16"
          type="error"
          show-icon
          :closable="false"
          :title="detail.error_message"
        />

        <div class="section mt-16">
          <div class="section__title">报告链接（report_urls）</div>
          <EmptyState v-if="!reportLinks.length" title="本次执行没有报告链接" :image-size="64" />
          <ul v-else class="link-list">
            <li v-for="(link, index) in reportLinks" :key="index">
              <a :href="link.url" target="_blank" rel="noopener noreferrer">{{ link.label }}</a>
            </li>
          </ul>
        </div>

        <div class="section">
          <div class="section__title">套件执行明细（step_log.suites）</div>
          <EmptyState v-if="!suiteSteps.length" title="暂无套件执行明细" :image-size="64" />
          <el-table v-else :data="suiteSteps" border size="small">
            <el-table-column prop="suite_id" label="套件 ID" width="90" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <StatusTag :status="row.status" />
              </template>
            </el-table-column>
            <el-table-column label="总" width="60">
              <template #default="{ row }">{{ formatNumber(row.total) }}</template>
            </el-table-column>
            <el-table-column label="通过" width="60">
              <template #default="{ row }">{{ formatNumber(row.passed) }}</template>
            </el-table-column>
            <el-table-column label="失败" width="60">
              <template #default="{ row }">{{ formatNumber(row.failed) }}</template>
            </el-table-column>
            <el-table-column label="通过率" width="90">
              <template #default="{ row }">{{ formatPercent(row.pass_rate) }}</template>
            </el-table-column>
            <el-table-column label="执行 ID" width="90">
              <template #default="{ row }">{{ row.execution_id || '—' }}</template>
            </el-table-column>
            <el-table-column label="报告 / 错误" min-width="160">
              <template #default="{ row }">
                <a v-if="row.report_url" :href="row.report_url" target="_blank" rel="noopener noreferrer">报告</a>
                <span v-else-if="row.error" class="text-danger">{{ row.error }}</span>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div v-if="stepErrors.length" class="section">
          <div class="section__title">执行错误</div>
          <ul class="error-list">
            <li v-for="(item, index) in stepErrors" :key="index">{{ item }}</li>
          </ul>
        </div>

        <div v-if="notification" class="section">
          <div class="section__title">通知结果（step_log.notification）</div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="成功">{{ formatNumber(notification.sent) }}</el-descriptions-item>
            <el-descriptions-item label="失败">{{ formatNumber(notification.failed) }}</el-descriptions-item>
            <el-descriptions-item label="跳过">{{ notification.skipped ? '是' : '否' }}</el-descriptions-item>
            <el-descriptions-item label="原因 / 错误">
              {{ notification.reason || notification.error || '—' }}
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <div class="section">
          <div class="section__title">原始 step_log</div>
          <JsonViewer :value="detail.step_log || {}" title="step_log" :max-height="320" />
        </div>
      </template>
      <template #footer>
        <el-button type="primary" @click="detailVisible = false">关闭</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyState from '@/components/EmptyState.vue'
import JsonViewer from '@/components/JsonViewer.vue'
import { useProjectStore } from '@/stores/project'
import { scheduledTasksApi } from '@/api/scheduledTasks'
import { formatDateTime, formatDuration, formatNumber, formatPercent } from '@/utils/format'

import { SUITE_TYPE_OPTIONS, suiteTypeLabel } from './utils/cron'

const route = useRoute()
const projectStore = useProjectStore()

const STATUS_OPTIONS = [
  { value: 'pending', label: '待执行' },
  { value: 'running', label: '执行中' },
  { value: 'passed', label: '通过' },
  { value: 'failed', label: '失败' },
  { value: 'error', label: '异常' },
  { value: 'cancelled', label: '已取消' },
]

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const pageError = ref('')

const tasks = ref([])
const filters = reactive({
  status: '',
  task: route.query.task ? Number(route.query.task) : '',
  project: projectStore.currentProjectId || '',
  suite_type: '',
})

const detailVisible = ref(false)
const detail = ref(null)

const suiteSteps = computed(() => {
  const value = detail.value?.step_log?.suites
  return Array.isArray(value) ? value : []
})

const stepErrors = computed(() => {
  const value = detail.value?.step_log?.errors
  return Array.isArray(value) ? value.map((item) => String(item)) : []
})

const notification = computed(() => {
  const value = detail.value?.step_log?.notification
  return value && typeof value === 'object' ? value : null
})

const reportLinks = computed(() => {
  const raw = detail.value?.report_urls
  if (!raw) return []
  const list = Array.isArray(raw) ? raw : [raw]
  return list
    .map((item, index) => {
      if (!item) return null
      if (typeof item === 'string') {
        return { url: item, label: item }
      }
      const url = item.report_url || item.url || ''
      if (!url) return null
      const scope = item.suite_type ? `${suiteTypeLabel(item.suite_type)} ` : ''
      const suite = item.suite_id ? `套件 #${item.suite_id} ` : ''
      return {
        url,
        label: `${scope}${suite}报告${item.execution_id ? `（执行 #${item.execution_id}）` : ''}` || `报告 ${index + 1}`,
      }
    })
    .filter(Boolean)
})

function requestParams() {
  const params = { page: page.value, page_size: pageSize.value }
  if (filters.status) params.status = filters.status
  if (filters.task) params.task = filters.task
  if (filters.suite_type) params.suite_type = filters.suite_type
  if (filters.project) params.project = filters.project
  return params
}

async function load() {
  loading.value = true
  pageError.value = ''
  try {
    const data = await scheduledTasksApi.listLogs(requestParams())
    rows.value = Array.isArray(data?.results) ? data.results : []
    total.value = Number(data?.count ?? rows.value.length)
  } catch (error) {
    rows.value = []
    total.value = 0
    pageError.value = error?.message || '执行日志加载失败'
  } finally {
    loading.value = false
  }
}

async function loadTasks() {
  try {
    const params = { page_size: 200 }
    if (filters.project) params.project = filters.project
    const data = await scheduledTasksApi.listTasks(params)
    tasks.value = Array.isArray(data?.results) ? data.results : []
  } catch (error) {
    tasks.value = []
  }
}

function reload() {
  page.value = 1
  load()
}

function handleProjectChange() {
  filters.task = ''
  loadTasks()
  reload()
}

function handlePageChange(next) {
  page.value = next
  load()
}

function handleSizeChange(size) {
  pageSize.value = size
  page.value = 1
  load()
}

async function openDetail(row) {
  detail.value = row
  detailVisible.value = true
  try {
    const data = await scheduledTasksApi.retrieveLog(row.id)
    detail.value = { ...row, ...data }
  } catch (error) {
    ElMessage.error(error?.message || '执行详情加载失败')
  }
}

onMounted(async () => {
  if (!projectStore.loaded) {
    try {
      await projectStore.fetchProjects()
    } catch (error) {
      // 忽略：无项目时仍展示可见日志
    }
  }
  await Promise.all([loadTasks(), load()])
})
</script>

<style scoped>
.logs {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section {
  margin-bottom: 18px;
}

.section__title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.link-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12.5px;
  line-height: 1.8;
}

.link-list a {
  color: #2563eb;
  text-decoration: none;
}

.link-list a:hover {
  text-decoration: underline;
}

.error-list {
  margin: 0;
  padding: 10px 12px 10px 28px;
  font-size: 12.5px;
  line-height: 1.7;
  color: #b91c1c;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
}

.text-success {
  color: #16a34a;
}

.text-danger {
  color: #dc2626;
}

.mt-16 {
  margin-top: 16px;
}
</style>
