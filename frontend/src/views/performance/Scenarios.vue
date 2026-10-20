<template>
  <div class="scenarios-pane">
    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
      description="场景列表加载失败，请稍后重试或检查后端服务。"
    />

    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="filters.search"
            class="filter-input"
            placeholder="搜索场景名称 / 描述"
            :prefix-icon="Search"
            clearable
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
          <el-select
            v-model="filters.source_type"
            class="filter-select"
            placeholder="来源类型"
            clearable
            @change="handleSearch"
          >
            <el-option
              v-for="option in SCENARIO_SOURCE_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-button :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </div>
        <div class="toolbar__right">
          <span class="text-small text-muted">共 {{ pagination.total }} 个压测场景</span>
          <el-button :icon="Refresh" :loading="loading" @click="loadScenarios">刷新</el-button>
          <el-button type="primary" :icon="Plus" @click="openCreate">新建场景</el-button>
        </div>
      </div>

      <DataTable
        v-model:page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :data="scenarios"
        :loading="loading"
        :total="pagination.total"
        row-key="id"
        empty-text="暂无压测场景"
        @change="loadScenarios"
      >
        <el-table-column label="场景名称" min-width="210" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" underline="never" @click="openEdit(row)">
              {{ row.name }}
            </el-link>
            <div v-if="row.description" class="scenario-desc">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="来源" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag
              size="small"
              effect="plain"
              :type="getScenarioSourceMeta(row.source_type).tagType"
            >
              {{ getScenarioSourceMeta(row.source_type).label }}
            </el-tag>
            <span class="source-name">{{ describeScenarioSource(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="接口数" width="86" align="center">
          <template #default="{ row }">{{ formatNumber(row.endpoint_count) }}</template>
        </el-table-column>
        <el-table-column label="负载配置" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.config_name || '未绑定，使用默认负载' }}</template>
        </el-table-column>
        <el-table-column label="变量" width="86" align="center">
          <template #default="{ row }">
            <el-tag v-if="variableCount(row.variables)" size="small" effect="plain" type="info">
              {{ variableCount(row.variables) }} 项
            </el-tag>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="86">
          <template #default="{ row }">
            <StatusTag :status="row.is_active ? 'active' : 'inactive'" />
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="160">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="270" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openRun(row)">运行</el-button>
            <el-button link type="primary" :loading="scriptLoadingId === row.id" @click="openScript(row)">
              生成脚本
            </el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <ConfirmButton
              link
              type="danger"
              text="删除"
              :content="`确定删除场景「${row.name}」吗？该场景关联的执行记录与 AI 诊断也会一并删除。`"
              :loading="deletingId === row.id"
              @confirm="handleDelete(row)"
            />
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            title="暂无压测场景"
            description="压测场景把 API 套件 / 用例或自定义 locustfile 与负载配置组合起来，可一键运行并查看 TPS 与延迟。"
          >
            <el-button type="primary" :icon="Plus" @click="openCreate">新建场景</el-button>
            <el-button @click="emit('switch-tab', 'configs')">先去创建负载配置</el-button>
          </EmptyState>
        </template>
      </DataTable>
    </div>

    <!-- 新建 / 编辑场景 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新建压测场景' : '编辑压测场景'"
      width="860px"
      :close-on-click-modal="false"
      @closed="handleDialogClosed"
    >
      <el-alert v-if="formError" :title="formError" type="error" show-icon :closable="false" class="mb-16" />
      <el-alert
        v-if="sourceOptionsError"
        :title="sourceOptionsError"
        type="warning"
        show-icon
        :closable="false"
        class="mb-16"
        description="关联 API 项目的套件/用例可能不完整，仍可选择本项目资源或使用自定义脚本。"
      />

      <el-form ref="formRef" :model="form" :rules="rules" label-width="104px" @submit.prevent>
        <div class="form-grid">
          <el-form-item label="场景名称" prop="name" class="form-grid__full">
            <el-input
              v-model="form.name"
              maxlength="255"
              show-word-limit
              placeholder="例如：商品列表压测"
            />
          </el-form-item>
          <el-form-item label="场景来源" prop="source_type">
            <el-radio-group v-model="form.source_type" @change="handleSourceTypeChange">
              <el-radio-button
                v-for="option in SCENARIO_SOURCE_OPTIONS"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="启用状态">
            <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
          </el-form-item>

          <el-form-item
            v-if="form.source_type === 'api_suite'"
            label="来源套件"
            prop="source_suite"
            class="form-grid__full"
          >
            <el-select
              v-model="form.source_suite"
              style="width: 100%"
              filterable
              clearable
              :loading="sourceOptionsLoading"
              placeholder="选择 API 套件（含关联 API 项目）"
            >
              <el-option
                v-for="suite in suiteOptions"
                :key="suite.id"
                :label="`${suite.__projectName} / ${suite.name}（${suite.case_count ?? 0} 条用例）`"
                :value="suite.id"
              />
            </el-select>
            <div class="field-help">
              性能项目可在项目设置中通过「关联 API 项目」复用接口测试套件；当前可用
              {{ suiteOptions.length }} 个套件。
            </div>
          </el-form-item>

          <el-form-item
            v-if="form.source_type === 'api_case'"
            label="来源用例"
            prop="source_case"
            class="form-grid__full"
          >
            <el-select
              v-model="form.source_case"
              style="width: 100%"
              filterable
              clearable
              :loading="sourceOptionsLoading"
              placeholder="选择 API 用例（含关联 API 项目）"
            >
              <el-option
                v-for="testCase in caseOptions"
                :key="testCase.id"
                :label="`${testCase.__projectName} / ${testCase.name}`"
                :value="testCase.id"
              />
            </el-select>
            <div class="field-help">
              单个用例会生成一个 @task 方法；当前可用 {{ caseOptions.length }} 条用例。
            </div>
          </el-form-item>

          <el-form-item
            v-if="form.source_type === 'custom_script'"
            label="Locust 脚本"
            prop="custom_script"
            class="form-grid__full"
          >
            <el-input
              v-model="form.custom_script"
              type="textarea"
              :rows="10"
              class="mono-input"
              placeholder="from locust import HttpUser, task, between&#10;&#10;class DemoUser(HttpUser):&#10;    @task&#10;    def index(self):&#10;        self.client.get('/')"
            />
            <div class="field-help">
              必填，且必须包含 HttpUser 用户类；保存后可通过「生成脚本」预览后端补全后的完整 locustfile。
            </div>
          </el-form-item>

          <el-form-item label="负载配置" prop="config">
            <el-select
              v-model="form.config"
              style="width: 100%"
              clearable
              filterable
              :loading="configOptionsLoading"
              placeholder="不绑定则使用场景 / 平台默认负载"
            >
              <el-option
                v-for="config in configs"
                :key="config.id"
                :label="`${config.name}（${config.users} 用户 / ${config.duration_seconds}s）`"
                :value="config.id"
              />
            </el-select>
            <div v-if="configError" class="field-help field-help--error">{{ configError }}</div>
          </el-form-item>

          <el-form-item label="接口数量" prop="endpoint_count">
            <el-input-number
              v-model="form.endpoint_count"
              :min="0"
              :step="1"
              :precision="0"
              style="width: 100%"
            />
            <div class="field-help">0 表示由后端按来源自动估算。</div>
          </el-form-item>

          <el-form-item label="变量 JSON" prop="variablesText" class="form-grid__full">
            <el-input
              v-model="form.variablesText"
              type="textarea"
              :rows="4"
              class="mono-input"
              placeholder='{"host": "https://demo.example.com", "token": "xxx"}'
            />
            <div class="field-help">
              <span>必须是 JSON 对象，脚本生成时可用 ${变量名} 占位。</span>
              <el-button link type="primary" size="small" @click="handleFormatVariables">
                格式化 JSON
              </el-button>
            </div>
          </el-form-item>

          <el-form-item label="场景描述" class="form-grid__full">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="2"
              maxlength="500"
              show-word-limit
              placeholder="压测目标、业务链路等"
            />
          </el-form-item>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">保存场景</el-button>
      </template>
    </el-dialog>

    <!-- 生成脚本预览 -->
    <el-dialog
      v-model="scriptDialogVisible"
      :title="`Locustfile 预览${scriptTarget ? ' · ' + scriptTarget.name : ''}`"
      width="860px"
      :close-on-click-modal="false"
    >
      <div v-loading="scriptLoading" class="script-body">
        <el-alert v-if="scriptError" :title="scriptError" type="error" show-icon :closable="false" />
        <template v-else>
          <div class="script-meta">
            <span class="text-small text-muted">
              由后端按场景来源自动生成并通过语法校验；接口数：
              {{ formatNumber(scriptEndpointCount) }}
            </span>
            <div class="script-meta__actions">
              <el-button size="small" :icon="CopyDocument" :disabled="!scriptText" @click="handleCopyScript">
                复制
              </el-button>
              <el-button
                size="small"
                :icon="Download"
                :disabled="!scriptText"
                @click="handleDownloadScript"
              >
                下载
              </el-button>
            </div>
          </div>
          <pre v-if="scriptText" class="script-preview">{{ scriptText }}</pre>
          <EmptyState v-else title="暂无脚本内容" description="该场景还没有可生成的脚本，请检查来源配置。" />
        </template>
      </div>
      <template #footer>
        <el-button @click="scriptDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 运行场景 -->
    <el-dialog
      v-model="runDialogVisible"
      title="运行压测场景"
      width="560px"
      :close-on-click-modal="false"
    >
      <template v-if="runTarget">
        <el-alert v-if="runError" :title="runError" type="error" show-icon :closable="false" class="mb-16" />
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="场景">{{ runTarget.name }}</el-descriptions-item>
          <el-descriptions-item label="来源">
            {{ getScenarioSourceMeta(runTarget.source_type).label }} ·
            {{ describeScenarioSource(runTarget) }}
          </el-descriptions-item>
          <el-descriptions-item label="接口数">
            {{ formatNumber(runTarget.endpoint_count) }}
          </el-descriptions-item>
        </el-descriptions>

        <el-form label-width="92px" class="mt-16" @submit.prevent>
          <el-form-item label="负载配置">
            <el-select
              v-model="runConfigId"
              style="width: 100%"
              clearable
              filterable
              :loading="configOptionsLoading"
              placeholder="不选择则使用场景绑定 / 平台默认负载"
            >
              <el-option
                v-for="config in configs"
                :key="config.id"
                :label="`${config.name}（${config.users} 用户 / ${config.duration_seconds}s）`"
                :value="config.id"
              />
            </el-select>
          </el-form-item>
        </el-form>

        <div v-if="selectedRunConfig" class="run-config-summary">
          <el-tag size="small" effect="plain" type="info">{{ selectedRunConfig.name }}</el-tag>
          <span>
            并发 {{ selectedRunConfig.users }} · 加压 {{ selectedRunConfig.spawn_rate }}/s ·
            持续 {{ selectedRunConfig.duration_seconds }}s
          </span>
          <span v-if="selectedRunConfig.host" class="mono">{{ selectedRunConfig.host }}</span>
        </div>
        <p class="text-small text-muted">
          提交后返回 202，页面会优先通过 WebSocket 接收执行进度；连接不可用时自动降级为 2 秒轮询，
          直至执行进入终态。
        </p>
      </template>
      <template #footer>
        <el-button @click="runDialogVisible = false">取消</el-button>
        <el-button type="primary" :icon="VideoPlay" :loading="runSubmitting" @click="confirmRun">
          开始压测
        </el-button>
      </template>
    </el-dialog>

    <!-- 执行进度 -->
    <el-dialog
      v-model="progressVisible"
      title="压测执行进度"
      width="560px"
      :close-on-click-modal="false"
      @closed="handleProgressClosed"
    >
      <div v-if="progressTarget" class="progress-body">
        <div class="progress-title">
          <span>{{ progressTarget.name }}</span>
          <el-tag :type="watcherState.tagType" effect="light">{{ watcherState.statusLabel || '等待中' }}</el-tag>
        </div>
        <el-progress
          :percentage="watcherState.progress"
          :status="progressStatus"
          :stroke-width="12"
          text-inside
        />
        <p class="progress-message">{{ watcherState.message || '等待执行器返回进度…' }}</p>
        <div class="progress-meta">
          <span class="text-small text-muted">
            进度通道：{{ channelLabel }}
            <template v-if="watcherState.executionId"> · 执行 ID：{{ watcherState.executionId }}</template>
          </span>
        </div>
        <el-alert
          v-if="watcherState.error"
          :title="watcherState.error"
          type="warning"
          show-icon
          :closable="false"
        />

        <div v-if="progressResult" class="progress-stats">
          <div class="progress-stat">
            <span>平均 TPS</span>
            <strong>{{ formatTps(progressResult.avg_tps) }}</strong>
          </div>
          <div class="progress-stat">
            <span>P95</span>
            <strong>{{ formatLatency(progressResult.p95_response_time) }}</strong>
          </div>
          <div class="progress-stat">
            <span>错误率</span>
            <strong :class="{ 'text-danger': Number(progressResult.error_rate) > 0.01 }">
              {{ formatErrorRate(progressResult.error_rate) }}
            </strong>
          </div>
          <div class="progress-stat">
            <span>耗时</span>
            <strong>{{ formatDurationText(progressResult.duration_ms) }}</strong>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button v-if="!watcherState.running" @click="progressVisible = false">关闭</el-button>
        <el-button v-else @click="handleProgressClosed">停止跟踪</el-button>
        <el-button
          v-if="isTerminal && progressResult"
          type="primary"
          @click="openProgressExecution"
        >
          查看执行记录
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  CopyDocument,
  Download,
  Plus,
  Refresh,
  RefreshLeft,
  Search,
  VideoPlay,
} from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import EmptyState from '@/components/EmptyState.vue'
import StatusTag from '@/components/StatusTag.vue'
import ConfirmButton from '@/components/ConfirmButton.vue'

