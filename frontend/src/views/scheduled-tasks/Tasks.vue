<template>
  <div class="tasks">
    <el-alert
      v-if="pageError"
      type="error"
      show-icon
      :closable="false"
      :title="pageError"
      description="任务列表加载失败，请确认后端服务已启动。"
    />

    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="filters.search"
            class="filter-input"
            placeholder="搜索任务名 / Cron"
            clearable
            :prefix-icon="Search"
            @keyup.enter="reload"
            @clear="reload"
          />
          <el-select v-model="filters.project" class="filter-select" clearable placeholder="全部项目" @change="reload">
            <el-option v-for="project in projectStore.projects" :key="project.id" :label="project.name" :value="project.id" />
          </el-select>
          <el-select v-model="filters.suite_type" class="filter-select" clearable placeholder="套件类型" @change="reload">
            <el-option v-for="item in SUITE_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="filters.is_enabled" class="filter-select" clearable placeholder="启用状态" @change="reload">
            <el-option label="已启用" value="true" />
            <el-option label="已停用" value="false" />
          </el-select>
        </div>
        <div class="toolbar__right">
          <el-button :icon="Refresh" :loading="loading" @click="reload">刷新</el-button>
          <el-button type="primary" :icon="Plus" :disabled="!projectStore.projects.length" @click="openCreate">
            新建任务
          </el-button>
        </div>
      </div>

      <DataTable
        :data="rows"
        :loading="loading"
        :total="total"
        :page="page"
        :page-size="pageSize"
        empty-text="暂无定时任务，点击「新建任务」配置 Cron 调度"
        @update:page="handlePageChange"
        @update:page-size="handleSizeChange"
      >
        <el-table-column prop="name" label="任务名称" min-width="170" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="name-cell">
              <span>{{ row.name }}</span>
              <el-tag v-if="row.suite_count" size="small" effect="plain" type="info">{{ row.suite_count }} 套件</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="套件类型" width="130">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="suiteTypeTag(row.suite_type)">
              {{ suiteTypeLabel(row.suite_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="项目" width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.project_name || projectName(row.project) }}</template>
        </el-table-column>
        <el-table-column label="Cron" width="150">
          <template #default="{ row }">
            <div class="mono">{{ row.cron_expression }}</div>
            <div class="text-small text-muted">{{ row.timezone || 'Asia/Shanghai' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="触发条件" width="120">
          <template #default="{ row }">{{ triggerConditionLabel(row.trigger_condition) }}</template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-switch
              :model-value="row.is_enabled"
              :disabled="togglingId === row.id"
              @change="handleToggle(row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="最近运行" width="170">
          <template #default="{ row }">
            <div>{{ formatDateTime(row.last_run_at) }}</div>
            <div class="text-small text-muted">下次 {{ formatDateTime(row.next_run_at) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="330" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" :loading="runningId === row.id" @click="handleRun(row)">
              立即运行
            </el-button>
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" size="small" @click="openLogs(row)">日志</el-button>
            <ConfirmButton
              text="删除"
              link
              size="small"
              :title="`删除定时任务「${row.name}」`"
              content="删除后对应的 Celery Beat 周期任务也会被清理，确定删除？"
              @confirm="handleDelete(row)"
            />
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <el-drawer v-model="drawerVisible" :title="drawerTitle" size="640px" :destroy-on-close="true">
      <el-form label-width="110px" class="drawer-form">
        <el-form-item label="归属项目" required>
          <el-select v-model="form.project" class="w-full" placeholder="选择项目" @change="handleProjectChange">
            <el-option v-for="project in projectStore.projects" :key="project.id" :label="project.name" :value="project.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务名称" required>
          <el-input v-model="form.name" maxlength="255" placeholder="例如：每日回归测试" />
        </el-form-item>
        <el-form-item label="任务描述">
          <el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" />
        </el-form-item>
        <el-form-item label="套件类型" required>
          <el-select v-model="form.suite_type" class="w-full" @change="handleSuiteTypeChange">
            <el-option v-for="item in SUITE_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="测试套件" required>
          <el-select
            v-model="form.suite_ids"
            class="w-full"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            :loading="suiteLoading"
            :disabled="!form.project"
            placeholder="选择要执行的套件（可多选）"
          >
            <el-option
              v-for="suite in suites"
              :key="suite.id"
              :label="suiteOptionLabel(suite)"
              :value="suite.id"
            />
          </el-select>
          <div class="field-hint">
            {{ form.project
              ? `已选 ${form.suite_ids.length} 个套件（按套件类型从对应模块加载）`
              : '请先选择归属项目' }}
          </div>
        </el-form-item>

        <el-form-item label="Cron 表达式" required>
          <div class="cron-field">
            <el-input v-model="form.cron_expression" class="mono-input" placeholder="0 9 * * *" :prefix-icon="Timer" />
            <div class="preset-row">
              <el-button
                v-for="preset in CRON_PRESETS"
                :key="preset.expr"
                size="small"
                plain
                @click="applyCronPreset(preset)"
              >
                {{ preset.label }}
              </el-button>
            </div>
            <div class="cron-preview" :class="{ 'is-invalid': cronPreview && !cronPreview.valid }">
              <div v-if="cronPreviewLoading" class="text-small text-muted">正在解析 Cron…</div>
              <template v-else-if="cronPreview">
                <div v-if="cronPreview.valid" class="cron-preview__ok">
                  <el-icon><CircleCheck /></el-icon>
                  <span>{{ cronPreview.description || '表达式合法' }}</span>
                </div>
                <div v-else class="cron-preview__error">
                  <el-icon><CircleClose /></el-icon>
                  <span>{{ cronPreview.message }}</span>
                </div>
                <div v-if="cronPreview.valid && cronPreview.nextRuns.length" class="cron-preview__runs">
                  <span class="text-small text-muted">未来 {{ cronPreview.nextRuns.length }} 次执行：</span>
                  <ul>
                    <li v-for="run in cronPreview.nextRuns" :key="run" class="mono">{{ run }}</li>
                  </ul>
                </div>
              </template>
              <div v-else-if="cronPreviewError" class="cron-preview__error">
                <el-icon><WarningFilled /></el-icon>
                <span>{{ cronPreviewError }}</span>
              </div>
              <div v-else class="text-small text-muted">输入表达式后自动预览中文描述与未来 5 次执行时间</div>
            </div>
          </div>
        </el-form-item>

        <el-form-item label="时区">
          <el-select v-model="form.timezone" class="w-full" filterable allow-create>
            <el-option v-for="zone in TIMEZONE_OPTIONS" :key="zone" :label="zone" :value="zone" />
          </el-select>
        </el-form-item>
        <el-form-item label="通知条件">
          <el-radio-group v-model="form.trigger_condition">
            <el-radio v-for="item in TRIGGER_CONDITION_OPTIONS" :key="item.value" :value="item.value">
              {{ item.label }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="执行环境">
          <el-select v-model="form.environment" class="w-full" clearable placeholder="不指定（使用套件默认环境）">
            <el-option
              v-for="environment in environments"
              :key="environment.id"
              :label="`${environment.name}${environment.base_url ? ` · ${environment.base_url}` : ''}`"
              :value="environment.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="通知接收人">
          <el-select
            v-model="form.notice_targets"
            class="w-full"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            :loading="receiverLoading"
            clearable
            placeholder="选择项目通知接收对象"
          >
            <el-option
              v-for="receiver in receivers"
              :key="receiver.id"
              :label="`${receiver.name}（${receiver.channel_name || receiver.channel_code}）`"
              :value="receiver.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.suite_type === 'app'" label="App 运行配置">
          <el-input v-model="form.appRunConfigText" type="textarea" :rows="4" placeholder='{"device": "emulator-5554"}' />
          <div class="field-hint">JSON 对象，可留空。</div>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_enabled" />
          <span class="field-hint inline">启用后自动同步 Celery Beat 周期任务</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="drawerVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  CircleCheck,
  CircleClose,
  Plus,
  Refresh,
  Search,
  Timer,
  WarningFilled,
} from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import ConfirmButton from '@/components/ConfirmButton.vue'
import { useProjectStore } from '@/stores/project'
import { scheduledTasksApi } from '@/api/scheduledTasks'
import { notificationsApi } from '@/api/notifications'
import { projectsApi } from '@/api/projects'
import { apiTestingApi } from '@/api/apiTesting'
import { webTestingApi } from '@/api/webTesting'
import { appTestingApi } from '@/api/appTesting'
import { formatDateTime } from '@/utils/format'

import {
  CRON_PRESETS,
  SUITE_TYPE_OPTIONS,
  TIMEZONE_OPTIONS,
  TRIGGER_CONDITION_OPTIONS,
  debounce,
  normalizeCronPreview,
  suiteTypeLabel,
  triggerConditionLabel,
} from './utils/cron'

const router = useRouter()
const projectStore = useProjectStore()

const SUITE_APIS = { api: apiTestingApi, web: webTestingApi, app: appTestingApi }

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const pageError = ref('')
const runningId = ref(null)
const togglingId = ref(null)

const filters = reactive({
  search: '',
  project: projectStore.currentProjectId || '',
  suite_type: '',
  is_enabled: '',
})

const drawerVisible = ref(false)
const mode = ref('create')
const currentId = ref(null)
const saving = ref(false)
const form = reactive(emptyForm())

const suites = ref([])
const suiteLoading = ref(false)
const environments = ref([])
const receivers = ref([])
const receiverLoading = ref(false)

const cronPreview = ref(null)
const cronPreviewLoading = ref(false)
const cronPreviewError = ref('')

const drawerTitle = computed(() => (mode.value === 'create' ? '新建定时任务' : '编辑定时任务'))

function emptyForm(values = {}) {
  return {
    project: projectStore.currentProjectId || null,
    name: '',
    description: '',
    suite_type: 'api',
    suite_ids: [],
    cron_expression: '0 9 * * *',
    timezone: 'Asia/Shanghai',
    trigger_condition: 'always',
    environment: null,
    notice_targets: [],
    is_enabled: true,
    appRunConfigText: '{}',
    ...values,
  }
}

function projectName(id) {
  return projectStore.projects.find((item) => item.id === id)?.name || `项目 #${id}`
}

function suiteTypeTag(type) {
  if (type === 'web') return 'success'
  if (type === 'app') return 'warning'
  return 'primary'
}

function suiteOptionLabel(suite) {
  const base = suite.name || `套件 #${suite.id}`
  return suite.case_count ? `${base}（${suite.case_count} 用例）` : base
}

function requestParams() {
  const params = { page: page.value, page_size: pageSize.value }
  if (filters.search.trim()) params.search = filters.search.trim()
  if (filters.project) params.project = filters.project
  if (filters.suite_type) params.suite_type = filters.suite_type
  if (filters.is_enabled !== '') params.is_enabled = filters.is_enabled
  return params
}

async function load() {
  loading.value = true
  pageError.value = ''
  try {
    const data = await scheduledTasksApi.listTasks(requestParams())
    rows.value = Array.isArray(data?.results) ? data.results : []
    total.value = Number(data?.count ?? rows.value.length)
  } catch (error) {
    rows.value = []
    total.value = 0
    pageError.value = error?.message || '任务列表加载失败'
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

async function loadSuites() {
  suites.value = []
  if (!form.project || !form.suite_type) return
  const api = SUITE_APIS[form.suite_type]
  if (!api) return
  suiteLoading.value = true
  try {
    const data = await api.listSuites({ project: form.project, page_size: 200 })
    suites.value = Array.isArray(data?.results) ? data.results : []
  } catch (error) {
    suites.value = []
    ElMessage.error(error?.message || '套件列表加载失败')
  } finally {
    suiteLoading.value = false
  }
}

async function loadEnvironments() {
  environments.value = []
  if (!form.project) return
  try {
    const data = await projectsApi.listEnvironments({ project: form.project, page_size: 100 })
    environments.value = Array.isArray(data?.results) ? data.results : []
  } catch (error) {
    environments.value = []
  }
}

async function loadReceivers() {
  receivers.value = []
  if (!form.project) return
  receiverLoading.value = true
  try {
    const data = await notificationsApi.listReceivers({ project: form.project, page_size: 100 })
    receivers.value = Array.isArray(data?.results) ? data.results : []
  } catch (error) {
    receivers.value = []
  } finally {
    receiverLoading.value = false
  }
}

function handleProjectChange() {
  form.suite_ids = []
  form.environment = null
  form.notice_targets = []
  loadSuites()
  loadEnvironments()
  loadReceivers()
}

function handleSuiteTypeChange() {
  form.suite_ids = []
  loadSuites()
}

function applyCronPreset(preset) {
  form.cron_expression = preset.expr
}

async function doCronPreview() {
  const expr = String(form.cron_expression || '').trim()
  if (!expr) {
    cronPreview.value = null
    cronPreviewError.value = ''
    return
  }
  cronPreviewLoading.value = true
  try {
    const data = await scheduledTasksApi.cronPreview(expr, { timezone: form.timezone })
    cronPreview.value = normalizeCronPreview(data, { count: 5 })
    cronPreviewError.value = ''
  } catch (error) {
    cronPreview.value = null
    cronPreviewError.value = error?.message || 'Cron 预览失败'
  } finally {
    cronPreviewLoading.value = false
  }
}

const schedulePreview = debounce(doCronPreview, 450)

function openCreate() {
  mode.value = 'create'
  currentId.value = null
  Object.assign(form, emptyForm())
  cronPreview.value = null
  cronPreviewError.value = ''
  drawerVisible.value = true
  loadSuites()
  loadEnvironments()
  loadReceivers()
  schedulePreview()
}

async function openEdit(row) {
  mode.value = 'edit'
  currentId.value = row.id
  Object.assign(
    form,
    emptyForm({
      project: row.project ?? null,
      name: row.name || '',
      description: row.description || '',
      suite_type: row.suite_type || 'api',
      suite_ids: Array.isArray(row.suite_ids) ? [...row.suite_ids] : [],
      cron_expression: row.cron_expression || '',
      timezone: row.timezone || 'Asia/Shanghai',
      trigger_condition: row.trigger_condition || 'always',
      environment: row.environment ?? null,
      notice_targets: Array.isArray(row.notice_targets) ? [...row.notice_targets] : [],
      is_enabled: row.is_enabled !== false,
      appRunConfigText: JSON.stringify(row.app_run_config ?? {}, null, 2),
    }),
  )
  cronPreview.value = null
  cronPreviewError.value = ''
  drawerVisible.value = true
  await Promise.all([loadSuites(), loadEnvironments(), loadReceivers()])
  schedulePreview()
}

function buildPayload() {
  if (!form.project) return { error: '请选择归属项目' }
  const name = String(form.name || '').trim()
  if (!name) return { error: '任务名称不能为空' }
  if (!form.suite_type) return { error: '请选择套件类型' }
  const suiteIds = (form.suite_ids || []).map((item) => Number(item)).filter((item) => item > 0)
  if (!suiteIds.length) return { error: '请至少选择一个测试套件' }
  const cron = String(form.cron_expression || '').trim()
  if (!cron) return { error: 'cron 表达式不能为空' }

  let appRunConfig = {}
  if (form.suite_type === 'app') {
    const raw = String(form.appRunConfigText || '').trim()
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (parsed !== null && (typeof parsed !== 'object' || Array.isArray(parsed))) {
          return { error: 'App 运行配置必须是 JSON 对象' }
        }
        appRunConfig = parsed || {}
      } catch (error) {
        return { error: `App 运行配置不是合法 JSON：${error.message}` }
      }
    }
  }

  return {
    payload: {
      project: form.project,
      name,
      description: String(form.description || ''),
      suite_type: form.suite_type,
      suite_ids: suiteIds,
      cron_expression: cron,
      timezone: form.timezone || 'Asia/Shanghai',
      trigger_condition: form.trigger_condition,
      environment: form.environment || null,
      notice_targets: form.notice_targets || [],
      is_enabled: Boolean(form.is_enabled),
      app_run_config: appRunConfig,
    },
  }
}

async function handleSave() {
  const { payload, error } = buildPayload()
  if (error) {
    ElMessage.warning(error)
    return
  }
  // 保存前确保 cron 已经校验过（后端同样会拒绝非法表达式）
  if (!cronPreview.value || cronPreview.value.expression !== payload.cron_expression.trim()) {
    await doCronPreview()
  }
  if (cronPreview.value && !cronPreview.value.valid) {
    ElMessage.warning(cronPreview.value.message || 'cron 表达式不合法')
    return
  }
  saving.value = true
  try {
    if (mode.value === 'create') {
      await scheduledTasksApi.createTask(payload)
      ElMessage.success('定时任务已创建')
    } else {
      await scheduledTasksApi.updateTask(currentId.value, payload)
      ElMessage.success('定时任务已更新')
    }
    drawerVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(error?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleRun(row) {
  runningId.value = row.id
  try {
    const data = await scheduledTasksApi.runTask(row.id)
    const status = data?.execution_log?.status || data?.status || 'pending'
    ElMessage.success(`已触发执行（日志 #${data?.log_id ?? '—'}，状态：${status}）`)
    await load()
  } catch (error) {
    ElMessage.error(error?.message || '触发执行失败')
  } finally {
    runningId.value = null
  }
}

async function handleToggle(row) {
  togglingId.value = row.id
  try {
    await scheduledTasksApi.toggleTask(row.id)
    ElMessage.success(row.is_enabled ? '已停用该任务' : '已启用该任务')
    await load()
  } catch (error) {
    ElMessage.error(error?.message || '启停失败')
  } finally {
    togglingId.value = null
  }
}

async function handleDelete(row) {
  try {
    await scheduledTasksApi.removeTask(row.id)
    ElMessage.success('已删除')
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (error) {
    ElMessage.error(error?.message || '删除失败')
  }
}

function openLogs(row) {
  router.push({ name: 'scheduled-tasks-logs', query: { task: row.id } })
}

watch(
  () => form.timezone,
  () => {
    if (drawerVisible.value) schedulePreview()
  },
)

watch(
  () => form.cron_expression,
  () => {
    if (drawerVisible.value) schedulePreview()
  },
)

onMounted(async () => {
  if (!projectStore.loaded) {
    try {
      await projectStore.fetchProjects()
    } catch (error) {
      // 无项目时仍展示列表（可能为空）
    }
  }
  if (!filters.project) filters.project = projectStore.currentProjectId || ''
  await load()
})

onUnmounted(() => schedulePreview.cancel?.())
</script>

<style scoped>
.tasks {
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

.mono-input :deep(input) {
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
}

.cron-field {
  width: 100%;
}

.preset-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.cron-preview {
  margin-top: 10px;
  padding: 10px 12px;
  background: #f8fafc;
  border: 1px solid var(--aits-border);
  border-radius: 8px;
}

.cron-preview.is-invalid {
  background: #fef2f2;
  border-color: #fecaca;
}

.cron-preview__ok,
.cron-preview__error {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
}

.cron-preview__ok {
  color: #15803d;
}

.cron-preview__error {
  color: #dc2626;
}

.cron-preview__runs {
  margin-top: 8px;
}

.cron-preview__runs ul {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin: 6px 0 0;
  padding: 0;
  list-style: none;
}

.cron-preview__runs li {
  padding: 2px 8px;
  font-size: 12px;
  color: #334155;
  background: #fff;
  border: 1px solid var(--aits-border);
  border-radius: 4px;
}
</style>
