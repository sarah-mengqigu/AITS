<template>
  <div class="mcp">
    <el-alert
      v-if="pageError"
      type="error"
      show-icon
      :closable="false"
      :title="pageError"
      description="MCP 配置接口加载失败，请确认后端服务已启动。"
    />

    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="filters.search"
            class="filter-input"
            placeholder="搜索配置名称"
            clearable
            :prefix-icon="Search"
            @keyup.enter="reload"
            @clear="reload"
          />
          <el-select v-model="filters.transport" class="filter-select" clearable placeholder="传输方式" @change="reload">
            <el-option label="stdio" value="stdio" />
            <el-option label="SSE" value="sse" />
            <el-option label="Streamable HTTP" value="streamable_http" />
          </el-select>
          <el-select v-model="filters.is_active" class="filter-select" clearable placeholder="启用状态" @change="reload">
            <el-option label="已启用" value="true" />
            <el-option label="已停用" value="false" />
          </el-select>
          <el-select v-model="filters.scope" class="filter-select" @change="reload">
            <el-option label="全部范围" value="all" />
            <el-option label="当前项目" value="current" :disabled="!projectStore.currentProjectId" />
          </el-select>
        </div>
        <div class="toolbar__right">
          <el-button :icon="Refresh" :loading="configLoading" @click="refreshAll">刷新</el-button>
          <el-button type="primary" :icon="Plus" @click="openCreate">新建 MCP 配置</el-button>
        </div>
      </div>

      <DataTable
        :data="configs"
        :loading="configLoading"
        :show-pagination="false"
        empty-text="暂无 MCP 配置，可先创建一个 stdio 或 SSE 服务"
      >
        <el-table-column prop="name" label="配置名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="传输方式" width="140">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ transportLabel(row.transport) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="工具数" width="90">
          <template #default="{ row }">{{ formatNumber(row.tool_count) }}</template>
        </el-table-column>
        <el-table-column label="最近状态" width="120">
          <template #default="{ row }">
            <StatusTag :status="statusToTag(row.last_status)" :text="statusLabel(row.last_status)" />
          </template>
        </el-table-column>
        <el-table-column label="范围" width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag v-if="!row.project" size="small" type="info" effect="plain">全局</el-tag>
            <span v-else>{{ projectName(row.project) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <StatusTag :status="row.is_active ? 'active' : 'inactive'" :text="row.is_active ? '启用' : '停用'" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button
              link
              type="success"
              size="small"
              :loading="refreshingId === row.id"
              @click="handleRefreshTools(row)"
            >
              刷新工具
            </el-button>
            <el-button link type="primary" size="small" @click="showTools(row)">查看工具</el-button>
            <ConfirmButton
              text="删除"
              link
              size="small"
              :title="`删除 MCP 配置「${row.name}」`"
              content="删除后该配置下的工具记录也会被清理，确定删除？"
              @confirm="handleDelete(row)"
            />
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <div class="page-card">
      <div class="card-title">
        <span>MCP 工具列表</span>
        <div class="card-title__actions">
          <el-select
            v-model="toolConfigId"
            class="filter-select"
            clearable
            placeholder="全部 MCP 配置"
            @change="loadTools"
          >
            <el-option v-for="item in configs" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
          <el-button :icon="Refresh" :loading="toolLoading" @click="loadTools">刷新</el-button>
        </div>
      </div>

      <DataTable
        :data="tools"
        :loading="toolLoading"
        :total="toolTotal"
        :page="toolPage"
        :page-size="toolPageSize"
        empty-text="暂无工具，点击上方「刷新工具」从 MCP Server 同步"
        @update:page="handleToolPageChange"
        @update:page-size="handleToolSizeChange"
      >
        <el-table-column prop="name" label="工具名称" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '—' }}</template>
        </el-table-column>
        <el-table-column label="所属配置" width="150">
          <template #default="{ row }">{{ configName(row.config) }}</template>
        </el-table-column>
        <el-table-column label="入参 Schema" width="130">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="showSchema(row)">查看 JSON</el-button>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <StatusTag :status="row.is_enabled ? 'active' : 'inactive'" :text="row.is_enabled ? '启用' : '停用'" />
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <el-drawer v-model="drawerVisible" :title="drawerTitle" size="580px" :destroy-on-close="true">
      <el-form label-width="110px" class="drawer-form">
        <el-form-item label="配置范围" required>
          <el-radio-group v-model="form.scope">
            <el-radio value="global">全局配置</el-radio>
            <el-radio value="project" :disabled="!projectStore.currentProjectId">当前项目</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="配置名称" required>
          <el-input v-model="form.name" maxlength="128" placeholder="例如：filesystem-mcp" />
        </el-form-item>
        <el-form-item label="传输方式">
          <el-select v-model="form.transport" class="w-full">
            <el-option label="stdio（本地进程）" value="stdio" />
            <el-option label="SSE（Server-Sent Events）" value="sse" />
            <el-option label="Streamable HTTP" value="streamable_http" />
          </el-select>
        </el-form-item>
        <el-form-item label="Server 配置">
          <el-input
            v-model="form.serverConfigText"
            type="textarea"
            :rows="10"
            placeholder='{"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem"]}'
          />
          <div class="json-actions">
            <el-button size="small" @click="formatJson">格式化 JSON</el-button>
            <span v-if="jsonError" class="json-error">{{ jsonError }}</span>
            <span v-else class="field-hint inline">JSON 对象；声明 tools 后「刷新工具」可同步工具清单</span>
          </div>
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

    <el-dialog v-model="schemaVisible" :title="schemaTitle" width="620px">
      <JsonViewer :value="schemaValue" title="input_schema" :max-height="420" />
      <template #footer>
        <el-button type="primary" @click="schemaVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import ConfirmButton from '@/components/ConfirmButton.vue'