import { apiTestingApi } from '@/api/apiTesting'
import { performanceApi } from '@/api/performance'
import { useProjectStore } from '@/stores/project'
import { downloadText } from '@/utils/download'
import { formatDateTime, formatNumber } from '@/utils/format'
import {
  SCENARIO_SOURCE_OPTIONS,
  buildScriptFilename,
  describeScenarioSource,
  formatDurationText,
  formatErrorRate,
  formatJsonText,
  formatLatency,
  formatTps,
  getScenarioSourceMeta,
  isExecutionTerminal,
  readErrorMessage,
  scenarioToForm,
  validateCustomScript,
  validateJsonObject,
  validateScenarioForm,
} from './utils'
import { useExecutionWatcher } from './utils/task'

const props = defineProps({
  projectId: { type: [Number, String], default: null },
  refreshKey: { type: Number, default: 0 },
  createKey: { type: Number, default: 0 },
})

const emit = defineEmits([
  'changed',
  'run-created',
  'open-execution',
  'switch-tab',
  'create-consumed',
])

const projectStore = useProjectStore()

const scenarios = ref([])
const loading = ref(false)
const errorMessage = ref('')
const filters = reactive({ search: '', source_type: '' })
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

const configs = ref([])
const configOptionsLoading = ref(false)
const configError = ref('')

