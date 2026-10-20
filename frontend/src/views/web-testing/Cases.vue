<template>
  <div class="tab-panel">
    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="filters.search"
            class="filter-input"
            placeholder="搜索用例名称 / 描述"
            :prefix-icon="Search"
            clearable
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
          <el-tree-select
            v-model="filters.module"
            class="filter-select-wide"
            :data="moduleTree"
            :props="{ label: 'name', value: 'id', children: 'children' }"
            check-strictly
            clearable
            placeholder="所属模块"
            @change="handleSearch"
          />
          <el-select
            v-model="filters.script_type"
            class="filter-select"
            placeholder="脚本类型"
            clearable
            @change="handleSearch"
          >
            <el-option
              v-for="option in SCRIPT_TYPE_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-button :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </div>
        <div class="toolbar__right">
          <span class="text-small text-muted">共 {{ pagination.total }} 条用例</span>
          <el-button type="primary" :icon="Plus" @click="openCreate">新建用例</el-button>
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
        :data="cases"
        :loading="loading"
        :total="pagination.total"
        row-key="id"
        empty-text="暂无用例，点击「新建用例」开始"
        @change="loadCases"
      >
        <el-table-column label="用例名称" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" underline="never" @click="openEdit(row)">{{ row.name }}</el-link>
            <div v-if="row.description" class="row-desc">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="模块" width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.module_name || '未归类' }}</template>
        </el-table-column>
        <el-table-column label="脚本类型" width="110">
          <template #default="{ row }">{{ getScriptTypeText(row.script_type) }}</template>
        </el-table-column>
        <el-table-column label="步骤" width="70" align="center">
          <template #default="{ row }">{{ row.step_count ?? (row.steps || []).length }}</template>
        </el-table-column>
        <el-table-column label="优先级" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="PRIORITY_TAG_TYPE[row.priority] || 'info'" effect="light">
              {{ getPriorityText(row.priority) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="100">
          <template #default="{ row }">{{ SOURCE_TEXT[row.source] || row.source || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <StatusTag :status="row.is_active ? 'active' : 'inactive'" />
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" :loading="generatingId === row.id" @click="handleGenerateScript(row)">
              生成脚本
            </el-button>
            <el-button link type="primary" @click="openNlDialog(row)">自然语言生成</el-button>
            <el-button link type="primary" :disabled="!row.is_active" @click="handleRun(row)">执行</el-button>
            <ConfirmButton
              link
              type="danger"
              text="删除"
              :content="`确定删除用例「${row.name}」吗？`"
              :loading="deletingId === row.id"
              @confirm="handleDelete(row)"
            />
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <!-- 新建 / 编辑抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      :title="form.id ? '编辑用例' : '新建用例'"
      size="880px"
      :close-on-click-modal="false"
      @closed="handleDrawerClosed"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="用例名称" prop="name">
              <el-input v-model="form.name" maxlength="255" show-word-limit placeholder="例如：登录成功跳转首页" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="所属模块" prop="module">
              <el-tree-select
                v-model="form.module"
                :data="moduleTree"
                :props="{ label: 'name', value: 'id', children: 'children' }"
                check-strictly
                clearable
                placeholder="不选则为未归类"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="用例类型" prop="case_type">
              <el-select v-model="form.case_type" style="width: 100%">
                <el-option
                  v-for="option in CASE_TYPE_OPTIONS"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="脚本类型" prop="script_type">
              <el-radio-group v-model="form.script_type">
                <el-radio-button
                  v-for="option in SCRIPT_TYPE_OPTIONS"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ option.label }}
                </el-radio-button>
              </el-radio-group>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="优先级" prop="priority">
              <el-select v-model="form.priority" style="width: 100%">
                <el-option
                  v-for="option in PRIORITY_OPTIONS"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="启用状态">
              <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="用例描述">
              <el-input
                v-model="form.description"
                type="textarea"
                :rows="2"
                maxlength="500"
                show-word-limit
                placeholder="前置条件、预期结果等"
              />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="POM 引用">
              <el-select
                v-model="form.pom_refs"
                multiple
                filterable
                collapse-tags
                collapse-tags-tooltip
                placeholder="选择关联的页面对象（可多选）"
                style="width: 100%"
                :loading="pagesLoading"
              >
                <el-option
                  v-for="option in pageOptions(pages)"
                  :key="option.value"
                  :label="option.value ? `${option.label}${option.url ? `（${option.url}）` : ''}` : option.label"
                  :value="option.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">测试步骤</el-divider>
        <StepEditor v-model="form.steps" :errors="stepErrors" />

        <el-divider content-position="left">断言（JSON 数组）</el-divider>
        <el-input
          v-model="form.assertionsText"
          type="textarea"
          :rows="3"
          class="mono"
          placeholder='例如：[{"type":"text","expected":"欢迎"}]'
        />

        <el-divider v-if="form.script" content-position="left">当前脚本</el-divider>
        <pre v-if="form.script" class="script-preview">{{ form.script }}</pre>
      </el-form>

      <template #footer>
        <el-button @click="drawerVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSubmit">保存</el-button>
      </template>
    </el-drawer>

    <!-- 脚本生成结果 -->
    <el-dialog v-model="scriptDialog.visible" title="生成的脚本" width="880px">
      <div class="script-meta">
        <el-tag size="small" effect="light">{{ getScriptTypeText(scriptDialog.scriptType) }}</el-tag>
        <span class="text-small text-muted">
          用例：{{ scriptDialog.caseName }} · 生成方式：{{ scriptDialog.generatedBy || '—' }}
        </span>
      </div>
      <pre class="script-preview script-preview--lg">{{ scriptDialog.content || '（脚本为空）' }}</pre>
      <template #footer>
        <el-button @click="copyScript">复制</el-button>
        <el-button @click="downloadScript">下载</el-button>
        <el-button type="primary" @click="scriptDialog.visible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 自然语言生成步骤 -->
    <el-dialog v-model="nlDialog.visible" title="从自然语言生成步骤" width="720px">
      <el-form label-width="96px">
        <el-form-item label="目标用例">
          <span>{{ nlDialog.caseName || '（未选择）' }}</span>
        </el-form-item>
        <el-form-item label="操作描述">
          <el-input
            v-model="nlDialog.text"
            type="textarea"
            :rows="5"
            placeholder="例如：打开 https://demo.example.com/login，输入用户名 admin，密码 123456，点击登录，断言页面显示「欢迎」"
          />
        </el-form-item>
        <el-form-item label="覆盖步骤">
          <el-switch v-model="nlDialog.apply" active-text="生成后直接覆盖用例步骤" />
        </el-form-item>
      </el-form>

      <el-alert
        v-if="nlDialog.error"
        :title="nlDialog.error"
        type="error"
        show-icon
        :closable="false"
        class="mb-16"
      />

      <template v-if="nlDialog.result">
        <el-divider content-position="left">生成结果（{{ nlDialog.result.generated_by || '—' }}）</el-divider>
        <el-empty
          v-if="!nlDialog.result.steps?.length"
          description="未解析出步骤，请补充更明确的操作描述"
          :image-size="60"
        />
        <ol v-else class="step-list">
          <li v-for="(step, index) in nlDialog.result.steps" :key="index">
            {{ formatStep(step, index + 1) }}
          </li>
        </ol>
      </template>

      <template #footer>
        <el-button @click="nlDialog.visible = false">关闭</el-button>
        <el-button type="primary" :loading="nlDialog.loading" @click="submitNl">生成</el-button>
      </template>
    </el-dialog>

    <!-- 单用例执行进度 -->
    <el-dialog v-model="runDialog.visible" title="用例执行" width="460px" :close-on-click-modal="false">
      <div class="run-progress">
        <el-progress
          :percentage="getProgressPercent(runDialog)"
          :status="progressStatus"
          :stroke-width="14"
        />
        <p class="run-progress__text">
          <StatusTag :status="runDialog.status || 'pending'" />
          <span class="text-small text-muted">{{ runDialog.message || '正在执行，请稍候…' }}</span>
        </p>
      </div>
      <template #footer>
        <el-button @click="runDialog.visible = false">关闭</el-button>
        <el-button type="primary" :disabled="!isTerminalStatus(runDialog.status)" @click="goExecutions">
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
import StepEditor from './StepEditor.vue'

