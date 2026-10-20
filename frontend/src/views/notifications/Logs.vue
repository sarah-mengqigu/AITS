<template>
  <div class="logs">
    <el-alert
      v-if="pageError"
      type="error"
      show-icon
      :closable="false"
      :title="pageError"
      description="通知日志加载失败，请确认后端服务已启动。"
    />

    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="filters.search"
            class="filter-input"
            placeholder="搜索标题 / 内容 / 任务名"
            clearable
            :prefix-icon="Search"
            @keyup.enter="reload"
            @clear="reload"
          />
          <el-select v-model="filters.channel_code" class="filter-select" clearable placeholder="通知渠道" @change="reload">
            <el-option v-for="item in CHANNEL_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="filters.status" class="filter-select" clearable placeholder="发送状态" @change="reload">
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
          </el-select>
          <el-select v-model="filters.project" class="filter-select" clearable placeholder="全部项目" @change="reload">
            <el-option v-for="project in projectStore.projects" :key="project.id" :label="project.name" :value="project.id" />
          </el-select>
        </div>
        <div class="toolbar__right">
          <el-button :icon="Refresh" :loading="loading" @click="reload">刷新</el-button>
        </div>
      </div>

      <DataTable
        :data="rows"
        :loading="loading"
        :total="total"
        :page="page"
        :page-size="pageSize"
        empty-text="暂无通知日志，发送一次测试通知后即可查看"
        @update:page="handlePageChange"
        @update:page-size="handleSizeChange"
      >
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="渠道" width="120">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ channelLabel(row.channel_code) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <StatusTag :status="row.status" :text="notificationStatusText(row.status)" />
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column label="接收人 / 任务" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.receiver_name || row.scheduled_task_name || row.project_name || '—' }}
          </template>
        </el-table-column>
        <el-table-column label="失败原因" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="{ 'text-danger': row.status === 'failed' }">{{ row.error_message || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <el-drawer v-model="detailVisible" title="通知详情" size="700px">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="发送时间">{{ formatDateTime(detail.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="渠道">{{ channelLabel(detail.channel_code) }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <StatusTag :status="detail.status" :text="notificationStatusText(detail.status)" />
          </el-descriptions-item>
          <el-descriptions-item label="接收人">{{ detail.receiver_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="项目">{{ detail.project_name || '全局' }}</el-descriptions-item>
          <el-descriptions-item label="关联定时任务">{{ detail.scheduled_task_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="标题" :span="2">{{ detail.title || '—' }}</el-descriptions-item>
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
          <div class="section__title">通知内容（Markdown 纯文本）</div>
          <pre class="content-block">{{ detail.content || '（空）' }}</pre>
        </div>

        <div class="section">
          <div class="section__title">请求载荷（payload）</div>
          <JsonViewer :value="detail.payload || {}" title="payload" :max-height="320" />
        </div>
      </template>
      <template #footer>
        <el-button type="primary" @click="detailVisible = false">关闭</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import JsonViewer from '@/components/JsonViewer.vue'
import { useProjectStore } from '@/stores/project'
import { notificationsApi } from '@/api/notifications'
import { formatDateTime } from '@/utils/format'

import { CHANNEL_OPTIONS, channelLabel, notificationStatusText } from './utils'

const projectStore = useProjectStore()

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const pageError = ref('')

const filters = reactive({
  search: '',
  channel_code: '',
  status: '',
  project: projectStore.currentProjectId || '',
})

const detailVisible = ref(false)
const detail = ref(null)

function requestParams() {
  const params = { page: page.value, page_size: pageSize.value }
  if (filters.search.trim()) params.search = filters.search.trim()
  if (filters.channel_code) params.channel_code = filters.channel_code
  if (filters.status) params.status = filters.status
  if (filters.project) params.project = filters.project
  return params
}

async function load() {
  loading.value = true
  pageError.value = ''
  try {
    const data = await notificationsApi.listLogs(requestParams())
    rows.value = Array.isArray(data?.results) ? data.results : []
    total.value = Number(data?.count ?? rows.value.length)
  } catch (error) {
    rows.value = []
    total.value = 0
    pageError.value = error?.message || '通知日志加载失败'
  } finally {
    loading.value = false
  }
}

function reload() {
  page.value = 1
  load()
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
    const data = await notificationsApi.retrieveLog(row.id)
    detail.value = { ...row, ...data }
  } catch (error) {
    ElMessage.error(error?.message || '通知详情加载失败')
  }
}

onMounted(async () => {
  if (!projectStore.loaded) {
    try {
      await projectStore.fetchProjects()
    } catch (error) {
      // 忽略：无项目时仍可查看全局日志
    }
  }
  if (!filters.project) filters.project = projectStore.currentProjectId || ''
  await load()
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

.content-block {
  max-height: 320px;
  margin: 0;
  padding: 12px 14px;
  overflow: auto;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12.5px;
  line-height: 1.7;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
  background: #f8fafc;
  border: 1px solid var(--aits-border);
  border-radius: 8px;
}

.text-danger {
  color: #dc2626;
}

.mt-16 {
  margin-top: 16px;
}
</style>
