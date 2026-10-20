<template>
  <div class="configs-pane">
    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
      description="负载配置加载失败，请稍后重试或检查后端服务。"
    />

    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="filters.search"
            class="filter-input"
            placeholder="搜索配置名称 / 描述 / Host"
            :prefix-icon="Search"
            clearable
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
          <el-button :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </div>
        <div class="toolbar__right">
          <span class="text-small text-muted">共 {{ pagination.total }} 个负载配置</span>
          <el-button :icon="Refresh" :loading="loading" @click="loadConfigs">刷新</el-button>
          <el-button type="primary" :icon="Plus" @click="openCreate">新建配置</el-button>
        </div>
      </div>

      <DataTable
        v-model:page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :data="configs"
        :loading="loading"
        :total="pagination.total"
        row-key="id"
        empty-text="暂无负载配置"
        @change="loadConfigs"
      >
        <el-table-column label="配置名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" underline="never" @click="openEdit(row)">
              {{ row.name }}
            </el-link>
            <div v-if="row.description" class="config-desc">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="并发用户" width="100" align="right">
          <template #default="{ row }">{{ formatNumber(row.users) }}</template>
        </el-table-column>
        <el-table-column label="加压速率" width="110" align="right">
          <template #default="{ row }">{{ formatNumber(row.spawn_rate, 1) }} u/s</template>
        </el-table-column>
        <el-table-column label="持续时间" width="110" align="right">
          <template #default="{ row }">{{ formatNumber(row.duration_seconds) }} s</template>
        </el-table-column>
        <el-table-column label="目标 Host" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.host || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="扩展配置" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="configKeyCount(row.config)" size="small" effect="plain" type="info">
              {{ configKeyCount(row.config) }} 项
            </el-tag>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="160">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <ConfirmButton
              link
              type="danger"
              text="删除"
              :content="`确定删除负载配置「${row.name}」吗？已关联的场景会保留，但会失去预设负载参数。`"
              :loading="deletingId === row.id"
              @confirm="handleDelete(row)"
            />
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            title="暂无负载配置"
            description="负载配置定义并发用户、加压速率与持续时间，可被多个压测场景复用。"
          >
            <el-button type="primary" :icon="Plus" @click="openCreate">新建配置</el-button>
          </EmptyState>
        </template>
      </DataTable>
    </div>

    <!-- 新建 / 编辑负载配置 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新建负载配置' : '编辑负载配置'"
      width="700px"
      :close-on-click-modal="false"
      @closed="handleDialogClosed"
    >
      <el-alert
        v-if="formError"
        :title="formError"
        type="error"
        show-icon
        :closable="false"
        class="mb-16"
      />
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="104px"
        @submit.prevent
      >
        <el-form-item label="配置名称" prop="name">
          <el-input
            v-model="form.name"
            maxlength="255"
            show-word-limit
            placeholder="例如：基线 50 并发"
          />
        </el-form-item>
        <div class="form-grid">
          <el-form-item label="并发用户数" prop="users">
            <el-input-number v-model="form.users" :min="1" :step="1" :precision="0" style="width: 100%" />
          </el-form-item>
          <el-form-item label="加压速率" prop="spawn_rate">
            <el-input-number
              v-model="form.spawn_rate"
              :min="0.1"
              :step="1"
              :precision="1"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="持续时间" prop="duration_seconds">
            <el-input-number
              v-model="form.duration_seconds"
              :min="1"
              :step="10"
              :precision="0"
              style="width: 100%"
            />
            <span class="field-suffix">秒</span>
          </el-form-item>
          <el-form-item label="目标 Host" prop="host">
            <el-input v-model="form.host" placeholder="https://demo.example.com" />
          </el-form-item>
        </div>
        <el-form-item label="扩展配置" prop="configText">
          <el-input
            v-model="form.configText"
            type="textarea"
            :rows="6"
            class="mono-input"
            placeholder='可覆盖 users / spawn_rate / duration_seconds / host，例如 {"users": 100}'
          />
          <div class="field-help">
            <span>必须是 JSON 对象；留空表示使用上方字段。</span>
            <el-button link type="primary" size="small" @click="handleFormatJson">格式化 JSON</el-button>
          </div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="2"
            maxlength="500"
            show-word-limit
            placeholder="配置用途、适用环境等"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          保存配置
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Refresh, RefreshLeft, Search } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmButton from '@/components/ConfirmButton.vue'

import { performanceApi } from '@/api/performance'
import { formatDateTime, formatNumber } from '@/utils/format'
import {
  formatJsonText,
  isValidHttpUrl,
  loadConfigToForm,
  readErrorMessage,
  validateJsonObject,
  validateLoadConfig,
} from './utils'

const props = defineProps({
  projectId: { type: [Number, String], default: null },
  refreshKey: { type: Number, default: 0 },
})

const emit = defineEmits(['changed'])

