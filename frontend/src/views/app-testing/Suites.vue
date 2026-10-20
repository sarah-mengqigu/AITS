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
            v-model="filters.application"
            class="filter-select-wide"
            placeholder="关联应用"
            clearable
            filterable
            @change="handleSearch"
          >
            <el-option v-for="app in applications" :key="app.id" :label="app.name" :value="app.id" />
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
        <el-table-column label="应用" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.application_name || '未绑定' }}</template>
        </el-table-column>
        <el-table-column label="用例数" width="90" align="center">
          <template #default="{ row }">{{ row.case_count ?? (row.case_ids || []).length }}</template>
        </el-table-column>
        <el-table-column label="设备配置" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ describeDeviceConfig(row.device_config) }}</template>
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
      width="720px"
      :close-on-click-modal="false"
      @closed="handleDialogClosed"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="104px">
        <el-form-item label="套件名称" prop="name">
          <el-input v-model="form.name" maxlength="255" show-word-limit placeholder="例如：登录主流程" />
        </el-form-item>
        <el-form-item label="套件描述">
          <el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" show-word-limit />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="关联应用" prop="application">
              <el-select
                v-model="form.application"
                clearable
                filterable
                placeholder="选择被测应用"
                style="width: 100%"
                :loading="applicationsLoading"
              >
                <el-option
                  v-for="app in applications"
                  :key="app.id"
                  :label="`${app.name}（${getPlatformText(app.platform)}）`"
                  :value="app.id"
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
            placeholder="选择要运行的用例（可多选）"
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

        <el-divider content-position="left">设备配置（Sonic）</el-divider>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="设备 UDID">
              <el-input v-model="form.device_udid" class="mono" placeholder="设备 UDID（留空则使用 Sonic 默认设备）" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="设备名称">
              <el-input v-model="form.device_name" placeholder="便于识别的设备名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="设备平台">
              <el-select v-model="form.device_platform" clearable placeholder="未指定" style="width: 100%">
                <el-option
                  v-for="option in PLATFORM_OPTIONS"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="在线设备">
              <el-select
                v-model="form.device_udid"
                clearable
                filterable
                placeholder="从 Sonic 在线设备选择"
                style="width: 100%"
                :loading="devicesLoading"
              >
                <el-option
                  v-for="device in devices"
                  :key="device.udid"
                  :label="`${device.name}（${device.udid}）`"
                  :value="device.udid"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-alert
          v-if="!devices.length"
          type="info"
          show-icon
          :closable="false"
          title="未获取到 Sonic 在线设备"
          :description="SONIC_GUIDANCE"
        />
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="runDialog.visible" title="运行套件" width="560px" :close-on-click-modal="false">
      <el-form label-width="104px">
        <el-form-item label="套件">
          <span>{{ runDialog.suiteName || '—' }}</span>
        </el-form-item>
        <el-form-item label="设备 UDID">
          <el-select
            v-model="runDialog.device_udid"
            clearable
            filterable
            allow-create
            default-first-option
            placeholder="留空使用套件默认设备"
            style="width: 100%"
            :loading="devicesLoading"
          >
            <el-option
              v-for="device in devices"
              :key="device.udid"
              :label="`${device.name}（${device.udid}）`"
              :value="device.udid"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="设备名称">
          <el-input v-model="runDialog.device_name" placeholder="可选" />
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="runDialog.platform" clearable placeholder="可选" style="width: 100%">
            <el-option
              v-for="option in PLATFORM_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="!devices.length"
        type="info"
        show-icon
        :closable="false"
        title="未获取到 Sonic 在线设备"
        :description="SONIC_GUIDANCE"
      />

      <template v-if="runDialog.submitted">
        <el-divider content-position="left">运行进度</el-divider>
        <el-progress
          :percentage="getProgressPercent(runDialog)"
          :status="progressStatus"
          :stroke-width="14"
        />
        <p class="run-progress__text">
          <StatusTag :status="runDialog.status || 'pending'" />
          <span class="text-small text-muted">{{ runDialog.message || '正在运行，请稍候…' }}</span>
        </p>
      </template>

      <template #footer>
        <el-button @click="runDialog.visible = false">关闭</el-button>
        <el-button
          type="primary"
          :loading="runDialog.loading"
          :disabled="runDialog.submitted && !isTerminalStatus(runDialog.status)"
          @click="submitRun"
        >
          {{ runDialog.submitted ? '重新运行' : '开始运行' }}
        </el-button>
        <el-button v-if="runDialog.submitted && isTerminalStatus(runDialog.status)" @click="goRuns">
          查看运行记录
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

import { appTestingApi } from '@/api/appTesting'
import { formatDateTime } from '@/utils/format'
import {
  PLATFORM_OPTIONS,
  SONIC_GUIDANCE,
  buildDeviceConfig,
  describeDeviceConfig,
  formatDevice,
  getPlatformText,
  getProgressPercent,
  isTerminalStatus,
  normalizeDeviceList,
  normalizeListPayload,
} from './utils'
import { watchTask } from './task'

const props = defineProps({
  projectId: { type: Number, default: null },
})

const switchTab = inject('appTestingSwitchTab', null)

const filters = reactive({ search: '', application: null })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

const suites = ref([])
const loading = ref(false)
const errorMessage = ref('')
const deletingId = ref(null)
const runningId = ref(null)

