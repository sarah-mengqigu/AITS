<template>
  <div class="suites-pane">
    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
    />

    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="filters.search"
            class="filter-input"
            placeholder="搜索套件名称 / 描述"
            :prefix-icon="Search"
            clearable
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
          <el-button :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </div>
        <div class="toolbar__right">
          <span class="text-small text-muted">共 {{ pagination.total }} 个套件</span>
          <el-button :icon="Refresh" :loading="loading" @click="loadSuites">刷新</el-button>
          <el-button type="primary" :icon="Plus" @click="openCreate">新建套件</el-button>
        </div>
      </div>

      <DataTable
        v-model:page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :data="suites"
        :loading="loading"
        :total="pagination.total"
        row-key="id"
        empty-text="暂无测试套件"
        @change="loadSuites"
      >
        <el-table-column label="套件名称" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" :underline="false" @click="openEdit(row)">
              {{ row.name }}
            </el-link>
            <div v-if="row.description" class="suite-desc">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="用例数" width="86" align="center">
          <template #default="{ row }">{{ row.case_count ?? (row.case_ids?.length || 0) }}</template>
        </el-table-column>
        <el-table-column label="执行环境" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.environment_name || '项目默认环境' }}</template>
        </el-table-column>
        <el-table-column label="来源" width="100">
          <template #default="{ row }">{{ getSourceLabel(row.source) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="86">
          <template #default="{ row }">
            <StatusTag :status="row.is_active ? 'active' : 'inactive'" />
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openRun(row)">运行</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <ConfirmButton
              link
              type="danger"
              text="删除"
              :content="`确定删除套件「${row.name}」吗？套件下的执行记录会保留。`"
              :loading="deletingId === row.id"
              @confirm="handleDelete(row)"
            />
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            title="暂无测试套件"
            description="把多条用例组合成套件后可批量执行，并实时查看执行进度与通过率。"
          >
            <el-button type="primary" :icon="Plus" @click="openCreate">新建套件</el-button>
            <el-button @click="emit('switch-tab', 'cases')">去用例管理</el-button>
          </EmptyState>
        </template>
      </DataTable>
    </div>

    <!-- 新建 / 编辑套件 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新建测试套件' : '编辑测试套件'"
      width="820px"
      :close-on-click-modal="false"
      @closed="handleDialogClosed"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="92px" @submit.prevent>
        <div class="form-grid">
          <el-form-item label="套件名称" prop="name" class="form-grid__full">
            <el-input v-model="form.name" maxlength="255" show-word-limit placeholder="例如：核心链路冒烟套件" />
          </el-form-item>
          <el-form-item label="执行环境">
            <el-select
              v-model="form.environment"
              style="width: 100%"
              clearable
              filterable
              :loading="envLoading"
              placeholder="默认使用项目默认环境"
            >
              <el-option
                v-for="env in envOptions"
                :key="env.id"
                :label="`${env.name}${env.is_default ? '（默认）' : ''}`"
                :value="env.id"
              />
            </el-select>
            <div v-if="envError" class="text-small env-error">{{ envError }}</div>
          </el-form-item>
          <el-form-item label="启用状态">
            <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
          </el-form-item>
          <el-form-item label="套件描述" class="form-grid__full">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="2"
              maxlength="500"
              show-word-limit
              placeholder="套件用途、执行范围等"
            />
          </el-form-item>
          <el-form-item label="选择用例" prop="case_ids" class="form-grid__full">
            <div v-loading="caseLoading" class="transfer-wrap">
              <el-transfer
                v-model="form.case_ids"
                :data="transferData"
                :props="{ key: 'id', label: 'label' }"
                :titles="['可选用例', '已选用例']"
                filterable
                filter-placeholder="搜索用例名称"
                :button-texts="['移除', '添加']"
              />
              <p class="text-small text-muted">
                已加载 {{ caseOptions.length }} / {{ caseTotal }} 条用例（单次最多 200 条）；
                可通过「用例管理」筛选后再回来选择。
              </p>
            </div>
          </el-form-item>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">保存套件</el-button>
      </template>
    </el-dialog>

    <!-- 运行套件 -->
    <el-dialog v-model="runDialogVisible" title="运行测试套件" width="480px" :close-on-click-modal="false">
      <div v-if="runTarget">
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="套件">{{ runTarget.name }}</el-descriptions-item>
          <el-descriptions-item label="用例数">
            {{ runTarget.case_count ?? (runTarget.case_ids?.length || 0) }}
          </el-descriptions-item>
        </el-descriptions>
        <el-form label-width="82px" class="mt-16" @submit.prevent>
          <el-form-item label="执行环境">
            <el-select
              v-model="runEnvironment"
              style="width: 100%"
              clearable
              filterable
              :loading="envLoading"
              placeholder="默认使用套件 / 项目默认环境"
            >
              <el-option
                v-for="env in envOptions"
                :key="env.id"
                :label="`${env.name}${env.is_default ? '（默认）' : ''}`"
                :value="env.id"
              />
            </el-select>
          </el-form-item>
        </el-form>
        <p class="text-small text-muted">
          执行会创建一条执行记录，并优先通过 WebSocket 推送实时进度；连接不可用时自动降级为轮询。
        </p>
      </div>
      <template #footer>
        <el-button @click="runDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="runSubmitting" @click="confirmRun">开始运行</el-button>
      </template>
    </el-dialog>

    <ExecutionProgressDialog
      v-model="progressVisible"
      :execution-id="progressExecutionId"
      :title="progressTitle"
      @finished="handleProgressFinished"
      @open-detail="handleOpenProgressDetail"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Refresh, RefreshLeft, Search } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import EmptyState from '@/components/EmptyState.vue'