import JsonViewer from '@/components/JsonViewer.vue'
import { useProjectStore } from '@/stores/project'
import { aiCoreApi } from '@/api/aiCore'
import { formatNumber } from '@/utils/format'

const projectStore = useProjectStore()

const configs = ref([])
const configLoading = ref(false)
const pageError = ref('')
const refreshingId = ref(null)
const filters = reactive({ search: '', transport: '', is_active: '', scope: 'all' })

const tools = ref([])
const toolLoading = ref(false)
const toolTotal = ref(0)
const toolPage = ref(1)
const toolPageSize = ref(20)
const toolConfigId = ref(null)

const drawerVisible = ref(false)
const mode = ref('create')
const currentId = ref(null)
const saving = ref(false)
const form = reactive({
  scope: 'global',
  project: null,
  name: '',
  transport: 'stdio',
  serverConfigText: '{}',
  is_active: true,
})
const jsonError = ref('')

const schemaVisible = ref(false)
const schemaTitle = ref('')
const schemaValue = ref(null)

const drawerTitle = computed(() => (mode.value === 'create' ? '新建 MCP 配置' : '编辑 MCP 配置'))

function projectName(id) {
  return projectStore.projects.find((item) => item.id === id)?.name || `项目 #${id}`
}

function configName(id) {
  return configs.value.find((item) => item.id === id)?.name || `配置 #${id}`
}

function transportLabel(value) {
  if (value === 'streamable_http') return 'Streamable HTTP'
  if (value === 'sse') return 'SSE'
  return 'stdio'
}

function statusLabel(status) {
  if (status === 'connected') return '已连接'
  if (status === 'disabled') return '已停用'
  if (status === 'error') return '异常'
  return '未探测'
}

function statusToTag(status) {
  if (status === 'connected') return 'success'
  if (status === 'disabled') return 'inactive'
  if (status === 'error') return 'error'
  return 'pending'
}

function configParams() {
  const params = { page_size: 100 }
  if (filters.search.trim()) params.search = filters.search.trim()
  if (filters.transport) params.transport = filters.transport
  if (filters.is_active !== '') params.is_active = filters.is_active
  if (filters.scope === 'current' && projectStore.currentProjectId) {
    params.project = projectStore.currentProjectId
  }
  return params
}

async function loadConfigs() {
  configLoading.value = true
  pageError.value = ''
  try {
    const data = await aiCoreApi.listMcpConfigs(configParams())
    configs.value = Array.isArray(data?.results) ? data.results : []
  } catch (error) {
    configs.value = []
    pageError.value = error?.message || 'MCP 配置加载失败'
  } finally {
    configLoading.value = false
  }
}

async function loadTools() {
  toolLoading.value = true
  try {
    const params = { page: toolPage.value, page_size: toolPageSize.value }
    if (toolConfigId.value) params.config = toolConfigId.value
    const data = await aiCoreApi.listMcpTools(params)
    tools.value = Array.isArray(data?.results) ? data.results : []
    toolTotal.value = Number(data?.count ?? tools.value.length)
  } catch (error) {
    tools.value = []
    toolTotal.value = 0
    ElMessage.error(error?.message || '工具列表加载失败')
  } finally {
    toolLoading.value = false
  }
}

function reload() {
  loadConfigs()
}

function refreshAll() {
  loadConfigs()
  loadTools()
}

function handleToolPageChange(next) {
  toolPage.value = next
  loadTools()
}