const applications = ref([])
const applicationsLoading = ref(false)
const caseOptions = ref([])
const casesLoading = ref(false)
const devices = ref([])
const devicesLoading = ref(false)

const dialogVisible = ref(false)
const saving = ref(false)
const formRef = ref(null)
const form = reactive({
  id: null,
  name: '',
  description: '',
  application: null,
  is_active: true,
  case_ids: [],
  device_udid: '',
  device_name: '',
  device_platform: '',
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
  device_udid: '',
  device_name: '',
  platform: '',
  status: 'pending',
  progress: null,
  message: '',
  runId: null,
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
    if (filters.application) params.application = filters.application
    const data = await appTestingApi.listSuites(params)
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
  applicationsLoading.value = true
  casesLoading.value = true
  devicesLoading.value = true
  const [appsResult, casesResult, devicesResult] = await Promise.allSettled([
    appTestingApi.listApplications({ project: props.projectId, page: 1, page_size: 100 }),
    appTestingApi.listCases({ project: props.projectId, page: 1, page_size: 200 }),
    appTestingApi.listDevices({ project: props.projectId }),
  ])
  applications.value = appsResult.status === 'fulfilled'
    ? normalizeListPayload(appsResult.value).results
    : []
  caseOptions.value = casesResult.status === 'fulfilled'
    ? normalizeListPayload(casesResult.value).results
    : []
  devices.value = devicesResult.status === 'fulfilled'
    ? normalizeDeviceList(devicesResult.value).map((device) => formatDevice(device))
    : []
  applicationsLoading.value = false
  casesLoading.value = false
  devicesLoading.value = false
}

function handleSearch() {
  pagination.page = 1
  loadSuites()
}

function handleReset() {
  filters.search = ''
  filters.application = null
  pagination.page = 1
  loadSuites()
}

function resetForm() {
  form.id = null
  form.name = ''
  form.description = ''
  form.application = filters.application ?? null
  form.is_active = true
  form.case_ids = []
  form.device_udid = ''
  form.device_name = ''
  form.device_platform = ''
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
  form.application = row.application ?? null
  form.is_active = row.is_active !== false
  form.case_ids = Array.isArray(row.case_ids) ? [...row.case_ids] : []
  const deviceConfig = row.device_config && typeof row.device_config === 'object'
    ? row.device_config
    : {}
  form.device_udid = deviceConfig.udid || deviceConfig.device_udid || ''
  form.device_name = deviceConfig.device_name || ''
  form.device_platform = deviceConfig.platform || ''
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
  saving.value = true
  try {
    const payload = {
      project: props.projectId,
      name: form.name.trim(),
      description: form.description.trim(),
      application: form.application ?? null,
      is_active: form.is_active,
      case_ids: form.case_ids,
      device_config: buildDeviceConfig({
        device_udid: form.device_udid,
        device_name: form.device_name,
        platform: form.device_platform,
      }),
    }
    if (form.id) {
      await appTestingApi.updateSuite(form.id, payload)
      ElMessage.success('套件已更新')
    } else {
      await appTestingApi.createSuite(payload)
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
    await appTestingApi.removeSuite(row.id)
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
  const deviceConfig = row.device_config && typeof row.device_config === 'object'
    ? row.device_config
    : {}
  runDialog.visible = true
  runDialog.loading = false
  runDialog.submitted = false
  runDialog.suiteId = row.id
  runDialog.suiteName = row.name
  runDialog.device_udid = deviceConfig.udid || deviceConfig.device_udid || ''
  runDialog.device_name = deviceConfig.device_name || ''
  runDialog.platform = deviceConfig.platform || ''
  runDialog.status = 'pending'
  runDialog.progress = null
  runDialog.message = ''
  runDialog.runId = null
  loadOptions()
}

async function submitRun() {
  if (!runDialog.suiteId) return
  runDialog.loading = true
  runDialog.submitted = true
  runDialog.status = 'pending'
  runDialog.progress = null
  runDialog.message = '已提交运行任务，等待执行…'
  runWatcher?.close()
  try {
    const deviceConfig = buildDeviceConfig({
      device_udid: runDialog.device_udid,
      device_name: runDialog.device_name,
      platform: runDialog.platform,
    })
    const payload = Object.keys(deviceConfig).length ? { device_config: deviceConfig } : {}
    const data = await appTestingApi.runSuite(runDialog.suiteId, payload)
    runningId.value = runDialog.suiteId
    runDialog.runId = data.run_id ?? null
    runDialog.status = data.run_status || 'pending'
    const taskId = data.task_id ?? data.run_id
    runWatcher = watchTask(taskId, {
      fetchState: () => appTestingApi.retrieveRun(data.run_id),
      onProgress: (state) => {
        runDialog.status = state.status || runDialog.status
        runDialog.progress = state.progress
        runDialog.message = state.message || runDialog.message
      },
      onFinished: (state) => {
        runDialog.status = state.status
        runDialog.progress = 100
        runDialog.message = `运行结束：${state.status}`
        ElMessage.success(`套件运行结束：${state.status}`)
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

function goRuns() {
  runDialog.visible = false
  if (typeof switchTab === 'function') switchTab('runs')
}

watch(
  () => props.projectId,
  () => {
    filters.application = null
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
.filter-select-wide {
  width: 180px;
}

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