import StatusTag from '@/components/StatusTag.vue'
import ConfirmButton from '@/components/ConfirmButton.vue'
import ExecutionProgressDialog from './components/ExecutionProgressDialog.vue'

import { apiTestingApi } from '@/api/apiTesting'
import { projectsApi } from '@/api/projects'
import { formatDateTime } from '@/utils/format'
import { getSourceLabel, getTestTypeLabel } from './utils'

const props = defineProps({
  projectId: { type: [Number, String], default: null },
  refreshKey: { type: Number, default: 0 },
})

const emit = defineEmits(['execution-created', 'open-execution', 'changed', 'switch-tab'])

const suites = ref([])
const loading = ref(false)
const errorMessage = ref('')
const deletingId = ref(null)
const filters = reactive({ search: '' })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

const dialogVisible = ref(false)
const dialogMode = ref('create')
const submitting = ref(false)
const formRef = ref(null)
const editingSuite = ref(null)

const envOptions = ref([])
const envLoading = ref(false)
const envError = ref('')
const caseOptions = ref([])
const caseTotal = ref(0)
const caseLoading = ref(false)

const runDialogVisible = ref(false)
const runTarget = ref(null)
const runEnvironment = ref(null)
const runSubmitting = ref(false)

const progressVisible = ref(false)
const progressExecutionId = ref(null)
const progressTitle = ref('套件运行')

const form = reactive({
  name: '',
  description: '',
  environment: null,
  case_ids: [],
  source: 'manual',
  is_active: true,
})

const rules = {
  name: [{ required: true, message: '请输入套件名称', trigger: 'blur' }],
  case_ids: [
    {
      validator(rule, value, callback) {
        if (!Array.isArray(value) || !value.length) {
          return callback(new Error('请至少选择一个用例'))
        }
        return callback()
      },
      trigger: 'change',
    },
  ],
}

const transferData = computed(() =>
  caseOptions.value.map((item) => ({
    id: item.id,
    label: `${item.name}（${getTestTypeLabel(item.test_type)}）`,
    disabled: item.is_active === false,
  })),
)

function buildParams() {
  const params = {
    project: props.projectId,
    page: pagination.page,
    page_size: pagination.pageSize,
  }
  if (filters.search.trim()) params.search = filters.search.trim()
  return params
}

