<template>
  <div class="channels">
    <el-alert
      v-if="pageError"
      type="error"
      show-icon
      :closable="false"
      :title="pageError"
      description="渠道列表加载失败，请确认后端服务已启动。"
    />

    <el-alert
      v-if="!isStaff"
      type="info"
      show-icon
      :closable="false"
      title="渠道为全局配置，仅管理员（staff）可修改"
      description="当前账号可查看渠道与启用状态，如需调整请联系管理员。"
    />

    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="filters.search"
            class="filter-input"
            placeholder="搜索渠道名称 / 说明"
            clearable
            :prefix-icon="Search"
            @keyup.enter="load"
            @clear="load"
          />
          <el-select v-model="filters.channel_code" class="filter-select" clearable placeholder="渠道类型" @change="load">
            <el-option v-for="item in CHANNEL_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="filters.is_active" class="filter-select" clearable placeholder="启用状态" @change="load">
            <el-option label="已启用" value="true" />
            <el-option label="已停用" value="false" />
          </el-select>
        </div>
        <div class="toolbar__right">
          <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        </div>
      </div>

      <div v-loading="loading" class="channel-grid">
        <div v-for="channel in channels" :key="channel.id" class="channel-card">
          <div class="channel-card__head">
            <div class="channel-card__title">
              <span class="channel-card__name">{{ channel.name }}</span>
              <el-tag size="small" effect="plain" type="info">{{ channel.channel_code }}</el-tag>
            </div>
            <StatusTag :status="channel.is_active ? 'active' : 'inactive'" :text="channel.is_active ? '启用' : '停用'" />
          </div>
          <p class="channel-card__desc">{{ channel.description || channelMeta(channel.channel_code).description }}</p>
          <div class="channel-card__meta">
            <span class="text-small text-muted">投递方式：{{ channelMeta(channel.channel_code).target === 'email' ? 'SMTP 邮件' : 'HTTP Webhook' }}</span>
          </div>
          <div class="channel-card__foot">
            <el-button size="small" @click="showSchema(channel)">配置模板</el-button>
            <el-button size="small" type="primary" plain @click="openEdit(channel)" :disabled="!isStaff">
              编辑
            </el-button>
            <el-button size="small" type="success" plain @click="$emit('test', channel.channel_code)">
              测试发送
            </el-button>
          </div>
        </div>
      </div>

      <EmptyState v-if="!loading && !channels.length" title="暂无通知渠道" description="后端初始化后会自动创建 5 个内置渠道" />
    </div>

    <el-dialog v-model="editVisible" :title="`编辑渠道：${activeChannel?.name || ''}`" width="560px">
      <el-form label-width="100px">
        <el-form-item label="渠道类型">
          <el-input :model-value="activeChannel?.channel_code || ''" disabled />
        </el-form-item>
        <el-form-item label="渠道名称">
          <el-input v-model="form.name" maxlength="64" />
        </el-form-item>
        <el-form-item label="渠道说明">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="是否启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
        <el-form-item label="配置模板">
          <el-input v-model="form.configSchemaText" type="textarea" :rows="5" placeholder="{}" />
          <div class="field-hint">JSON 对象，可留空；非法 JSON 将无法保存。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="schemaVisible" :title="`${activeChannel?.name || ''} · 配置模板`" width="600px">
      <JsonViewer :value="activeChannel?.config_schema || {}" title="config_schema" :max-height="420" />
      <template #footer>
        <el-button type="primary" @click="schemaVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'

import StatusTag from '@/components/StatusTag.vue'
import EmptyState from '@/components/EmptyState.vue'
import JsonViewer from '@/components/JsonViewer.vue'
import { useAuthStore } from '@/stores/auth'
import { notificationsApi } from '@/api/notifications'

import { CHANNEL_OPTIONS, channelMeta } from './utils'

defineEmits(['test'])

const authStore = useAuthStore()
const isStaff = computed(() => Boolean(authStore.user?.is_staff || authStore.user?.is_superuser))

const channels = ref([])
const loading = ref(false)
const pageError = ref('')
const filters = reactive({ search: '', channel_code: '', is_active: '' })

const editVisible = ref(false)
const schemaVisible = ref(false)
const activeChannel = ref(null)
const saving = ref(false)
const form = reactive({ name: '', description: '', is_active: true, configSchemaText: '{}' })

async function load() {
  loading.value = true
  pageError.value = ''
  const params = { page_size: 100, ordering: 'id' }
  if (filters.search.trim()) params.search = filters.search.trim()
  if (filters.channel_code) params.channel_code = filters.channel_code
  if (filters.is_active !== '') params.is_active = filters.is_active
  try {
    const data = await notificationsApi.listChannels(params)
    channels.value = Array.isArray(data?.results) ? data.results : []
  } catch (error) {
    channels.value = []
    pageError.value = error?.message || '渠道列表加载失败'
  } finally {
    loading.value = false
  }
}

function openEdit(channel) {
  activeChannel.value = channel
  Object.assign(form, {
    name: channel.name || '',
    description: channel.description || '',
    is_active: channel.is_active !== false,
    configSchemaText: JSON.stringify(channel.config_schema ?? {}, null, 2),
  })
  editVisible.value = true
}

function showSchema(channel) {
  activeChannel.value = channel
  schemaVisible.value = true
}

async function handleSave() {
  if (!activeChannel.value) return
  let configSchema = {}
  const raw = String(form.configSchemaText || '').trim()
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (parsed !== null && (typeof parsed !== 'object' || Array.isArray(parsed))) {
        ElMessage.warning('配置模板必须是 JSON 对象')
        return
      }
      configSchema = parsed || {}
    } catch (error) {
      ElMessage.warning(`配置模板不是合法 JSON：${error.message}`)
      return
    }
  }
  saving.value = true
  try {
    await notificationsApi.updateChannel(activeChannel.value.id, {
      name: String(form.name || '').trim(),
      description: String(form.description || ''),
      is_active: Boolean(form.is_active),
      config_schema: configSchema,
    })
    ElMessage.success('渠道已更新')
    editVisible.value = false
    await load()
  } catch (error) {
    if (error?.response?.status === 403) {
      ElMessage.error('没有权限修改通知渠道（仅管理员可操作）')
    } else {
      ElMessage.error(error?.message || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.channels {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.channel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}

.channel-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  background: #f8fafc;
  border: 1px solid var(--aits-border);
  border-radius: 10px;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}

.channel-card:hover {
  border-color: #bfdbfe;
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.08);
}

.channel-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.channel-card__title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.channel-card__name {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}

.channel-card__desc {
  flex: 1;
  margin: 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--aits-text-secondary);
}

.channel-card__meta {
  display: flex;
  gap: 8px;
}

.channel-card__foot {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 4px;
}

.field-hint {
  width: 100%;
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: #94a3b8;
}
</style>
