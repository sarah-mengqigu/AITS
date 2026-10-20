<template>
  <div class="tab-panel">
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
          <el-select
            v-model="filters.browser"
            class="filter-select"
            placeholder="浏览器"
            clearable
            @change="handleSearch"
          >
            <el-option
              v-for="option in BROWSER_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-button :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </div>
        <div class="toolbar__right">
          <span class="text-small text-muted">共 {{ pagination.total }} 个套件</span>
          <el-button type="primary" :icon="Plus" @click="openCreate">新建套件</el-button>
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
        :data="suites"
        :loading="loading"
        :total="pagination.total"
        row-key="id"
        empty-text="暂无套件，点击「新建套件」开始"
        @change="loadSuites"
      >
        <el-table-column prop="name" label="套件名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" underline="never" @click="openEdit(row)">{{ row.name }}</el-link>
            <div v-if="row.description" class="row-desc">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="用例数" width="90" align="center">
          <template #default="{ row }">{{ row.case_count ?? (row.case_ids || []).length }}</template>
        </el-table-column>
        <el-table-column label="浏览器" width="110">
          <template #default="{ row }">{{ BROWSER_TEXT[row.browser] || row.browser || '—' }}</template>
        </el-table-column>
        <el-table-column label="无头模式" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.headless ? 'success' : 'info'" effect="light">
              {{ row.headless ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="执行环境" width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.environment_name || '未指定' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <StatusTag :status="row.is_active ? 'active' : 'inactive'" />
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              :disabled="!row.is_active"
              :loading="runningId === row.id"
              @click="openRun(row)"
            >
              运行
            </el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <ConfirmButton
              link
              type="danger"
              text="删除"
              :content="`确定删除套件「${row.name}」吗？`"
              :loading="deletingId === row.id"
              @confirm="handleDelete(row)"
            />
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="form.id ? '编辑套件' : '新建套件'"
      width="680px"
      :close-on-click-modal="false"
      @closed="handleDialogClosed"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
        <el-form-item label="套件名称" prop="name">
          <el-input v-model="form.name" maxlength="255" show-word-limit placeholder="例如：核心流程回归" />
        </el-form-item>
        <el-form-item label="套件描述">
          <el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" show-word-limit />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="浏览器" prop="browser">
              <el-select v-model="form.browser" style="width: 100%">
                <el-option
                  v-for="option in BROWSER_OPTIONS"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="无头模式">
              <el-switch v-model="form.headless" active-text="无头" inactive-text="有界面" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="执行环境">
              <el-select
                v-model="form.environment"
                clearable
                filterable
                placeholder="未指定"
                style="width: 100%"
                :loading="environmentsLoading"
              >
                <el-option
                  v-for="env in environments"
                  :key="env.id"
                  :label="`${env.name}${env.base_url ? `（${env.base_url}）` : ''}`"
                  :value="env.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="启用状态">
              <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="包含用例" prop="case_ids">
          <el-select
            v-model="form.case_ids"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            placeholder="选择要执行的用例（可多选）"
            style="width: 100%"
            :loading="casesLoading"
          >
            <el-option
              v-for="item in caseOptions"
              :key="item.id"
              :label="`${item.name}${item.module_name ? ` · ${item.module_name}` : ''}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="执行配置">
          <el-input
            v-model="form.configText"
            type="textarea"
            :rows="3"
            class="mono"
            placeholder='JSON 对象，例如 {"timeout": 30000}'
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="runDialog.visible" title="运行套件" width="520px" :close-on-click-modal="false">
      <el-form label-width="96px">
        <el-form-item label="套件">
          <span>{{ runDialog.suiteName || '—' }}</span>
        </el-form-item>
        <el-form-item label="执行环境">
          <el-select
            v-model="runDialog.environment"
            clearable
            placeholder="使用套件默认环境"
            style="width: 100%"
          >
            <el-option
              v-for="env in environments"
              :key="env.id"
              :label="env.name"
              :value="env.id"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <template v-if="runDialog.submitted">
        <el-divider content-position="left">执行进度</el-divider>
        <el-progress
          :percentage="getProgressPercent(runDialog)"
          :status="progressStatus"
          :stroke-width="14"
        />
        <p class="run-progress__text">
          <StatusTag :status="runDialog.status || 'pending'" />
          <span class="text-small text-muted">{{ runDialog.message || '正在执行，请稍候…' }}</span>
        </p>
      </template>

      <template #footer>
        <el-button @click="runDialog.visible = false">关闭</el-button>
        <el-button
          type="primary"
          :loading="runDialog.loading"
          :disabled="runDialog.submitted && !isTerminalStatus(runDialog.status)"
          @click="submittedRun"
        >
          {{ runDialog.submitted ? '重新运行' : '开始运行' }}
        </el-button>
        <el-button
          v-if="runDialog.submitted && isTerminalStatus(runDialog.status)"
          @click="goExecutions"
        >
          查看执行记录
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, RefreshLeft, Search } from '@element-plus/icons-vue'

import ConfirmButton from '@/components/ConfirmButton.vue'
import DataTable from '@/components/DataTable.vue'
import StatusTag from '@/components/StatusTag.vue'

import { webTestingApi } from '@/api/webTesting'
import { projectsApi } from '@/api/projects'
import { formatDateTime } from '@/utils/format'
import {
  BROWSER_OPTIONS,
  BROWSER_TEXT,
  getProgressPercent,
  isTerminalStatus,
  normalizeListPayload,
  parseJsonText,
} from './utils'
import { watchTask } from './task'

const props = defineProps({
  projectId: { type: Number, default: null },
})

const switchTab = inject('webTestingSwitchTab', null)

const filters = reactive({ search: '', browser: '' })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

const suites = ref([])
const loading = ref(false)
const errorMessage = ref('')
const deletingId = ref(null)
const runningId = ref(null)

const caseOptions = ref([])
const casesLoading = ref(false)
const environments = ref([])
const environmentsLoading = ref(false)

const dialogVisible = ref(false)
const saving = ref(false)
const formRef = ref(null)
const form = reactive({
  id: null,
  name: '',
  description: '',
  browser: 'chromium',
  headless: true,
  environment: null,
  is_active: true,
  case_ids: [],
  configText: '{}',
})

const rules = {
  name: [{ required: true, message: '请输入套件名称', trigger: 'blur' }],
  case_ids: [{ required: true, message: '请至少选择一个用例', trigger: 'change' }],
}

const runDialog = reactive({
  visible: false,
  loading: false,
  submitted: false,
  suiteId: null,
  suiteName: '',
  environment: null,
  status: 'pending',
  progress: null,
  message: '',
  executionId: null,
})
let runWatcher = null

const progressStatus = computed(() => {
  if (runDialog.status === 'passed') return 'success'
  if (runDialog.status === 'failed' || runDialog.status === 'error') return 'exception'
  if (runDialog.status === 'cancelled') return 'warning'
  return ''
})

async function loadSuites() {
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
    if (filters.browser) params.browser = filters.browser
    const data = await webTestingApi.listSuites(params)
    const { results, count } = normalizeListPayload(data)
    suites.value = results
    pagination.total = count
  } catch (error) {
    suites.value = []
    pagination.total = 0
    errorMessage.value = error?.message || '套件列表加载失败'
  } finally {
    loading.value = false
  }
}