async function loadSuites() {
  if (!props.projectId) {
    suites.value = []
    pagination.total = 0
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await apiTestingApi.listSuites(buildParams())
    suites.value = Array.isArray(data?.results) ? data.results : []
    pagination.total = Number(data?.count ?? suites.value.length)
  } catch (error) {
    suites.value = []
    pagination.total = 0
    errorMessage.value = error?.message || '测试套件加载失败'
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadSuites()
}

function handleReset() {
  filters.search = ''
  pagination.page = 1
  loadSuites()
}

async function loadEnvOptions() {
  if (!props.projectId) return
  envLoading.value = true
  envError.value = ''
  try {
    const data = await projectsApi.listEnvironments({
      project: props.projectId,
      page_size: 100,
    })
    envOptions.value = Array.isArray(data?.results) ? data.results : []
    if (!envOptions.value.length) envError.value = '当前项目暂无环境配置，将使用项目默认环境执行'
  } catch (error) {
    envOptions.value = []
    envError.value = error?.message || '环境列表加载失败'
  } finally {
    envLoading.value = false
  }
}

async function loadCaseOptions() {
  if (!props.projectId) return
  caseLoading.value = true
  try {
    const data = await apiTestingApi.listCases({ project: props.projectId, page_size: 200 })
    caseOptions.value = Array.isArray(data?.results) ? data.results : []
    caseTotal.value = Number(data?.count ?? caseOptions.value.length)
  } catch (error) {
    caseOptions.value = []
    caseTotal.value = 0
    ElMessage.error(error?.message || '用例列表加载失败')
  } finally {
    caseLoading.value = false
  }
}

function resetForm() {
  form.name = ''
  form.description = ''
  form.environment = null
  form.case_ids = []
  form.source = 'manual'
  form.is_active = true
  envError.value = ''
}

function openCreate() {
  dialogMode.value = 'create'
  editingSuite.value = null
  resetForm()
  dialogVisible.value = true
  loadEnvOptions()
  loadCaseOptions()
  nextTick(() => formRef.value?.clearValidate())
}

function openEdit(row) {
  dialogMode.value = 'edit'
  editingSuite.value = row
  resetForm()
  form.name = row.name || ''
  form.description = row.description || ''
  form.environment = row.environment ?? null
  form.case_ids = Array.isArray(row.case_ids) ? [...row.case_ids] : []
  form.source = row.source || 'manual'
  form.is_active = row.is_active !== false
  dialogVisible.value = true
  loadEnvOptions()
  loadCaseOptions()
  nextTick(() => formRef.value?.clearValidate())
}

function handleDialogClosed() {
  editingSuite.value = null
  envError.value = ''
}

async function handleSubmit() {
  if (!props.projectId) {
    ElMessage.warning('请先选择项目')
    return
  }
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  const payload = {
    project: props.projectId,
    name: form.name.trim(),
    description: form.description,
    environment: form.environment || null,
    case_ids: form.case_ids,
    source: editingSuite.value?.source || form.source || 'manual',
    is_active: form.is_active,
    config: editingSuite.value?.config || {},
  }
  submitting.value = true
  try {
    if (dialogMode.value === 'edit' && editingSuite.value?.id) {
      await apiTestingApi.updateSuite(editingSuite.value.id, payload)
      ElMessage.success('套件已保存')
    } else {
      await apiTestingApi.createSuite(payload)
      ElMessage.success('套件已创建')
    }
    dialogVisible.value = false
    await loadSuites()
    emit('changed')
  } catch (error) {
    ElMessage.error(error?.message || '套件保存失败')
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row) {
  deletingId.value = row.id
  try {
    await apiTestingApi.removeSuite(row.id)
    ElMessage.success('套件已删除')
    if (suites.value.length === 1 && pagination.page > 1) pagination.page -= 1
    await loadSuites()
    emit('changed')
  } catch (error) {
    ElMessage.error(error?.message || '删除套件失败')
  } finally {
    deletingId.value = null
  }
}

function openRun(row) {
  runTarget.value = row
  const defaultEnv =
    envOptions.value.find((env) => env.is_default)?.id ||
    row.environment ||
    null
  runEnvironment.value = defaultEnv
  runDialogVisible.value = true
  loadEnvOptions()
}

async function confirmRun() {
  if (!runTarget.value) return
  runSubmitting.value = true
  try {
    const payload = runEnvironment.value ? { environment: runEnvironment.value } : {}
    const data = await apiTestingApi.runSuite(runTarget.value.id, payload)
    const executionId = data?.execution_id || data?.task_id
    if (!executionId) throw new Error('后端未返回执行 ID')
    runDialogVisible.value = false
    progressExecutionId.value = executionId
    progressTitle.value = `套件运行 · ${runTarget.value.name}`
    progressVisible.value = true
    ElMessage.success('套件已开始执行，正在跟踪进度')
    emit('execution-created')
  } catch (error) {
    ElMessage.error(error?.message || '套件运行失败')
  } finally {
    runSubmitting.value = false
  }
}

function handleProgressFinished() {
  emit('execution-created')
}

function handleOpenProgressDetail(executionId) {
  progressVisible.value = false
  if (executionId) emit('open-execution', executionId)
}

watch(
  () => props.projectId,
  () => {
    pagination.page = 1
    loadSuites()
    loadEnvOptions()
  },
)

watch(
  () => props.refreshKey,
  () => loadSuites(),
)

onMounted(() => {
  loadSuites()
  loadEnvOptions()
})
</script>

<style scoped>
.suites-pane {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.suite-desc {
  margin-top: 3px;
  font-size: 12px;
  color: var(--aits-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 18px;
}

.form-grid__full {
  grid-column: 1 / -1;
}

.transfer-wrap {
  width: 100%;
}

.transfer-wrap :deep(.el-transfer) {
  display: flex;
  align-items: center;
  justify-content: center;
}

.env-error {
  margin-top: 4px;
  color: #d97706;
}

.mt-16 {
  margin-top: 16px;
}
</style>