import { webTestingApi } from '@/api/webTesting'
import { downloadText } from '@/utils/download'
import { formatDateTime } from '@/utils/format'
import {
  CASE_TYPE_OPTIONS,
  PRIORITY_OPTIONS,
  PRIORITY_TAG_TYPE,
  SCRIPT_TYPE_OPTIONS,
  SOURCE_TEXT,
  buildStepsPayload,
  formatStep,
  getPriorityText,
  getProgressPercent,
  getScriptTypeText,
  isTerminalStatus,
  normalizeListPayload,
  normalizeSteps,
  pageOptions,
  parseJsonText,
  scriptFileName,
  validateSteps,
} from './utils'
import { watchTask } from './task'

const props = defineProps({
  projectId: { type: Number, default: null },
})

const switchTab = inject('webTestingSwitchTab', null)

const moduleTree = ref([])
const pages = ref([])
const pagesLoading = ref(false)

const filters = reactive({ search: '', module: null, script_type: '' })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

const cases = ref([])
const loading = ref(false)
const errorMessage = ref('')
const deletingId = ref(null)
const generatingId = ref(null)

const drawerVisible = ref(false)
const saving = ref(false)
const formRef = ref(null)
const form = reactive({
  id: null,
  name: '',
  module: null,
  description: '',
  case_type: 'ui',
  script_type: 'playwright',
  priority: 'medium',
  is_active: true,
  steps: [],
  pom_refs: [],
  assertionsText: '[]',
  script: '',
})