async function loadOptions() {
  if (!props.projectId) return
  casesLoading.value = true
  environmentsLoading.value = true
  const [casesResult, envResult] = await Promise.allSettled([
    webTestingApi.listCases({ project: props.projectId, page: 1, page_size: 200 }),
    projectsApi.listEnvironments({ project: props.projectId, page: 1, page_size: 100 }),
  ])
  caseOptions.value = casesResult.status === 'fulfilled'
    ? normalizeListPayload(casesResult.value).results
    : []
  environments.value = envResult.status === 'fulfilled'
    ? normalizeListPayload(envResult.value).results
    : []
  casesLoading.value = false
  environmentsLoading.value = false
}

function handleSearch() {
  pagination.page = 1
  loadSuites()
}

function handleReset() {
  filters.search = ''
  filters.browser = ''
  pagination.page = 1
  loadSuites()
}

function resetForm() {
  form.id = null
  form.name = ''
  form.description = ''
  form.browser = 'chromium'
  form.headless = true
  form.environment = null
  form.is_active = true
  form.case_ids = []
  form.configText = '{}'
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
  loadOptions()
  formRef.value?.clearValidate?.()
}

function openEdit(row) {
  resetForm()
  form.id = row.id
  form.name = row.name || ''
  form.description = row.description || ''
  form.browser = row.browser || 'chromium'
  form.headless = row.headless !== false
  form.environment = row.environment ?? null
  form.is_active = row.is_active !== false
  form.case_ids = Array.isArray(row.case_ids) ? [...row.case_ids] : []
  form.configText = JSON.stringify(row.config || {}, null, 2)
  dialogVisible.value = true
  loadOptions()
  formRef.value?.clearValidate?.()
}

