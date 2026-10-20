<template>
  <div class="models">
    <el-alert
      v-if="pageError"
      type="error"
      show-icon
      :closable="false"
      :title="pageError"
      description="列表加载失败，可尝试切换筛选条件或稍后重试。"
      @close="pageError = ''"
    />

    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="filters.search"
            class="filter-input"
            placeholder="搜索名称 / 模型名"
            clearable
            :prefix-icon="Search"
            @keyup.enter="reload"
            @clear="reload"
          />
          <el-select v-model="filters.scope" class="filter-select" @change="reload">
            <el-option label="全部范围" value="all" />
            <el-option label="当前项目" value="current" :disabled="!projectStore.currentProjectId" />
          </el-select>
          <el-select v-model="filters.provider" class="filter-select" clearable placeholder="提供商" @change="reload">
            <el-option v-for="item in PROVIDER_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="filters.model_type" class="filter-select" clearable placeholder="模型类型" @change="reload">
            <el-option v-for="item in MODEL_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="filters.is_active" class="filter-select" clearable placeholder="启用状态" @change="reload">
            <el-option label="已启用" value="true" />
            <el-option label="已停用" value="false" />
          </el-select>
        </div>
        <div class="toolbar__right">
          <el-button :icon="Refresh" :loading="loading" @click="reload">刷新</el-button>
          <el-button type="primary" :icon="Plus" @click="openCreate">新建模型配置</el-button>
        </div>
      </div>

      <DataTable
        :data="rows"
        :loading="loading"
        :total="total"
        :page="page"
        :page-size="pageSize"
        empty-text="暂无模型配置，点击「新建模型配置」开始"
        @update:page="handlePageChange"
        @update:page-size="handleSizeChange"
      >
        <el-table-column prop="name" label="配置名称" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="name-cell">
              {{ row.name }}
              <el-tag v-if="row.is_default" size="small" type="success" effect="plain">默认</el-tag>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="提供商" width="130">
          <template #default="{ row }">{{ providerLabel(row.provider) }}</template>
        </el-table-column>
        <el-table-column prop="model_name" label="模型名称" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.model_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="row.model_type === 'vision' ? 'warning' : 'primary'">
              {{ modelTypeLabel(row.model_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="范围" width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag v-if="!row.project" size="small" type="info" effect="plain">全局</el-tag>
            <span v-else>{{ projectStore.projects.find((item) => item.id === row.project)?.name || `项目 #${row.project}` }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <StatusTag :status="row.is_active ? 'active' : 'inactive'" :text="row.is_active ? '启用' : '停用'" />
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="290" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" size="small" :loading="testingId === row.id" @click="handleTest(row)">
              测试
            </el-button>
            <el-button
              v-if="!row.is_default"
              link
              type="success"
              size="small"
              :loading="defaultingId === row.id"
              @click="handleSetDefault(row)"
            >
              设为默认
            </el-button>
            <ConfirmButton
              text="删除"
              link
              size="small"
              :title="`删除模型配置「${row.name}」`"
              content="删除后不可恢复，且引用该配置的调用会回退到默认配置，确定删除？"
              @confirm="handleDelete(row)"
            />
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <!-- 新建 / 编辑抽屉 -->
    <el-drawer v-model="drawerVisible" :title="drawerTitle" size="560px" :destroy-on-close="true">
      <el-form label-width="110px" label-position="right" class="drawer-form">
        <el-form-item label="配置范围" required>
          <el-radio-group v-model="form.scope">
            <el-radio value="global">全局配置</el-radio>
            <el-radio value="project" :disabled="!projectStore.currentProjectId">当前项目</el-radio>
          </el-radio-group>
          <div class="field-hint">
            {{ form.scope === 'global'
              ? '全局配置对所有项目生效（需要管理员权限）。'
              : `归属项目：${projectStore.currentProjectName || '未选择'}` }}
          </div>
        </el-form-item>
        <el-form-item label="配置名称" required>
          <el-input v-model="form.name" maxlength="128" placeholder="例如：DeepSeek 文本主模型" />
        </el-form-item>
        <el-form-item label="提供商">
          <el-select v-model="form.provider" class="w-full" @change="handleProviderChange">
            <el-option v-for="item in PROVIDER_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型类型">
          <el-radio-group v-model="form.model_type">
            <el-radio v-for="item in MODEL_TYPE_OPTIONS" :key="item.value" :value="item.value">
              {{ item.label }}
            </el-radio>
          </el-radio-group>
          <div class="field-hint">同一范围 + 模型类型下默认配置唯一。</div>
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="form.model_name" maxlength="128" placeholder="例如：deepseek-chat" />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="form.base_url" maxlength="500" placeholder="https://api.deepseek.com/v1" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            autocomplete="new-password"
            :placeholder="keyPlaceholder"
          />
          <div class="field-hint">
            已保存的 Key 仅以掩码回显，留空保存不会修改原值。
          </div>
        </el-form-item>
        <el-form-item label="temperature">
          <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" :precision="1" />
          <span class="field-hint inline">0~2，越大越随机</span>
        </el-form-item>
        <el-form-item label="max_tokens">
          <el-input-number v-model="form.max_tokens" :min="1" :max="128000" :step="128" />
        </el-form-item>
        <el-form-item label="扩展参数">
          <el-input
            v-model="form.extraText"
            type="textarea"
            :rows="4"
            placeholder='{"top_p": 0.9}'
          />
          <div class="field-hint">JSON 对象，可留空。</div>
        </el-form-item>
        <el-form-item label="默认配置">
          <el-switch v-model="form.is_default" />
          <span class="field-hint inline">同一范围与类型只能有一个默认配置</span>
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

    <!-- 连通性测试结果 -->
    <el-dialog v-model="testResultVisible" title="连通性测试结果" width="520px">
      <template v-if="testResult">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="结果">
            <el-tag :type="testResult.success ? 'success' : 'danger'" effect="light">
              {{ testResult.success ? '连通正常' : '连通失败' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="提供商">{{ testResult.provider || '—' }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ testResult.model || '—' }}</el-descriptions-item>
          <el-descriptions-item label="模式">{{ testResult.mock ? 'Mock（离线确定性）' : '真实调用' }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ formatNumber(testResult.latency_ms) }} ms</el-descriptions-item>
          <el-descriptions-item label="说明">{{ testResult.message || '—' }}</el-descriptions-item>
        </el-descriptions>
      </template>
      <template #footer>
        <el-button type="primary" @click="testResultVisible = false">关闭</el-button>
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
import { useProjectStore } from '@/stores/project'
import { aiCoreApi } from '@/api/aiCore'
import { formatDateTime, formatNumber } from '@/utils/format'

import {
  MODEL_TYPE_OPTIONS,
  PROVIDER_BASE_URLS,
  PROVIDER_OPTIONS,
  apiKeyPlaceholder,
  buildLlmPayload,
  emptyLlmForm,
  llmRecordToForm,
  modelTypeLabel,
  providerLabel,
} from './utils/llm'

const projectStore = useProjectStore()

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const pageError = ref('')

const filters = reactive({
  search: '',
  scope: 'all',
  provider: '',
  model_type: '',
  is_active: '',
})

const drawerVisible = ref(false)
const mode = ref('create')
const currentId = ref(null)
const saving = ref(false)
const form = reactive(emptyLlmForm())
const editingMaskedKey = ref('')

const testingId = ref(null)
const defaultingId = ref(null)
const testResultVisible = ref(false)
const testResult = ref(null)

const drawerTitle = computed(() => (mode.value === 'create' ? '新建模型配置' : '编辑模型配置'))
const keyPlaceholder = computed(() =>
  apiKeyPlaceholder({ isEdit: mode.value === 'edit', masked: editingMaskedKey.value }),
)

function requestParams() {
  const params = { page: page.value, page_size: pageSize.value }
  if (filters.search.trim()) params.search = filters.search.trim()
  if (filters.provider) params.provider = filters.provider
  if (filters.model_type) params.model_type = filters.model_type
  if (filters.is_active !== '') params.is_active = filters.is_active
  if (filters.scope === 'current' && projectStore.currentProjectId) {
    params.project = projectStore.currentProjectId
  }
  return params
}

async function load() {
  loading.value = true
  pageError.value = ''
  try {
    const data = await aiCoreApi.listLlmConfigs(requestParams())
    rows.value = Array.isArray(data?.results) ? data.results : []
    total.value = Number(data?.count ?? rows.value.length)
  } catch (error) {
    rows.value = []
    total.value = 0
    pageError.value = error?.message || '模型配置加载失败'
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

function resetForm(values = {}) {
  Object.assign(form, emptyLlmForm(values))
  editingMaskedKey.value = values.apiKeyMasked || ''
}

function openCreate() {
  mode.value = 'create'
  currentId.value = null
  resetForm({
    scope: projectStore.currentProjectId ? 'project' : 'global',
    project: projectStore.currentProjectId || null,
    provider: 'mock',
  })
  drawerVisible.value = true
}

function openEdit(row) {
  mode.value = 'edit'
  currentId.value = row.id
  const values = llmRecordToForm(row)
  resetForm(values)
  drawerVisible.value = true
}

function handleProviderChange(provider) {
  if (!form.base_url && PROVIDER_BASE_URLS[provider]) {
    form.base_url = PROVIDER_BASE_URLS[provider]
  }
}

async function handleSave() {
  const { payload, error } = buildLlmPayload(form)
  if (error) {
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
      await aiCoreApi.createLlmConfig(payload)
      ElMessage.success('模型配置已创建')
    } else {
      await aiCoreApi.updateLlmConfig(currentId.value, payload)
      ElMessage.success('模型配置已更新')
    }
    drawerVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(error?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleTest(row) {
  testingId.value = row.id
  try {
    const data = await aiCoreApi.testLlmConfig(row.id)
    testResult.value = data
    testResultVisible.value = true
  } catch (error) {
    ElMessage.error(error?.message || '连通性测试失败')
  } finally {
    testingId.value = null
  }
}

async function handleSetDefault(row) {
  defaultingId.value = row.id
  try {
    await aiCoreApi.setDefaultLlmConfig(row.id)
    ElMessage.success(`已将「${row.name}」设为默认配置`)
    await load()
  } catch (error) {
    ElMessage.error(error?.message || '设置默认失败')
  } finally {
    defaultingId.value = null
  }
}

async function handleDelete(row) {
  try {
    await aiCoreApi.removeLlmConfig(row.id)
    ElMessage.success('已删除')
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (error) {
    ElMessage.error(error?.message || '删除失败')
  }
}

onMounted(async () => {
  if (!projectStore.loaded) {
    try {
      await projectStore.fetchProjects()
    } catch (error) {
      // 项目列表失败不影响全局配置管理
    }
  }
  await load()
})
</script>

<style scoped>
.models {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.name-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.w-full {
  width: 100%;
}

.drawer-form {
  padding-right: 8px;
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

.field-hint.inline {
  width: auto;
  margin: 0 0 0 10px;
}
</style>