const suiteOptions = ref([])
const caseOptions = ref([])
const sourceOptionsLoading = ref(false)
const sourceOptionsError = ref('')

const dialogVisible = ref(false)
const dialogMode = ref('create')
const editingId = ref(null)
const formRef = ref(null)
const form = reactive(createEmptyForm())
const submitting = ref(false)
const formError = ref('')
const deletingId = ref(null)

const scriptDialogVisible = ref(false)
const scriptLoading = ref(false)
const scriptLoadingId = ref(null)
const scriptError = ref('')
const scriptText = ref('')
const scriptEndpointCount = ref(0)
const scriptTarget = ref(null)

const runDialogVisible = ref(false)
const runTarget = ref(null)
const runConfigId = ref(null)
const runSubmitting = ref(false)
const runError = ref('')

const progressVisible = ref(false)
const progressTarget = ref(null)
const progressResult = ref(null)

const watcher = useExecutionWatcher({ onFinish: handleWatcherFinish })
const watcherState = watcher.state

const selectedRunConfig = computed(
  () => configs.value.find((item) => item.id === runConfigId.value) || null,
)

const progressStatus = computed(() => {
  const status = progressResult.value?.status || watcherState.status
  if (status === 'passed') return 'success'
  if (status === 'failed' || status === 'error') return 'exception'
  if (status === 'cancelled') return 'warning'
  return undefined
})

