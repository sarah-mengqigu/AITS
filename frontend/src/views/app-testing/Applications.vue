<template>
  <div class="tab-panel">
    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="filters.search"
            class="filter-input"
            placeholder="搜索应用名称 / 包名 / Bundle ID"
            :prefix-icon="Search"
            clearable
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
          <el-select
            v-model="filters.platform"
            class="filter-select"
            placeholder="平台"
            clearable
            @change="handleSearch"
          >
            <el-option
              v-for="option in PLATFORM_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-button :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </div>
        <div class="toolbar__right">
          <span class="text-small text-muted">共 {{ pagination.total }} 个应用</span>
          <el-button type="primary" :icon="Plus" @click="openCreate">新建应用</el-button>
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
        :data="applications"
        :loading="loading"
        :total="pagination.total"
        row-key="id"
        empty-text="暂无应用，点击「新建应用」录入被测 App"
        @change="loadApplications"
      >
        <el-table-column prop="name" label="应用名称" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" :underline="false" @click="openEdit(row)">{{ row.name }}</el-link>
            <div v-if="row.description" class="row-desc">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="平台" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="PLATFORM_TAG_TYPE[row.platform] || 'info'" effect="light">
              {{ getPlatformText(row.platform) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="包名 / Bundle ID" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ applicationIdentifier(row) || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="版本" width="110">
          <template #default="{ row }">{{ row.app_version || '—' }}</template>
        </el-table-column>
        <el-table-column label="用例数" width="90" align="center">
          <template #default="{ row }">{{ row.case_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <ConfirmButton
              link
              type="danger"
              text="删除"
              :content="`确定删除应用「${row.name}」吗？关联用例将解除绑定。`"
              :loading="deletingId === row.id"
              @confirm="handleDelete(row)"
            />
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="form.id ? '编辑应用' : '新建应用'"
      width="600px"
      :close-on-click-modal="false"
      @closed="handleDialogClosed"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="112px">
        <el-form-item label="应用名称" prop="name">
          <el-input v-model="form.name" maxlength="128" show-word-limit placeholder="例如：AITS App" />
        </el-form-item>
        <el-form-item label="所属平台" prop="platform">
          <el-radio-group v-model="form.platform" @change="handlePlatformChange">
            <el-radio-button
              v-for="option in PLATFORM_OPTIONS"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item
          v-if="form.platform === 'android'"
          label="包名"
          prop="package_name"
          :error="fieldErrors.package_name"
        >
          <el-input v-model="form.package_name" class="mono" placeholder="com.example.app（必填）" />
          <div class="field-hint">{{ platformFieldHint('android') }}</div>
        </el-form-item>

        <el-form-item
          v-if="form.platform === 'ios'"
          label="Bundle ID"
          prop="bundle_id"
          :error="fieldErrors.bundle_id"
        >
          <el-input v-model="form.bundle_id" class="mono" placeholder="com.example.app（必填）" />
          <div class="field-hint">{{ platformFieldHint('ios') }}</div>
        </el-form-item>

        <el-form-item label="应用版本" prop="app_version">
          <el-input v-model="form.app_version" placeholder="例如：2.0.0" />
        </el-form-item>
        <el-form-item label="应用描述" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="被测 App 说明、环境要求等"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, RefreshLeft, Search } from '@element-plus/icons-vue'

import ConfirmButton from '@/components/ConfirmButton.vue'
import DataTable from '@/components/DataTable.vue'

import { appTestingApi } from '@/api/appTesting'
import { formatDateTime } from '@/utils/format'
import {
  PLATFORM_OPTIONS,
  PLATFORM_TAG_TYPE,
  applicationIdentifier,
  buildApplicationPayload,
  getPlatformText,
  normalizeListPayload,
  platformFieldHint,
  validateApplicationForm,
} from './utils'

const props = defineProps({
  projectId: { type: Number, default: null },
})

const filters = reactive({ search: '', platform: '' })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

const applications = ref([])
const loading = ref(false)
const errorMessage = ref('')
const deletingId = ref(null)

const dialogVisible = ref(false)
const saving = ref(false)
const formRef = ref(null)
const form = reactive({
  id: null,
  name: '',
  platform: 'android',
  package_name: '',
  bundle_id: '',
  app_version: '',
  description: '',
})
const fieldErrors = reactive({ package_name: '', bundle_id: '', platform: '' })

const rules = computed(() => ({
  name: [{ required: true, message: '请输入应用名称', trigger: 'blur' }],
  platform: [{ required: true, message: '请选择平台', trigger: 'change' }],
  package_name:
    form.platform === 'android'
      ? [{ required: true, message: 'Android 应用必须填写包名', trigger: 'blur' }]
      : [],
  bundle_id:
    form.platform === 'ios'
      ? [{ required: true, message: 'iOS 应用必须填写 Bundle ID', trigger: 'blur' }]
      : [],
}))

async function loadApplications() {
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
    if (filters.search.trim()) params.search = filters.search.trim()
    if (filters.platform) params.platform = filters.platform
    const data = await appTestingApi.listApplications(params)
    const { results, count } = normalizeListPayload(data)
    applications.value = results
    pagination.total = count
  } catch (error) {
    applications.value = []
    pagination.total = 0
    errorMessage.value = error?.message || '应用列表加载失败'
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadApplications()
}

function handleReset() {
  filters.search = ''
  filters.platform = ''
  pagination.page = 1
  loadApplications()
}

function clearFieldErrors() {
  fieldErrors.package_name = ''
  fieldErrors.bundle_id = ''
  fieldErrors.platform = ''
}

function openCreate() {
  form.id = null
  form.name = ''
  form.platform = 'android'
  form.package_name = ''
  form.bundle_id = ''
  form.app_version = ''
  form.description = ''
  clearFieldErrors()
  dialogVisible.value = true
  formRef.value?.clearValidate?.()
}

function openEdit(row) {
  form.id = row.id
  form.name = row.name || ''
  form.platform = row.platform || 'android'
  form.package_name = row.package_name || ''
  form.bundle_id = row.bundle_id || ''
  form.app_version = row.app_version || ''
  form.description = row.description || ''
  clearFieldErrors()
  dialogVisible.value = true
  formRef.value?.clearValidate?.()
}

function handlePlatformChange(platform) {
  // 平台切换时校验对应字段：清空另一平台的标识，避免脏数据提交
  if (platform === 'android') form.bundle_id = ''
  else form.package_name = ''
  clearFieldErrors()
  formRef.value?.clearValidate?.(['package_name', 'bundle_id'])
}

function handleDialogClosed() {
  formRef.value?.clearValidate?.()
  clearFieldErrors()
}

async function handleSubmit() {
  const result = validateApplicationForm(form)
  clearFieldErrors()
  Object.entries(result.errors).forEach(([field, message]) => {
    if (field in fieldErrors) fieldErrors[field] = message
  })
  if (formRef.value) {
    try {
      await formRef.value.validate()
    } catch {
      return
    }
  }
  if (!result.valid) {
    ElMessage.error(Object.values(result.errors)[0] || '请检查表单填写')
    return
  }
  saving.value = true
  try {
    const payload = { project: props.projectId, ...buildApplicationPayload(form) }
    if (form.id) {
      await appTestingApi.updateApplication(form.id, payload)
      ElMessage.success('应用已更新')
    } else {
      await appTestingApi.createApplication(payload)
      ElMessage.success('应用已创建')
    }
    dialogVisible.value = false
    await loadApplications()
  } catch (error) {
    const message = error?.message || '保存应用失败'
    if (/package_name|包名/i.test(message)) fieldErrors.package_name = message
    if (/bundle_id|Bundle/i.test(message)) fieldErrors.bundle_id = message
    ElMessage.error(message)
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  deletingId.value = row.id
  try {
    await appTestingApi.removeApplication(row.id)
    ElMessage.success('应用已删除')
    if (applications.value.length === 1 && pagination.page > 1) pagination.page -= 1
    await loadApplications()
  } catch (error) {
    ElMessage.error(error?.message || '删除应用失败')
  } finally {
    deletingId.value = null
  }
}

watch(
  () => props.projectId,
  () => {
    pagination.page = 1
    loadApplications()
  },
)

onMounted(loadApplications)
</script>

<style scoped>
.row-desc {
  margin-top: 2px;
  overflow: hidden;
  color: #94a3b8;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.field-hint {
  margin-top: 4px;
  color: var(--aits-text-secondary);
  font-size: 12px;
  line-height: 1.4;
}
</style>
