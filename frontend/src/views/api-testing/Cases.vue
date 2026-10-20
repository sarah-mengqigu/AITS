<template>
  <div class="cases-pane">
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
            placeholder="搜索用例名称 / 描述"
            :prefix-icon="Search"
            clearable
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
          <el-select
            v-model="filters.case_type"
            class="filter-select"
            placeholder="用例类型"
            clearable
            @change="handleSearch"
          >
            <el-option
              v-for="option in CASE_TYPE_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-select
            v-model="filters.test_type"
            class="filter-select"
            placeholder="测试类型"
            clearable
            @change="handleSearch"
          >
            <el-option
              v-for="option in TEST_TYPE_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-select
            v-model="filters.source"
            class="filter-select"
            placeholder="来源"
            clearable
            @change="handleSearch"
          >
            <el-option
              v-for="option in SOURCE_OPTIONS"
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
          <el-button :icon="Refresh" :loading="loading" @click="loadCases">刷新</el-button>
          <el-button type="primary" :icon="Plus" @click="openCreate">新建用例</el-button>
        </div>
      </div>

      <DataTable
        v-model:page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :data="cases"
        :loading="loading"
        :total="pagination.total"
        row-key="id"
        empty-text="暂无用例"
        @change="loadCases"
      >
        <el-table-column label="用例名称" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" :underline="false" @click="openEdit(row)">
              {{ row.name }}
            </el-link>
            <div v-if="row.description" class="case-desc">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="86">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ getCaseTypeLabel(row.case_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="测试类型" width="94">
          <template #default="{ row }">
            <el-tag size="small" effect="light" :type="getTestTypeTagType(row.test_type)">
              {{ getTestTypeLabel(row.test_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="94">
          <template #default="{ row }">{{ getSourceLabel(row.source) }}</template>
        </el-table-column>
        <el-table-column label="优先级" width="88">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="getPriorityMeta(row.priority).tagType">
              {{ getPriorityMeta(row.priority).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="断言" width="70" align="center">
          <template #default="{ row }">{{ Array.isArray(row.assertions) ? row.assertions.length : 0 }}</template>
        </el-table-column>
        <el-table-column label="关联端点" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.endpoint_name || row.endpoint || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <StatusTag :status="row.is_active ? 'active' : 'inactive'" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="272" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" @click="handleGenerateScript(row)">生成脚本</el-button>
            <el-button
              link
              type="primary"
              :loading="runningCaseId === row.id"
              @click="handleRun(row)"
            >
              执行
            </el-button>
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
        <template #empty>
          <EmptyState
            title="暂无用例"
            description="可以在端点列表中批量生成用例，或点击「新建用例」手工编写请求配置与断言。"
          >
            <el-button type="primary" :icon="Plus" @click="openCreate">新建用例</el-button>
            <el-button @click="emit('switch-tab', 'endpoints')">去端点生成</el-button>
          </EmptyState>
        </template>
      </DataTable>
    </div>

    <!-- 新建 / 编辑用例 -->
    <el-drawer
      v-model="drawerVisible"
      :title="drawerMode === 'create' ? '新建用例' : '编辑用例'"
      size="72%"
      :close-on-click-modal="false"
      @closed="handleDrawerClosed"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="98px"
        class="case-form"
        @submit.prevent
      >
        <div class="form-section-title">基本信息</div>
        <div class="form-grid">
          <el-form-item label="用例名称" prop="name" class="form-grid__full">
            <el-input v-model="form.name" maxlength="255" show-word-limit placeholder="例如：登录接口 - 正向用例" />
          </el-form-item>
          <el-form-item label="用例类型" prop="case_type">
            <el-select v-model="form.case_type" style="width: 100%" @change="handleCaseTypeChange">
              <el-option
                v-for="option in CASE_TYPE_OPTIONS"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="测试类型" prop="test_type">
            <el-select v-model="form.test_type" style="width: 100%">
              <el-option
                v-for="option in TEST_TYPE_OPTIONS"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </el-form-item>
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
          <el-form-item label="启用状态">
            <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
          </el-form-item>
          <el-form-item label="关联端点">
            <el-select
              v-model="form.endpoint"
              style="width: 100%"
              filterable
              clearable
              :loading="optionsLoading"
              placeholder="可选，关联到具体端点"
            >
              <el-option
                v-for="option in endpointSelectOptions"
                :key="option.id"
                :label="option.label"
                :value="option.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="所属模块">
            <el-select
              v-model="form.module"
              style="width: 100%"
              filterable
              clearable
              :loading="optionsLoading"
              placeholder="可选"
            >
              <el-option
                v-for="option in moduleSelectOptions"
                :key="option.id"
                :label="option.label"
                :value="option.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="用例描述" class="form-grid__full">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="2"
              maxlength="500"
              show-word-limit
              placeholder="用例目的、前置条件等"
            />
          </el-form-item>
        </div>

        <div class="form-section-title">请求配置</div>
        <el-alert
          v-if="form.case_type === 'scenario'"
          class="mb-16"
          type="warning"
          :closable="false"
          show-icon
          title="场景用例需要在下方 JSON 中配置 request_config.steps（步骤数组），保存时由后端校验。"
        />
        <template v-if="form.case_type === 'scenario'">
          <el-form-item label="request_config" :error="jsonErrors.raw">
            <div class="json-field">
              <el-input
                v-model="form.rawRequestText"
                type="textarea"
                :rows="12"
                class="json-textarea mono"
                placeholder='{ "steps": [ { "name": "步骤1", "request_config": { "method": "GET", "url": "/api/health" }, "assertions": [{ "type": "status_code", "expected": 200 }] } ] }'
              />
              <div class="json-field__actions">
                <el-button size="small" :icon="MagicStick" @click="formatField('raw')">格式化</el-button>
                <span class="text-small text-muted">steps 必须是非空数组</span>
              </div>
            </div>
          </el-form-item>
        </template>
        <template v-else>
          <div class="form-grid">
            <el-form-item label="请求方法" prop="method">
              <el-select v-model="form.method" style="width: 100%">
                <el-option
                  v-for="method in HTTP_METHODS"
                  :key="method"
                  :label="getMethodLabel(method)"
                  :value="method.toUpperCase()"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="请求 URL" prop="url">
              <el-input v-model="form.url" placeholder="/api/users/{id} 或 https://host/api/users" />
            </el-form-item>
            <el-form-item label="Query 参数" class="form-grid__full" :error="jsonErrors.params">
              <div class="json-field">
                <el-input
                  v-model="form.paramsText"
                  type="textarea"
                  :rows="5"
                  class="json-textarea mono"
                  placeholder='{ "page": 1, "page_size": 20 }'
                />
                <div class="json-field__actions">
                  <el-button size="small" :icon="MagicStick" @click="formatField('params')">格式化</el-button>
                </div>
              </div>
            </el-form-item>
            <el-form-item label="请求头" class="form-grid__full" :error="jsonErrors.headers">
              <div class="json-field">
                <el-input
                  v-model="form.headersText"
                  type="textarea"
                  :rows="5"
                  class="json-textarea mono"
                  placeholder='{ "Content-Type": "application/json" }'
                />
                <div class="json-field__actions">
                  <el-button size="small" :icon="MagicStick" @click="formatField('headers')">格式化</el-button>
                </div>
              </div>
            </el-form-item>
            <el-form-item label="请求体" class="form-grid__full" :error="jsonErrors.body">
              <div class="json-field">
                <el-input
                  v-model="form.bodyText"
                  type="textarea"
                  :rows="7"
                  class="json-textarea mono"
                  placeholder='{ "username": "demo", "password": "demo" }'
                />
                <div class="json-field__actions">
                  <el-button size="small" :icon="MagicStick" @click="formatField('body')">格式化</el-button>
                  <span class="text-small text-muted">支持任意合法 JSON；保存时统一包装为 raw/json</span>
                </div>
              </div>
            </el-form-item>
          </div>
        </template>

        <div class="form-section-title">
          断言配置
          <el-button size="small" :icon="Plus" @click="addAssertion">添加断言</el-button>
        </div>
        <el-table :data="assertionRows" size="small" border empty-text="暂无断言，保存的用例将不校验响应">
          <el-table-column label="断言类型" width="150">
            <template #default="{ row }">
              <el-select v-model="row.type" size="small" style="width: 100%" @change="handleAssertionTypeChange(row)">
                <el-option
                  v-for="option in ASSERTION_TYPE_OPTIONS"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="JSON 路径" min-width="190">
            <template #default="{ row }">
              <el-input
                v-model="row.json_path"
                size="small"
                :disabled="isPathDisabled(row)"
                placeholder="例如 data.list[0].id"
              />
            </template>
          </el-table-column>
          <el-table-column label="期望值" min-width="150">
            <template #default="{ row }">
              <el-input v-model="row.expected" size="small" placeholder="例如 200 / ok / 1" />
            </template>
          </el-table-column>
          <el-table-column label="比较方式" width="130">
            <template #default="{ row }">
              <el-select
                v-model="row.operator"
                size="small"
                style="width: 100%"
                :disabled="isOperatorDisabled(row)"
                @change="handleAssertionOperatorChange(row)"
              >
                <el-option
                  v-for="option in ASSERTION_OPERATOR_OPTIONS"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" @click="removeAssertion($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <p class="text-small text-muted mt-8">
          说明：比较方式与断言类型联动（等于 → JSON 路径、包含 → 包含、大于等于 → 长度≥、小于 → 响应时间&lt;），
          保存时同时写入 type 与 operator，后端以 type 执行比较。
        </p>
      </el-form>

      <template #footer>
        <el-button @click="drawerVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">保存用例</el-button>
      </template>
    </el-drawer>

    <!-- HttpRunner YAML -->
    <el-dialog
      v-model="scriptVisible"
      title="HttpRunner YAML 脚本"
      width="760px"
      @closed="scriptYaml = ''"
    >
      <div v-loading="scriptLoading">
        <el-alert v-if="scriptError" :title="scriptError" type="error" show-icon :closable="false" />
        <template v-if="scriptYaml">
          <div class="script-toolbar">
            <span class="text-small text-muted">{{ scriptCase?.name || '' }}</span>
            <div>
              <el-button size="small" :icon="CopyDocument" @click="copyScript">复制</el-button>
              <el-button size="small" :icon="Download" @click="downloadScript">下载 YAML</el-button>
            </div>
          </div>
          <pre class="yaml-block">{{ scriptYaml }}</pre>
        </template>
      </div>
      <template #footer>
        <el-button @click="scriptVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <ExecutionProgressDialog
      v-model="progressVisible"
      :execution-id="progressExecutionId"
      :title="progressTitle"
      @finished="emit('execution-created')"
      @open-detail="handleOpenProgressDetail"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  CopyDocument,
  Download,
  MagicStick,
  Plus,
  Refresh,
  RefreshLeft,
  Search,
} from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import EmptyState from '@/components/EmptyState.vue'
import StatusTag from '@/components/StatusTag.vue'
import ConfirmButton from '@/components/ConfirmButton.vue'
import ExecutionProgressDialog from './components/ExecutionProgressDialog.vue'

import { apiTestingApi } from '@/api/apiTesting'
import { downloadText } from '@/utils/download'
import {
  ASSERTION_OPERATOR_OPTIONS,
  ASSERTION_TYPE_OPTIONS,
  CASE_TYPE_OPTIONS,
  HTTP_METHODS,
  PRIORITY_OPTIONS,
  SOURCE_OPTIONS,
  TEST_TYPE_OPTIONS,
  buildAssertionsPayload,
  buildRequestConfig,
  formatJsonText,
  getAssertionTypeForOperator,
  getCaseTypeLabel,
  getMethodLabel,
  getOperatorForAssertionType,
  getPriorityMeta,
  getSourceLabel,
  getTestTypeLabel,
  getTestTypeTagType,
  isValidRequestUrl,
  normalizeAssertionRows,
  requestConfigToForm,
  validateAssertionRows,
  validateJsonText,
} from './utils'

const props = defineProps({
  projectId: { type: [Number, String], default: null },
  refreshKey: { type: Number, default: 0 },
})

const emit = defineEmits(['execution-created', 'changed', 'switch-tab', 'open-execution'])

const cases = ref([])
const loading = ref(false)
const errorMessage = ref('')
const deletingId = ref(null)
const runningCaseId = ref(null)
const filters = reactive({ search: '', test_type: '', case_type: '', source: '' })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

const drawerVisible = ref(false)
const drawerMode = ref('create')
const submitting = ref(false)
const formRef = ref(null)
const editingCase = ref(null)
const optionsLoading = ref(false)
const endpointOptions = ref([])
const moduleOptions = ref([])

const form = reactive({
  name: '',
  case_type: 'endpoint',
  test_type: 'positive',
  priority: 2,
  description: '',
  endpoint: null,
  module: null,
  is_active: true,
  method: 'GET',
  url: '',
  paramsText: '',
  headersText: '',
  bodyText: '',
  rawRequestText: '',
})

const assertionRows = ref([])
const jsonErrors = reactive({ params: '', headers: '', body: '', raw: '' })

const scriptVisible = ref(false)
const scriptLoading = ref(false)
const scriptError = ref('')
const scriptYaml = ref('')
const scriptCase = ref(null)

const progressVisible = ref(false)
const progressExecutionId = ref(null)
const progressTitle = ref('单用例执行')

const endpointSelectOptions = computed(() => {
  const options = endpointOptions.value.map((item) => ({
    id: item.id,
    label: `${getMethodLabel(item.method)} ${item.path}`,
  }))
  if (form.endpoint && !options.some((option) => option.id === form.endpoint)) {
    options.unshift({
      id: form.endpoint,
      label: editingCase.value?.endpoint_name || `端点 #${form.endpoint}`,
    })
  }
  return options
})

const moduleSelectOptions = computed(() => {
  const options = moduleOptions.value.map((item) => ({
    id: item.id,
    label: item.full_path || item.name,
  }))
  if (form.module && !options.some((option) => option.id === form.module)) {
    options.unshift({
      id: form.module,
      label: editingCase.value?.module_name || `模块 #${form.module}`,
    })
  }
  return options
})

const rules = {
  name: [
    { required: true, message: '请输入用例名称', trigger: 'blur' },
    { max: 255, message: '用例名称不能超过 255 个字符', trigger: 'blur' },
  ],
  case_type: [{ required: true, message: '请选择用例类型', trigger: 'change' }],
  test_type: [{ required: true, message: '请选择测试类型', trigger: 'change' }],
  priority: [{ required: true, message: '请选择优先级', trigger: 'change' }],
  method: [{ required: true, message: '请选择请求方法', trigger: 'change' }],
  url: [
    {
      validator(rule, value, callback) {
        if (form.case_type === 'scenario') return callback()
        const raw = String(value || '').trim()
        if (!raw) return callback(new Error('请输入请求 URL'))
        if (!isValidRequestUrl(raw)) {
          return callback(new Error('URL 需以 / 开头，或为 http(s) 完整地址'))
        }
        return callback()
      },
      trigger: 'blur',
    },
  ],
}

function buildParams() {
  const params = {
    project: props.projectId,
    page: pagination.page,
    page_size: pagination.pageSize,
  }
  if (filters.search.trim()) params.search = filters.search.trim()
  if (filters.test_type) params.test_type = filters.test_type
  if (filters.case_type) params.case_type = filters.case_type
  if (filters.source) params.source = filters.source
  return params
}

async function loadCases() {
  if (!props.projectId) {
    cases.value = []
    pagination.total = 0
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await apiTestingApi.listCases(buildParams())
    cases.value = Array.isArray(data?.results) ? data.results : []
    pagination.total = Number(data?.count ?? cases.value.length)
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
  filters.test_type = ''
  filters.case_type = ''
  filters.source = ''
  pagination.page = 1
  loadCases()
}

async function loadFormOptions() {
  if (!props.projectId) return
  optionsLoading.value = true
  const [endpointResult, moduleResult] = await Promise.allSettled([
    apiTestingApi.listEndpoints({ project: props.projectId, page_size: 200, is_active: true }),
    apiTestingApi.listModules({ project: props.projectId, page_size: 200 }),
  ])
  endpointOptions.value =
    endpointResult.status === 'fulfilled' && Array.isArray(endpointResult.value?.results)
      ? endpointResult.value.results
      : []
  moduleOptions.value =
    moduleResult.status === 'fulfilled' && Array.isArray(moduleResult.value?.results)
      ? moduleResult.value.results
      : []
  optionsLoading.value = false
}

function resetForm() {
  Object.assign(form, {
    name: '',
    case_type: 'endpoint',
    test_type: 'positive',
    priority: 2,
    description: '',
    endpoint: null,
    module: null,
    is_active: true,
    method: 'GET',
    url: '',
    paramsText: '',
    headersText: '',
    bodyText: '',
    rawRequestText: '',
  })
  assertionRows.value = []
  Object.assign(jsonErrors, { params: '', headers: '', body: '', raw: '' })
}

function clearJsonErrors() {
  Object.assign(jsonErrors, { params: '', headers: '', body: '', raw: '' })
}

function openCreate() {
  drawerMode.value = 'create'
  editingCase.value = null
  resetForm()
  drawerVisible.value = true
  loadFormOptions()
  nextTick(() => formRef.value?.clearValidate())
}

async function openEdit(row) {
  drawerMode.value = 'edit'
  editingCase.value = row
  resetForm()
  drawerVisible.value = true
  loadFormOptions()
  try {
    const detail = await apiTestingApi.retrieveCase(row.id)
    editingCase.value = detail
    applyCase(detail)
  } catch (error) {
    ElMessage.error(error?.message || '用例详情加载失败，已使用列表数据')
    applyCase(row)
  }
  nextTick(() => formRef.value?.clearValidate())
}

function applyCase(detail) {
  form.name = detail.name || ''
  form.case_type = detail.case_type || 'endpoint'
  form.test_type = detail.test_type || 'positive'
  form.priority = detail.priority ?? 2
  form.description = detail.description || ''
  form.endpoint = detail.endpoint ?? null
  form.module = detail.module ?? null
  form.is_active = detail.is_active !== false
  if (form.case_type === 'scenario') {
    form.rawRequestText = JSON.stringify(detail.request_config || {}, null, 2)
  } else {
    Object.assign(form, requestConfigToForm(detail.request_config))
  }
  assertionRows.value = normalizeAssertionRows(detail.assertions)
}

function handleDrawerClosed() {
  editingCase.value = null
  clearJsonErrors()
}

function handleCaseTypeChange(value) {
  if (value === 'scenario' && !form.rawRequestText.trim()) {
    form.rawRequestText = JSON.stringify({ steps: [] }, null, 2)
  }
}

function addAssertion() {
  assertionRows.value.push({
    type: 'status_code',
    json_path: '',
    expected: '200',
    operator: 'equals',
  })
}

function removeAssertion(index) {
  assertionRows.value.splice(index, 1)
}

function isPathDisabled(row) {
  return ['status_code', 'response_time_lt', 'header_present'].includes(row?.type)
}

function isOperatorDisabled(row) {
  return ['status_code', 'header_present'].includes(row?.type)
}

function handleAssertionTypeChange(row) {
  row.operator = getOperatorForAssertionType(row.type)
  if (isPathDisabled(row)) row.json_path = ''
  if (row.type === 'status_code' && !String(row.expected ?? '').trim()) row.expected = '200'
}

function handleAssertionOperatorChange(row) {
  row.type = getAssertionTypeForOperator(row.operator)
  if (isPathDisabled(row)) row.json_path = ''
}

function formatField(field) {
  const key = field === 'raw' ? 'rawRequestText' : `${field}Text`
  const result = formatJsonText(form[key])
  if (result.ok) {
    form[key] = result.text
    jsonErrors[field] = ''
    ElMessage.success('已格式化 JSON')
  } else {
    jsonErrors[field] = result.message
    ElMessage.error(result.message)
  }
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

  clearJsonErrors()
  let requestConfig
  if (form.case_type === 'scenario') {
    const parsed = validateJsonText(form.rawRequestText, {
      allowEmpty: false,
      label: '场景 request_config ',
    })
    if (!parsed.valid) {
      jsonErrors.raw = parsed.message
      ElMessage.error(parsed.message)
      return
    }
    if (
      !parsed.value ||
      typeof parsed.value !== 'object' ||
      Array.isArray(parsed.value) ||
      !Array.isArray(parsed.value.steps) ||
      !parsed.value.steps.length
    ) {
      jsonErrors.raw = '场景用例需要 request_config.steps 非空数组'
      ElMessage.error(jsonErrors.raw)
      return
    }
    requestConfig = parsed.value
  } else {
    const result = buildRequestConfig({
      method: form.method,
      url: form.url,
      paramsText: form.paramsText,
      headersText: form.headersText,
      bodyText: form.bodyText,
    })
    Object.assign(jsonErrors, result.fieldErrors)
    if (!result.ok) {
      ElMessage.error(result.errors[0] || '请求配置不合法')
      return
    }
    requestConfig = result.config
  }

  const assertionErrors = validateAssertionRows(assertionRows.value)
  if (assertionErrors.length) {
    ElMessage.error(assertionErrors[0])
    return
  }

  const payload = {
    project: props.projectId,
    name: form.name.trim(),
    case_type: form.case_type,
    test_type: form.test_type,
    priority: form.priority,
    description: form.description,
    is_active: form.is_active,
    endpoint: form.endpoint || null,
    module: form.module || null,
    request_config: requestConfig,
    assertions: buildAssertionsPayload(assertionRows.value),
    extract: editingCase.value?.extract || {},
    hooks: editingCase.value?.hooks || {},
    source: editingCase.value?.source || 'manual',
  }

  submitting.value = true
  try {
    if (drawerMode.value === 'edit' && editingCase.value?.id) {
      await apiTestingApi.updateCase(editingCase.value.id, payload)
      ElMessage.success('用例已保存')
    } else {
      await apiTestingApi.createCase(payload)
      ElMessage.success('用例已创建')
    }
    drawerVisible.value = false
    await loadCases()
    emit('changed')
  } catch (error) {
    ElMessage.error(error?.message || '用例保存失败')
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row) {
  deletingId.value = row.id
  try {
    await apiTestingApi.removeCase(row.id)
    ElMessage.success('用例已删除')
    if (cases.value.length === 1 && pagination.page > 1) pagination.page -= 1
    await loadCases()
    emit('changed')
  } catch (error) {
    ElMessage.error(error?.message || '删除用例失败')
  } finally {
    deletingId.value = null
  }
}

async function handleGenerateScript(row) {
  scriptCase.value = row
  scriptVisible.value = true
  scriptLoading.value = true
  scriptError.value = ''
  scriptYaml.value = ''
  try {
    const data = await apiTestingApi.generateScript(row.id)
    scriptYaml.value = data?.script_yaml || ''
    if (!scriptYaml.value) scriptError.value = '后端未返回脚本内容'
  } catch (error) {
    scriptError.value = error?.message || '脚本生成失败'
  } finally {
    scriptLoading.value = false
  }
}

async function copyScript() {
  const text = scriptYaml.value
  if (!text) return
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = text
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
  if (!scriptYaml.value) return
  const name = (scriptCase.value?.name || 'api-case').replace(/[\\/:*?"<>|]+/g, '_')
  downloadText(scriptYaml.value, `${name}.yaml`, 'application/x-yaml;charset=utf-8')
}

async function handleRun(row) {
  runningCaseId.value = row.id
  try {
    const data = await apiTestingApi.runCase(row.id, {})
    const executionId = data?.execution_id || data?.task_id
    if (!executionId) throw new Error('后端未返回执行 ID')
    progressExecutionId.value = executionId
    progressTitle.value = `单用例执行 · ${row.name}`
    progressVisible.value = true
    ElMessage.success('已提交执行，正在跟踪进度')
    emit('execution-created')
  } catch (error) {
    ElMessage.error(error?.message || '用例执行失败')
  } finally {
    runningCaseId.value = null
  }
}

function handleOpenProgressDetail(executionId) {
  progressVisible.value = false
  if (executionId) emit('open-execution', executionId)
}

watch(
  () => props.projectId,
  () => {
    pagination.page = 1
    loadCases()
  },
)

watch(
  () => props.refreshKey,
  () => loadCases(),
)

onMounted(loadCases)
</script>

<style scoped>
.cases-pane {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.case-desc {
  margin-top: 3px;
  font-size: 12px;
  color: var(--aits-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.case-form {
  padding-right: 6px;
}

.form-section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 6px 0 14px;
  padding-left: 10px;
  border-left: 3px solid var(--aits-primary);
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 18px;
}

.form-grid__full {
  grid-column: 1 / -1;
}

.json-field {
  width: 100%;
}

.json-field__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
}

.json-textarea :deep(.el-textarea__inner) {
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12.5px;
  line-height: 1.6;
}

.script-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.yaml-block {
  margin: 0;
  padding: 14px;
  max-height: 460px;
  overflow: auto;
  border-radius: 8px;
  background: #0f172a;
  color: #e2e8f0;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12.5px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}

.mt-8 {
  margin-top: 8px;
}
</style>