function handleToolSizeChange(size) {
  toolPageSize.value = size
  toolPage.value = 1
  loadTools()
}

function openCreate() {
  mode.value = 'create'
  currentId.value = null
  Object.assign(form, {
    scope: projectStore.currentProjectId ? 'project' : 'global',
    project: projectStore.currentProjectId || null,
    name: '',
    transport: 'stdio',
    serverConfigText: JSON.stringify(
      { command: 'npx', args: ['-y', '@modelcontextprotocol/server-filesystem', '/tmp'] },
      null,
      2,
    ),
    is_active: true,
  })
  jsonError.value = ''
  drawerVisible.value = true
}

function openEdit(row) {
  mode.value = 'edit'
  currentId.value = row.id
  Object.assign(form, {
    scope: row.project ? 'project' : 'global',
    project: row.project ?? null,
    name: row.name || '',
    transport: row.transport || 'stdio',
    serverConfigText: JSON.stringify(row.server_config ?? {}, null, 2),
    is_active: row.is_active !== false,
  })
  jsonError.value = ''
  drawerVisible.value = true
}

function formatJson() {
  try {
    const parsed = JSON.parse(form.serverConfigText || '{}')
    form.serverConfigText = JSON.stringify(parsed, null, 2)
    jsonError.value = ''
    ElMessage.success('已格式化')
  } catch (error) {
    jsonError.value = `JSON 不合法：${error.message}`
  }
}

function buildPayload() {
  const name = String(form.name || '').trim()
  if (!name) return { error: '配置名称不能为空' }
  let serverConfig = {}
  const raw = String(form.serverConfigText || '').trim()
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (parsed !== null && (typeof parsed !== 'object' || Array.isArray(parsed))) {
        return { error: 'Server 配置必须是 JSON 对象' }
      }
      serverConfig = parsed || {}
    } catch (error) {
      return { error: `Server 配置不是合法 JSON：${error.message}` }
    }
  }
  return {
    payload: {
      project: form.scope === 'project' ? form.project ?? null : null,
      name,
      transport: form.transport,
      server_config: serverConfig,
      is_active: Boolean(form.is_active),
    },
  }
}

async function handleSave() {
  const { payload, error } = buildPayload()
  if (error) {
    jsonError.value = error
    ElMessage.warning(error)
    return
  }
  if (form.scope === 'project' && !payload.project) {
    ElMessage.warning('请先在顶部选择当前项目，或改为全局配置')
    return
  }
  saving.value = true
  try {
    if (mode.value === 'create') {
      await aiCoreApi.createMcpConfig(payload)
      ElMessage.success('MCP 配置已创建')
    } else {
      await aiCoreApi.updateMcpConfig(currentId.value, payload)
      ElMessage.success('MCP 配置已更新')
    }
    drawerVisible.value = false
    await loadConfigs()
  } catch (error) {
    ElMessage.error(error?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleRefreshTools(row) {
  refreshingId.value = row.id
  try {
    const data = await aiCoreApi.refreshMcpTools(row.id)
    ElMessage.success(`已同步 ${data?.count ?? 0} 个工具（状态：${statusLabel(data?.status)}）`)
    await Promise.all([loadConfigs(), loadTools()])
  } catch (error) {
    ElMessage.error(error?.message || '刷新工具失败')
  } finally {
    refreshingId.value = null
  }
}

async function handleDelete(row) {
  try {
    await aiCoreApi.removeMcpConfig(row.id)
    ElMessage.success('已删除')
    await Promise.all([loadConfigs(), loadTools()])
  } catch (error) {
    ElMessage.error(error?.message || '删除失败')
  }
}

function showTools(row) {
  toolConfigId.value = row.id
  toolPage.value = 1
  loadTools()
}

function showSchema(row) {
  schemaTitle.value = `${row.name} · 入参 Schema`
  schemaValue.value = row.input_schema ?? {}
  schemaVisible.value = true
}

onMounted(async () => {
  if (!projectStore.loaded) {
    try {
      await projectStore.fetchProjects()
    } catch (error) {
      // 忽略：无项目时仍可管理全局配置
    }
  }
  await Promise.all([loadConfigs(), loadTools()])
})
</script>

<style scoped>
.mcp {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card-title__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.drawer-form {
  padding-right: 8px;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.json-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  margin-top: 6px;
}

.json-error {
  font-size: 12px;
  color: #dc2626;
}

.field-hint {
  width: 100%;
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: #94a3b8;
}

.field-hint.inline {
  width: auto;
  margin: 0;
}

.w-full {
  width: 100%;
}
</style>
