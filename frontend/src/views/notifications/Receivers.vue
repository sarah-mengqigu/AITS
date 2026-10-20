<template>
  <div class="receivers">
    <el-alert
      v-if="pageError"
      type="error"
      show-icon
      :closable="false"
      :title="pageError"
      description="接收人列表加载失败，请确认后端服务已启动。"
    />

    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="filters.search"
            class="filter-input"
            placeholder="搜索名称 / Webhook / 邮箱"
            clearable
            :prefix-icon="Search"
            @keyup.enter="reload"
            @clear="reload"
          />
          <el-select v-model="filters.project" class="filter-select" clearable placeholder="全部项目" @change="reload">
            <el-option v-for="project in projectStore.projects" :key="project.id" :label="project.name" :value="project.id" />
          </el-select>
          <el-select v-model="filters.channel" class="filter-select" clearable placeholder="通知渠道" @change="reload">
            <el-option v-for="channel in channels" :key="channel.id" :label="channel.name" :value="channel.id" />
          </el-select>
          <el-select v-model="filters.is_active" class="filter-select" clearable placeholder="启用状态" @change="reload">
            <el-option label="已启用" value="true" />
            <el-option label="已停用" value="false" />
          </el-select>
        </div>
        <div class="toolbar__right">
          <el-button :icon="Refresh" :loading="loading" @click="reload">刷新</el-button>
          <el-button type="primary" :icon="Plus" @click="openCreate">新建接收人</el-button>
        </div>
      </div>

      <DataTable
        :data="rows"
        :loading="loading"
        :total="total"
        :page="page"
        :page-size="pageSize"
        empty-text="暂无通知接收人"
        @update:page="handlePageChange"
        @update:page-size="handleSizeChange"
      >
        <el-table-column prop="name" label="接收人名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="渠道" width="120">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" type="primary">
              {{ row.channel_name || channelLabel(row.channel_code) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="项目" width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag v-if="!row.project" size="small" type="info" effect="plain">全局</el-tag>
            <span v-else>{{ row.project_name || projectName(row.project) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="目标地址" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ receiverTargetLabel(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <StatusTag :status="row.is_active ? 'active' : 'inactive'" :text="row.is_active ? '启用' : '停用'" />
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <ConfirmButton
              text="删除"
              link
              size="small"
              :title="`删除接收人「${row.name}」`"
              content="删除后引用该接收人的定时任务将不再推送通知，确定删除？"
              @confirm="handleDelete(row)"
            />
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <el-drawer v-model="drawerVisible" :title="drawerTitle" size="520px" :destroy-on-close="true">
      <el-form label-width="100px">
        <el-form-item label="归属范围" required>
          <el-radio-group v-model="form.scope">
            <el-radio label="project" :disabled="!projectStore.currentProjectId">当前项目</el-radio>
            <el-radio label="global" :disabled="!isStaff">全局（仅管理员）</el-radio>
          </el-radio-group>
          <div class="field-hint">
            {{ form.scope === 'project'
              ? `归属项目：${projectStore.currentProjectName || '未选择'}`
              : '全局接收人不归属任何项目，仅管理员可维护' }}
          </div>
        </el-form-item>
        <el-form-item label="接收人名称" required>
          <el-input v-model="form.name" maxlength="128" placeholder="例如：测试组钉钉群" />
        </el-form-item>
        <el-form-item label="通知渠道" required>
          <el-select v-model="form.channel" class="w-full" placeholder="选择渠道" @change="handleChannelChange">
            <el-option
              v-for="channel in channels"
              :key="channel.id"
              :label="`${channel.name}（${channel.channel_code}）`"
              :value="channel.id"
              :disabled="!channel.is_active"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="isWebhook" label="Webhook 地址" :required="isWebhook">
          <el-input v-model="form.webhook_url" placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." />
        </el-form-item>
        <el-form-item v-if="isEmail" label="收件邮箱" :required="isEmail">
          <el-input v-model="form.target_address" type="textarea" :rows="3" placeholder="多个邮箱用逗号分隔" />
          <div class="field-hint">支持逗号 / 分号分隔的多个邮箱。</div>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" />
        </el-form-item>
        <el-form-item label="扩展元数据">
          <el-input v-model="form.metadataText" type="textarea" :rows="3" placeholder="{}" />
          <div class="field-hint">JSON 对象，可留空。</div>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="drawerVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import ConfirmButton from '@/components/ConfirmButton.vue'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'
import { notificationsApi } from '@/api/notifications'
import { formatDateTime } from '@/utils/format'

import { channelLabel, isEmailChannel, isWebhookChannel, receiverTargetLabel } from './utils'

const authStore = useAuthStore()
const projectStore = useProjectStore()
const isStaff = computed(() => Boolean(authStore.user?.is_staff || authStore.user?.is_superuser))

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const pageError = ref('')
const channels = ref([])

const filters = reactive({
  search: '',
  project: projectStore.currentProjectId || '',
  channel: '',
  is_active: '',
})

const drawerVisible = ref(false)
const mode = ref('create')
const currentId = ref(null)
const saving = ref(false)
const form = reactive(emptyForm())

const drawerTitle = computed(() => (mode.value === 'create' ? '新建接收人' : '编辑接收人'))

const selectedChannel = computed(() => channels.value.find((item) => item.id === form.channel) || null)
const selectedChannelCode = computed(() => selectedChannel.value?.channel_code || '')
const isWebhook = computed(() => Boolean(selectedChannelCode.value) && isWebhookChannel(selectedChannelCode.value))
const isEmail = computed(() => Boolean(selectedChannelCode.value) && isEmailChannel(selectedChannelCode.value))

function emptyForm(values = {}) {
  return {
    scope: 'project',
    project: projectStore.currentProjectId || null,
    name: '',
    channel: null,
    webhook_url: '',
    target_address: '',
    description: '',
    is_active: true,
    metadataText: '{}',
    ...values,
  }
}

function projectName(id) {
  return projectStore.projects.find((item) => item.id === id)?.name || `项目 #${id}`
}

function requestParams() {
  const params = { page: page.value, page_size: pageSize.value }
  if (filters.search.trim()) params.search = filters.search.trim()
  if (filters.project) params.project = filters.project
  if (filters.channel) params.channel = filters.channel
  if (filters.is_active !== '') params.is_active = filters.is_active
  return params
}

async function load() {
  loading.value = true
  pageError.value = ''
  try {
    const data = await notificationsApi.listReceivers(requestParams())
    rows.value = Array.isArray(data?.results) ? data.results : []
    total.value = Number(data?.count ?? rows.value.length)
  } catch (error) {
    rows.value = []
    total.value = 0
    pageError.value = error?.message || '接收人加载失败'
  } finally {
    loading.value = false
  }
}

async function loadChannels() {
  try {
    const data = await notificationsApi.listChannels({ page_size: 100, ordering: 'id' })
    channels.value = Array.isArray(data?.results) ? data.results : []
  } catch (error) {
    channels.value = []
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

function handleChannelChange() {
  form.webhook_url = ''
  form.target_address = ''
}

function openCreate() {
  mode.value = 'create'
  currentId.value = null
  Object.assign(form, emptyForm())
  drawerVisible.value = true
}

function openEdit(row) {
  mode.value = 'edit'
  currentId.value = row.id
  Object.assign(
    form,
    emptyForm({
      scope: row.project ? 'project' : 'global',
      project: row.project ?? null,
      name: row.name || '',
      channel: row.channel ?? null,
      webhook_url: row.webhook_url || '',
      target_address: row.target_address || '',
      description: row.description || '',
      is_active: row.is_active !== false,
      metadataText: JSON.stringify(row.metadata ?? {}, null, 2),
    }),
  )
  drawerVisible.value = true
}

async function handleSave() {
  const name = String(form.name || '').trim()
  if (!name) {
    ElMessage.warning('接收人名称不能为空')
    return
  }
  if (!form.channel) {
    ElMessage.warning('请选择通知渠道')
    return
  }
  if (form.scope === 'project' && !form.project) {
    ElMessage.warning('请先在顶部选择当前项目，或改为全局接收人')
    return
  }
  if (isWebhook.value && !String(form.webhook_url || '').trim()) {
    ElMessage.warning('该渠道需要填写 Webhook 地址')
    return
  }
  if (isEmail.value && !String(form.target_address || '').includes('@')) {
    ElMessage.warning('请填写合法的收件邮箱地址')
    return
  }
  let metadata = {}
  const raw = String(form.metadataText || '').trim()
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (parsed !== null && (typeof parsed !== 'object' || Array.isArray(parsed))) {
        ElMessage.warning('扩展元数据必须是 JSON 对象')
        return
      }
      metadata = parsed || {}
    } catch (error) {
      ElMessage.warning(`扩展元数据不是合法 JSON：${error.message}`)
      return
    }
  }

  const payload = {
    project: form.scope === 'project' ? form.project : null,
    name,
    channel: form.channel,
    webhook_url: isWebhook.value ? String(form.webhook_url || '').trim() : '',
    target_address: isEmail.value ? String(form.target_address || '').trim() : '',
    description: String(form.description || ''),
    is_active: Boolean(form.is_active),
    metadata,
  }

  saving.value = true
  try {
    if (mode.value === 'create') {
      await notificationsApi.createReceiver(payload)
      ElMessage.success('接收人已创建')
    } else {
      await notificationsApi.updateReceiver(currentId.value, payload)
      ElMessage.success('接收人已更新')
    }
    drawerVisible.value = false
    await load()
  } catch (error) {
    if (error?.response?.status === 403) {
      ElMessage.error('没有权限维护该接收人（项目需管理员、全局需 staff）')
    } else {
      ElMessage.error(error?.message || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  try {
    await notificationsApi.removeReceiver(row.id)
    ElMessage.success('已删除')
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (error) {
    if (error?.response?.status === 403) {
      ElMessage.error('没有权限删除该接收人')
    } else {
      ElMessage.error(error?.message || '删除失败')
    }
  }
}

onMounted(async () => {
  if (!projectStore.loaded) {
    try {
      await projectStore.fetchProjects()
    } catch (error) {
      // 忽略：无项目时仅能查看全局接收人
    }
  }
  if (!filters.project) filters.project = projectStore.currentProjectId || ''
  await Promise.all([loadChannels(), load()])
})
</script>

<style scoped>
.receivers {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.w-full {
  width: 100%;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.field-hint {
  width: 100%;
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: #94a3b8;
}
</style>