function handleDialogClosed() {
  formRef.value?.clearValidate?.()
}

async function handleSubmit() {
  if (formRef.value) {
    try {
      await formRef.value.validate()
    } catch {
      return
    }
  }
  const config = parseJsonText(form.configText, { allowEmpty: true, expected: 'object' })
  if (!config.ok) {
    ElMessage.error(`执行配置 JSON 不合法：${config.error}`)
    return
  }
  saving.value = true
  try {
    const payload = {
      project: props.projectId,
      name: form.name.trim(),
      description: form.description.trim(),
      browser: form.browser,
      headless: form.headless,
      environment: form.environment ?? null,
      is_active: form.is_active,
      case_ids: form.case_ids,
      config: config.value || {},
    }
    if (form.id) {
      await webTestingApi.updateSuite(form.id, payload)
      ElMessage.success('套件已更新')
    } else {
      await webTestingApi.createSuite(payload)
      ElMessage.success('套件已创建')
    }
    dialogVisible.value = false
    await loadSuites()
  } catch (error) {
    ElMessage.error(error?.message || '保存套件失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  deletingId.value = row.id
  try {
    await webTestingApi.removeSuite(row.id)
    ElMessage.success('套件已删除')
    if (suites.value.length === 1 && pagination.page > 1) pagination.page -= 1
    await loadSuites()
  } catch (error) {
    ElMessage.error(error?.message || '删除套件失败')
  } finally {
    deletingId.value = null
  }
}

function openRun(row) {
  runWatcher?.close()
  runDialog.visible = true
  runDialog.loading = false
  runDialog.submitted = false
  runDialog.suiteId = row.id
  runDialog.suiteName = row.name
  runDialog.environment = row.environment ?? null
  runDialog.status = 'pending'
  runDialog.progress = null
  runDialog.message = ''
  runDialog.executionId = null
  loadOptions()
}

async function submittedRun() {
  if (!runDialog.suiteId) return
  runDialog.loading = true
  runDialog.submitted = true
  runDialog.status = 'pending'
  runDialog.progress = null
  runDialog.message = '已提交执行任务，等待执行…'
  runWatcher?.close()
  try {
    const payload = {}
    if (runDialog.environment) payload.environment = runDialog.environment
    const data = await webTestingApi.runSuite(runDialog.suiteId, payload)
    runningId.value = runDialog.suiteId
    runDialog.executionId = data.execution_id ?? null
    runDialog.status = data.execution_status || 'pending'
    const taskId = data.task_id ?? data.execution_id
    runWatcher = watchTask(taskId, {
      fetchState: () => webTestingApi.retrieveExecution(data.execution_id),
      onProgress: (state) => {
        runDialog.status = state.status || runDialog.status
        runDialog.progress = state.progress
        runDialog.message = state.message || runDialog.message
      },
      onFinished: (state) => {
        runDialog.status = state.status
        runDialog.progress = 100
        runDialog.message = `执行结束：${state.status}`
        ElMessage.success(`套件执行结束：${state.status}`)
        loadSuites()
      },
    })
  } catch (error) {
    runDialog.status = 'error'
    runDialog.message = error?.message || '运行失败'
    ElMessage.error(runDialog.message)
  } finally {
    runDialog.loading = false
    runningId.value = null
  }
}

function goExecutions() {
  runDialog.visible = false
  if (typeof switchTab === 'function') switchTab('executions')
}

watch(
  () => props.projectId,
  () => {
    filters.browser = ''
    pagination.page = 1
    loadSuites()
    loadOptions()
  },
)

onMounted(() => {
  loadSuites()
  loadOptions()
})

onBeforeUnmount(() => {
  runWatcher?.close()
})
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

.run-progress__text {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 16px 0 0;
}
</style>