const configs = ref([])
const loading = ref(false)
const errorMessage = ref('')
const filters = reactive({ search: '' })
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

const dialogVisible = ref(false)
const dialogMode = ref('create')
const editingId = ref(null)
const formRef = ref(null)
const form = reactive(createEmptyForm())
const submitting = ref(false)
const formError = ref('')
const deletingId = ref(null)

function createEmptyForm() {
  return {
    name: '',
    users: 10,
    spawn_rate: 5,
    duration_seconds: 60,
    host: '',
    configText: '{}',
    description: '',
  }
}

function positiveIntegerRule(label) {
  return (rule, value, callback) => {
    const number = Number(value)
    if (!Number.isFinite(number) || !Number.isInteger(number) || number <= 0) {
      callback(new Error(`${label}必须为正整数`))
      return
    }
    callback()
  }
}

const rules = {
  name: [{ required: true, message: '请输入配置名称', trigger: 'blur' }],
  users: [{ validator: positiveIntegerRule('并发用户数'), trigger: 'change' }],
  spawn_rate: [
    {
      validator: (rule, value, callback) => {
        const number = Number(value)
        if (!Number.isFinite(number) || number <= 0) {
          callback(new Error('并发增长率必须大于 0'))
          return
        }
        callback()
      },
      trigger: 'change',
    },
  ],
  duration_seconds: [{ validator: positiveIntegerRule('持续时间'), trigger: 'change' }],
  host: [
    {
      validator: (rule, value, callback) => {
        const raw = String(value || '').trim()
        if (raw && !isValidHttpUrl(raw)) {
          callback(new Error('目标 Host 必须是 http(s):// 开头的完整地址'))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
  configText: [
    {
      validator: (rule, value, callback) => {
        const result = validateJsonObject(value, { label: '扩展配置' })
        if (!result.valid) {
          callback(new Error(result.message))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
}

function configKeyCount(config) {
  return config && typeof config === 'object' && !Array.isArray(config)
    ? Object.keys(config).length
    : 0
}

async function loadConfigs() {
  if (!props.projectId) {
    configs.value = []
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
    const data = await performanceApi.listConfigs(params)
    configs.value = Array.isArray(data?.results) ? data.results : []
    pagination.total = Number(data?.count ?? configs.value.length)
  } catch (error) {
    configs.value = []
    pagination.total = 0
    errorMessage.value = readErrorMessage(error, '负载配置加载失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadConfigs()
}

function handleReset() {
  filters.search = ''
  pagination.page = 1
  loadConfigs()
}

function resetForm() {
  Object.assign(form, createEmptyForm())
  editingId.value = null
  formError.value = ''
}

function openCreate() {
  dialogMode.value = 'create'
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  dialogMode.value = 'edit'
  editingId.value = row.id
  formError.value = ''
  Object.assign(form, loadConfigToForm(row))
  dialogVisible.value = true
}

function handleDialogClosed() {
  formRef.value?.clearValidate()
  formError.value = ''
}

function handleFormatJson() {
  const result = formatJsonText(form.configText)
  if (!result.ok) {
    formError.value = result.message
    return
  }
  form.configText = result.text || '{}'
  formError.value = ''
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  const result = validateLoadConfig(form)
  if (!result.valid) {
    formError.value = result.errors[0]
    return
  }
  submitting.value = true
  formError.value = ''
  try {
    if (dialogMode.value === 'edit' && editingId.value) {
      await performanceApi.updateConfig(editingId.value, result.payload)
      ElMessage.success('负载配置已更新')
    } else {
      await performanceApi.createConfig({ project: props.projectId, ...result.payload })
      ElMessage.success('负载配置已创建')
    }
    dialogVisible.value = false
    await loadConfigs()
    emit('changed')
  } catch (error) {
    formError.value = readErrorMessage(error, '负载配置保存失败')
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row) {
  deletingId.value = row.id
  try {
    await performanceApi.removeConfig(row.id)
    ElMessage.success(`已删除负载配置「${row.name}」`)
    if (configs.value.length === 1 && pagination.page > 1) pagination.page -= 1
    await loadConfigs()
    emit('changed')
  } catch (error) {
    ElMessage.error(readErrorMessage(error, '删除负载配置失败'))
  } finally {
    deletingId.value = null
  }
}

watch(() => props.projectId, () => {
  pagination.page = 1
  loadConfigs()
})
watch(() => props.refreshKey, loadConfigs)

onMounted(loadConfigs)
</script>

<style scoped>
.configs-pane {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.config-desc {
  margin-top: 2px;
  font-size: 12px;
  color: var(--aits-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 18px;
}

.field-suffix {
  margin-left: 8px;
  font-size: 12px;
  color: var(--aits-text-secondary);
}

.field-help {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 12px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--aits-text-secondary);
}

.mono-input :deep(textarea) {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12.5px;
}

@media (max-width: 900px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