const isTerminal = computed(
  () => isExecutionTerminal(progressResult.value?.status) || isExecutionTerminal(watcherState.status),
)

const channelLabel = computed(
  () =>
    ({
      ws: 'WebSocket 实时进度',
      polling: '轮询（2s）',
      done: '已完成',
      stopped: '已停止跟踪',
      timeout: '跟踪超时',
      idle: '未开始',
    })[watcherState.channel] || watcherState.channel,
)

function createEmptyForm() {
  return {
    name: '',
    description: '',
    source_type: 'api_suite',
    source_suite: null,
    source_case: null,
    custom_script: '',
    endpoint_count: 0,
    config: null,
    variablesText: '{}',
    is_active: true,
  }
}

const rules = {
  name: [{ required: true, message: '请输入场景名称', trigger: 'blur' }],
  source_suite: [
    {
      validator: (rule, value, callback) => {
        if (form.source_type === 'api_suite' && !value) {
          callback(new Error('请选择来源 API 套件'))
          return
        }
        callback()
      },
      trigger: 'change',
    },
  ],
  source_case: [
    {
      validator: (rule, value, callback) => {
        if (form.source_type === 'api_case' && !value) {
          callback(new Error('请选择来源 API 用例'))
          return
        }
        callback()
      },
      trigger: 'change',
    },
  ],
  custom_script: [
    {
      validator: (rule, value, callback) => {
        if (form.source_type !== 'custom_script') {
          callback()
          return
        }
        const result = validateCustomScript(value)
        if (!result.valid) {
          callback(new Error(result.message))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
  variablesText: [
    {
      validator: (rule, value, callback) => {
        const result = validateJsonObject(value, { label: '变量' })
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

function variableCount(variables) {
  return variables && typeof variables === 'object' && !Array.isArray(variables)
    ? Object.keys(variables).length
    : 0
}

function projectLabel(projectId) {
  if (Number(projectId) === Number(props.projectId)) {
    return projectStore.currentProjectName || `项目 #${projectId}`
  }
  const project = projectStore.projects.find((item) => item.id === Number(projectId))
  return project?.name || `项目 #${projectId}`
}

function linkedProjectIds() {
  const ids = []
  const push = (value) => {
    const id = Number(value)
    if (Number.isFinite(id) && id > 0 && !ids.includes(id)) ids.push(id)
  }
  push(props.projectId)
  const current = projectStore.currentProject
  const linked = Array.isArray(current?.linked_api_projects) ? current.linked_api_projects : []
  linked.forEach(push)
  return ids
}

async function loadScenarios() {
  if (!props.projectId) {
    scenarios.value = []
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
    if (filters.source_type) params.source_type = filters.source_type
    const data = await performanceApi.listScenarios(params)
    scenarios.value = Array.isArray(data?.results) ? data.results : []
    pagination.total = Number(data?.count ?? scenarios.value.length)
  } catch (error) {
    scenarios.value = []
    pagination.total = 0
    errorMessage.value = readErrorMessage(error, '压测场景加载失败')
  } finally {
    loading.value = false
  }
}

async function loadConfigOptions() {
  if (!props.projectId) {
    configs.value = []
    return
  }
  configOptionsLoading.value = true
  configError.value = ''
  try {
    const data = await performanceApi.listConfigs({
      project: props.projectId,
      page_size: 200,
      ordering: '-created_at',
    })
    configs.value = Array.isArray(data?.results) ? data.results : []
  } catch (error) {
    configs.value = []
    configError.value = readErrorMessage(error, '负载配置加载失败')
  } finally {
    configOptionsLoading.value = false
  }
}

/** 拉取本项目 + 关联 API 项目的套件与用例，供来源选择。 */
async function loadSourceOptions() {
  if (!props.projectId) {
    suiteOptions.value = []
    caseOptions.value = []
    return
  }
  sourceOptionsLoading.value = true
  sourceOptionsError.value = ''
  const ids = linkedProjectIds()
  const requests = []
  ids.forEach((projectId) => {
    requests.push({
      kind: 'suite',
      projectId,
      promise: apiTestingApi.listSuites({ project: projectId, page_size: 200 }),
    })
    requests.push({
      kind: 'case',
      projectId,
      promise: apiTestingApi.listCases({ project: projectId, page_size: 200 }),
    })
  })
  const results = await Promise.allSettled(requests.map((item) => item.promise))
  const suites = []
  const cases = []
  const failures = []
  results.forEach((result, index) => {
    const meta = requests[index]
    if (result.status !== 'fulfilled') {
      failures.push(
        readErrorMessage(
          result.reason,
          `${projectLabel(meta.projectId)} 的${meta.kind === 'suite' ? '套件' : '用例'}加载失败`,
        ),
      )
      return
    }
    const data = result.value
    const list = Array.isArray(data?.results) ? data.results : Array.isArray(data) ? data : []
    const __projectName = projectLabel(meta.projectId)
    list.forEach((item) => {
      if (meta.kind === 'suite') suites.push({ ...item, __projectName })
      else cases.push({ ...item, __projectName })
    })
  })
  suiteOptions.value = suites
  caseOptions.value = cases
  if (failures.length) sourceOptionsError.value = failures[0]
  sourceOptionsLoading.value = false
}

function handleSearch() {
  pagination.page = 1
  loadScenarios()
}

function handleReset() {
  filters.search = ''
  filters.source_type = ''
  pagination.page = 1
  loadScenarios()
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
  loadSourceOptions()
  if (!configs.value.length) loadConfigOptions()
}

function openEdit(row) {
  dialogMode.value = 'edit'
  editingId.value = row.id
  formError.value = ''
  Object.assign(form, scenarioToForm(row))
  dialogVisible.value = true
  loadSourceOptions()
  if (!configs.value.length) loadConfigOptions()
}

function handleDialogClosed() {
  formRef.value?.clearValidate()
  formError.value = ''
}

function handleSourceTypeChange() {
  formRef.value?.clearValidate(['source_suite', 'source_case', 'custom_script'])
  formError.value = ''
}

function handleFormatVariables() {
  const result = formatJsonText(form.variablesText)
  if (!result.ok) {
    formError.value = result.message
    return
  }
  form.variablesText = result.text || '{}'
  formError.value = ''
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  const result = validateScenarioForm(form)
  if (!result.valid) {
    formError.value = result.errors[0]
    return
  }
  submitting.value = true
  formError.value = ''
  try {
    if (dialogMode.value === 'edit' && editingId.value) {
      await performanceApi.updateScenario(editingId.value, result.payload)
      ElMessage.success('压测场景已更新')
    } else {
      await performanceApi.createScenario({ project: props.projectId, ...result.payload })
      ElMessage.success('压测场景已创建')
    }
    dialogVisible.value = false
    await loadScenarios()
    emit('changed')
  } catch (error) {
    formError.value = readErrorMessage(error, '压测场景保存失败')
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row) {
  deletingId.value = row.id
  try {
    await performanceApi.removeScenario(row.id)
    ElMessage.success(`已删除场景「${row.name}」`)
    if (scenarios.value.length === 1 && pagination.page > 1) pagination.page -= 1
    await loadScenarios()
    emit('changed')
  } catch (error) {
    ElMessage.error(readErrorMessage(error, '删除压测场景失败'))
  } finally {
    deletingId.value = null
  }
}

async function openScript(row) {
  scriptTarget.value = row
  scriptDialogVisible.value = true
  scriptText.value = ''
  scriptEndpointCount.value = 0
  scriptError.value = ''
  scriptLoading.value = true
  scriptLoadingId.value = row.id
  try {
    const data = await performanceApi.generateScript(row.id)
    scriptText.value = typeof data?.script === 'string' ? data.script : ''
    scriptEndpointCount.value = Number(data?.endpoint_count ?? row.endpoint_count ?? 0)
    if (scriptEndpointCount.value && row.endpoint_count !== scriptEndpointCount.value) {
      row.endpoint_count = scriptEndpointCount.value
    }
    if (!scriptText.value) scriptError.value = '后端返回的脚本为空'
  } catch (error) {
    scriptError.value = readErrorMessage(error, '脚本生成失败')
  } finally {
    scriptLoading.value = false
    scriptLoadingId.value = null
  }
}

async function handleCopyScript() {
  if (!scriptText.value) return
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(scriptText.value)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = scriptText.value
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    ElMessage.success('脚本已复制到剪贴板')
  } catch (error) {
    ElMessage.error(`复制失败：${error?.message || '浏览器不支持剪贴板'}`)
  }
}

function handleDownloadScript() {
  if (!scriptText.value) return
  downloadText(
    scriptText.value,
    buildScriptFilename(scriptTarget.value || {}),
    'text/x-python;charset=utf-8',
  )
}

function openRun(row) {
  runTarget.value = row
  runConfigId.value = row.config ?? null
  runError.value = ''
  runDialogVisible.value = true
  if (!configs.value.length) loadConfigOptions()
}

async function confirmRun() {
  if (!runTarget.value) return
  runSubmitting.value = true
  runError.value = ''
  try {
    const payload = runConfigId.value ? { config_id: runConfigId.value } : {}
    const result = await performanceApi.runScenario(runTarget.value.id, payload)
    const executionId = result?.execution_id ?? result?.task_id ?? null
    if (!executionId) {
      throw new Error('后端未返回执行 ID，无法跟踪进度')
    }
    runDialogVisible.value = false
    progressTarget.value = runTarget.value
    progressResult.value = null
    progressVisible.value = true
    watcher.start(executionId)
    ElMessage.success('压测任务已提交，正在跟踪执行进度')
    emit('run-created', executionId)
  } catch (error) {
    runError.value = readErrorMessage(error, '压测任务提交失败')
  } finally {
    runSubmitting.value = false
  }
}

async function handleWatcherFinish(execution) {
  const executionId = execution?.id ?? watcherState.executionId
  if (execution) progressResult.value = execution
  if (executionId) {
    try {
      const detail = await performanceApi.retrieveExecution(executionId)
      progressResult.value = detail
    } catch (error) {
      // 保留 WebSocket / 轮询已有的数据，不阻塞终态提示。
    }
  }
  const status = progressResult.value?.status || watcherState.status
  if (status === 'passed') ElMessage.success('压测执行完成，结果已写入执行记录')
  else if (status === 'failed') ElMessage.warning('压测执行结束，但未达到通过阈值（错误率或 P95）')
  else if (status === 'error') ElMessage.error('压测执行异常，请查看执行记录中的错误信息')
  else if (status === 'cancelled') ElMessage.info('压测执行已取消')
  await loadScenarios()
  emit('changed')
  emit('run-created', executionId)
}

function handleProgressClosed() {
  watcher.stop()
}

function openProgressExecution() {
  const id = progressResult.value?.id ?? watcherState.executionId
  progressVisible.value = false
  if (id) emit('open-execution', id)
}

watch(() => props.projectId, () => {
  pagination.page = 1
  loadScenarios()
  configs.value = []
  suiteOptions.value = []
  caseOptions.value = []
})
watch(() => props.refreshKey, loadScenarios)
watch(
  () => props.createKey,
  (value) => {
    if (!value) return
    openCreate()
    emit('create-consumed')
  },
  { immediate: true },
)

onMounted(() => {
  loadScenarios()
  loadConfigOptions()
})
</script>

<style scoped>
.scenarios-pane {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.scenario-desc {
  margin-top: 2px;
  font-size: 12px;
  color: var(--aits-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-name {
  margin-left: 6px;
  font-size: 12.5px;
  color: #334155;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 18px;
}

.form-grid__full {
  grid-column: 1 / -1;
}

.field-help {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  margin-top: 4px;
  font-size: 12px;
  color: var(--aits-text-secondary);
  line-height: 1.5;
}

.field-help--error {
  color: #dc2626;
}

.mono-input :deep(textarea) {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12.5px;
}

.script-body {
  min-height: 240px;
}

.script-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.script-meta__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.script-preview {
  max-height: 480px;
  margin: 0;
  padding: 14px;
  overflow: auto;
  color: #e2e8f0;
  background: #0f172a;
  border-radius: 8px;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12.5px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.run-config-summary {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  margin-bottom: 10px;
  font-size: 12.5px;
  color: #334155;
  background: #f8fafc;
  border: 1px solid var(--aits-border);
  border-radius: 8px;
}

.run-config-summary .mono {
  color: var(--aits-text-secondary);
}

.progress-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.progress-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}

.progress-message {
  margin: 0;
  font-size: 13px;
  color: var(--aits-text-secondary);
}

.progress-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.progress-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  padding-top: 6px;
}

.progress-stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  background: #f8fafc;
  border: 1px solid var(--aits-border);
  border-radius: 8px;
}

.progress-stat span {
  font-size: 12px;
  color: var(--aits-text-secondary);
}

.progress-stat strong {
  font-size: 16px;
  color: #0f172a;
  font-variant-numeric: tabular-nums;
}

.text-danger {
  color: #dc2626 !important;
}

@media (max-width: 900px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .progress-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