const rules = {
  name: [{ required: true, message: '请输入用例名称', trigger: 'blur' }],
}

const stepErrors = ref([])

const scriptDialog = reactive({
  visible: false,
  content: '',
  scriptType: 'playwright',
  generatedBy: '',
  caseName: '',
})

const nlDialog = reactive({
  visible: false,
  loading: false,
  caseId: null,
  caseName: '',
  text: '',
  apply: true,
  result: null,
  error: '',
})

const runDialog = reactive({
  visible: false,
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

async function loadMeta() {
  if (!props.projectId) return
  const [treeResult, pagesResult] = await Promise.allSettled([
    webTestingApi.moduleTree({ project: props.projectId }),
    webTestingApi.listPages({ project: props.projectId, page: 1, page_size: 100 }),
  ])
  moduleTree.value = treeResult.status === 'fulfilled' && Array.isArray(treeResult.value)
    ? treeResult.value
    : []
  if (pagesResult.status === 'fulfilled') {
    pages.value = normalizeListPayload(pagesResult.value).results
  } else {
    pages.value = []
  }
}

async function loadCases() {
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
    if (filters.module) params.module = filters.module
    if (filters.script_type) params.script_type = filters.script_type
    const data = await webTestingApi.listCases(params)
    const { results, count } = normalizeListPayload(data)
    cases.value = results
    pagination.total = count
  } catch (error) {
    cases.value = []
    pagination.total = 0
    errorMessage.value = error?.message || '用例列表加载失败'
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadCases()
}

function handleReset() {
  filters.search = ''
  filters.module = null
  filters.script_type = ''
  pagination.page = 1
  loadCases()
}

function resetForm() {
  form.id = null
  form.name = ''
  form.module = filters.module ?? null
  form.description = ''
  form.case_type = 'ui'
  form.script_type = 'playwright'
  form.priority = 'medium'
  form.is_active = true
  form.steps = []
  form.pom_refs = []
  form.assertionsText = '[]'
  form.script = ''
  stepErrors.value = []
}

function openCreate() {
  resetForm()
  drawerVisible.value = true
  formRef.value?.clearValidate?.()
}

async function openEdit(row) {
  resetForm()
  form.id = row.id
  form.name = row.name || ''
  form.module = row.module ?? null
  form.description = row.description || ''
  form.case_type = row.case_type || 'ui'
  form.script_type = row.script_type || 'playwright'
  form.priority = row.priority || 'medium'
  form.is_active = row.is_active !== false
  form.steps = normalizeSteps(row.steps)
  form.pom_refs = Array.isArray(row.pom_refs) ? [...row.pom_refs] : []
  form.assertionsText = JSON.stringify(row.assertions || [], null, 2)
  form.script = row.script || ''
  drawerVisible.value = true
  formRef.value?.clearValidate?.()
  try {
    const detail = await webTestingApi.retrieveCase(row.id)
    form.name = detail.name || form.name
    form.module = detail.module ?? form.module
    form.description = detail.description || ''
    form.case_type = detail.case_type || form.case_type
    form.script_type = detail.script_type || form.script_type
    form.priority = detail.priority || form.priority
    form.is_active = detail.is_active !== false
    form.steps = normalizeSteps(detail.steps)
    form.pom_refs = Array.isArray(detail.pom_refs) ? [...detail.pom_refs] : []
    form.assertionsText = JSON.stringify(detail.assertions || [], null, 2)
    form.script = detail.script || ''
  } catch (error) {
    ElMessage.warning(error?.message || '用例详情加载失败，已使用列表数据')
  }
}

function handleDrawerClosed() {
  formRef.value?.clearValidate?.()
  stepErrors.value = []
}

async function handleSubmit() {
  if (formRef.value) {
    try {
      await formRef.value.validate()
    } catch {
      return
    }
  }
  const stepsResult = validateSteps(form.steps)
  if (!stepsResult.valid) {
    stepErrors.value = stepsResult.errors
    ElMessage.error('测试步骤校验未通过，请检查后重试')
    return
  }
  stepErrors.value = []
  const assertions = parseJsonText(form.assertionsText, { allowEmpty: true, expected: 'array' })
  if (!assertions.ok) {
    ElMessage.error(`断言 JSON 不合法：${assertions.error}`)
    return
  }
  saving.value = true
  try {
    const payload = {
      project: props.projectId,
      name: form.name.trim(),
      module: form.module ?? null,
      description: form.description.trim(),
      case_type: form.case_type,
      script_type: form.script_type,
      priority: form.priority,
      is_active: form.is_active,
      steps: buildStepsPayload(form.steps),
      pom_refs: Array.isArray(form.pom_refs) ? form.pom_refs : [],
      assertions: assertions.value || [],
    }
    if (form.id) {
      await webTestingApi.updateCase(form.id, payload)
      ElMessage.success('用例已更新')
    } else {
      await webTestingApi.createCase(payload)
      ElMessage.success('用例已创建')
    }
    drawerVisible.value = false
    await loadCases()
    await loadMeta()
  } catch (error) {
    ElMessage.error(error?.message || '保存用例失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  deletingId.value = row.id
  try {
    await webTestingApi.removeCase(row.id)
    ElMessage.success('用例已删除')
    if (cases.value.length === 1 && pagination.page > 1) pagination.page -= 1
    await loadCases()
  } catch (error) {
    ElMessage.error(error?.message || '删除用例失败')
  } finally {
    deletingId.value = null
  }
}

async function handleGenerateScript(row) {
  generatingId.value = row.id
  try {
    const data = await webTestingApi.generateScript(row.id, { script_type: row.script_type || 'playwright' })
    scriptDialog.visible = true
    scriptDialog.content = data.script || ''
    scriptDialog.scriptType = data.script_type || row.script_type
    scriptDialog.generatedBy = data.generated_by || ''
    scriptDialog.caseName = row.name
    ElMessage.success('脚本已生成')
    await loadCases()
  } catch (error) {
    ElMessage.error(error?.message || '脚本生成失败')
  } finally {
    generatingId.value = null
  }
}

async function copyScript() {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(scriptDialog.content || '')
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = scriptDialog.content || ''
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    ElMessage.success('脚本已复制到剪贴板')
  } catch (error) {
    ElMessage.error(`复制失败：${error?.message || '浏览器不支持'}`)
  }
}

function downloadScript() {
  downloadText(
    scriptDialog.content || '',
    scriptFileName({ name: scriptDialog.caseName }, scriptDialog.scriptType),
    'text/plain;charset=utf-8',
  )
}

function openNlDialog(row) {
  nlDialog.visible = true
  nlDialog.caseId = row.id
  nlDialog.caseName = row.name
  nlDialog.text = ''
  nlDialog.apply = true
  nlDialog.result = null
  nlDialog.error = ''
}

async function submitNl() {
  if (!nlDialog.text.trim()) {
    ElMessage.warning('请先填写操作描述')
    return
  }
  nlDialog.loading = true
  nlDialog.error = ''
  try {
    const data = await webTestingApi.generateFromNl(nlDialog.caseId, {
      natural_language: nlDialog.text.trim(),
      apply: nlDialog.apply,
    })
    nlDialog.result = data
    ElMessage.success(data.applied ? '已生成并应用步骤' : '已生成步骤（未保存）')
    if (data.applied) await loadCases()
  } catch (error) {
    nlDialog.error = error?.message || '自然语言生成失败'
  } finally {
    nlDialog.loading = false
  }
}

function handleRun(row) {
  runDialog.visible = true
  runDialog.status = 'pending'
  runDialog.progress = null
  runDialog.message = '已提交执行任务，等待执行…'
  runDialog.executionId = null
  runWatcher?.close()
  webTestingApi
    .runCase(row.id)
    .then((data) => {
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
          runDialog.message = state.status === 'passed' ? '执行通过' : `执行结束：${state.status}`
          ElMessage.success(`用例执行结束：${state.status}`)
          loadCases()
        },
      })
    })
    .catch((error) => {
      runDialog.status = 'error'
      runDialog.message = error?.message || '执行提交失败'
      ElMessage.error(runDialog.message)
    })
}

function goExecutions() {
  runDialog.visible = false
  if (typeof switchTab === 'function') switchTab('executions')
  else runDialog.visible = false
}

watch(
  () => props.projectId,
  () => {
    filters.module = null
    pagination.page = 1
    loadMeta()
    loadCases()
  },
)

onMounted(() => {
  loadMeta()
  loadCases()
})

onBeforeUnmount(() => {
  runWatcher?.close()
})
</script>

<style scoped>
.filter-select-wide {
  width: 200px;
}

.row-desc {
  margin-top: 2px;
  overflow: hidden;
  color: #94a3b8;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.script-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.script-preview {
  max-height: 260px;
  margin: 0;
  padding: 12px;
  overflow: auto;
  border-radius: 8px;
  background: #0f172a;
  color: #e2e8f0;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12.5px;
  white-space: pre-wrap;
  word-break: break-word;
}

.script-preview--lg {
  max-height: 460px;
}

.step-list {
  margin: 0;
  padding-left: 20px;
  color: #334155;
  font-size: 13px;
  line-height: 1.9;
}

.run-progress {
  padding: 8px 4px;
}

.run-progress__text {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 16px 0 0;
}
</style>
