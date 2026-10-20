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
            v-model="filters.application"
            class="filter-select-wide"
            placeholder="关联应用"
            clearable
            filterable
            @change="handleSearch"
          >
            <el-option
              v-for="app in applications"
              :key="app.id"
              :label="app.name"
              :value="app.id"
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
        <el-table-column label="模块" width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.module_name || '未归类' }}</template>
        </el-table-column>
        <el-table-column label="应用" width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.application_name || '未绑定' }}</template>
        </el-table-column>
        <el-table-column label="步骤" width="70" align="center">
          <template #default="{ row }">{{ row.step_count ?? (row.steps || []).length }}</template>
        </el-table-column>
        <el-table-column label="Sonic 步骤" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="(row.sonic_steps || []).length" size="small" type="success" effect="light">
              {{ row.sonic_steps.length }} 步
            </el-tag>
            <span v-else class="text-muted text-small">—</span>
          </template>
        </el-table-column>
        <el-table-column label="优先级" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="PRIORITY_TAG_TYPE[row.priority] || 'info'" effect="light">
              {{ getPriorityText(row.priority) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="100">
          <template #default="{ row }">{{ APP_SOURCE_TEXT[row.source] || row.source || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <StatusTag :status="row.is_active ? 'active' : 'inactive'" />
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" @click="openGenerate(row)">生成步骤</el-button>
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

    <el-drawer
      v-model="drawerVisible"
      :title="form.id ? '编辑用例' : '新建用例'"
      size="880px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="用例名称" prop="name">
              <el-input v-model="form.name" maxlength="255" show-word-limit placeholder="例如：登录成功后进入首页" />
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
              <el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" show-word-limit />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">AITS 步骤</el-divider>
        <StepEditor v-model="form.steps" :errors="stepErrors" />

        <template v-if="form.id">
          <el-divider content-position="left">Sonic 步骤快照（保存后只读）</el-divider>
          <DataTable
            :data="summarizeSonicSteps(form.sonic_steps)"
            :show-pagination="false"
            empty-text="暂无 Sonic 步骤快照，保存步骤后自动生成"
          >
            <el-table-column prop="index" label="#" width="50" />
            <el-table-column prop="typeLabel" label="类型" width="70" />
            <el-table-column prop="action" label="动作" width="90" />
            <el-table-column prop="target" label="目标" min-width="120" show-overflow-tooltip />
            <el-table-column prop="value" label="值" min-width="120" show-overflow-tooltip />
          </DataTable>
        </template>
      </el-form>

      <template #footer>
        <el-button @click="drawerVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSubmit">保存</el-button>
      </template>
    </el-drawer>

    <el-dialog v-model="generateDialog.visible" title="根据需求生成步骤" width="720px">
      <el-form label-width="96px">
        <el-form-item label="目标用例">
          <span>{{ generateDialog.caseName || '（未选择）' }}</span>
        </el-form-item>
        <el-form-item label="需求描述">
          <el-input
            v-model="generateDialog.requirement"
            type="textarea"
            :rows="6"
            placeholder="例如：启动 App，点击登录按钮，输入用户名 admin 和密码 123456，点击确认，断言页面显示「首页」"
          />
        </el-form-item>
        <el-form-item label="应用平台">
          <span>{{ getPlatformText(generateDialog.platform) }}</span>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="generateDialog.error"
        :title="generateDialog.error"
        type="error"
        show-icon
        :closable="false"
        class="mb-16"
      />

      <template v-if="generateDialog.result">
        <el-divider content-position="left">
          生成结果（{{ generateDialog.result.generated_by || '—' }}）
        </el-divider>
        <ol v-if="generateDialog.result.steps?.length" class="step-list">
          <li v-for="(step, index) in generateDialog.result.steps" :key="index">
            {{ formatAppStep(step, index + 1) }}
          </li>
        </ol>
        <el-empty v-else description="未生成步骤，请补充需求描述" :image-size="60" />

        <h4 class="section-title">Sonic 步骤快照</h4>
        <DataTable :data="summarizeSonicSteps(generateDialog.result.sonic_steps)" :show-pagination="false">
          <el-table-column prop="index" label="#" width="50" />
          <el-table-column prop="typeLabel" label="类型" width="70" />
          <el-table-column prop="action" label="动作" width="90" />
          <el-table-column prop="target" label="目标" min-width="120" show-overflow-tooltip />
          <el-table-column prop="value" label="值" min-width="120" show-overflow-tooltip />
        </DataTable>
      </template>

      <template #footer>
        <el-button @click="generateDialog.visible = false">关闭</el-button>
        <el-button type="primary" :loading="generateDialog.loading" @click="submitGenerate">
          生成并覆盖步骤
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, RefreshLeft, Search } from '@element-plus/icons-vue'

import ConfirmButton from '@/components/ConfirmButton.vue'
import DataTable from '@/components/DataTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import StepEditor from './StepEditor.vue'

import { appTestingApi } from '@/api/appTesting'
import { formatDateTime } from '@/utils/format'
import {
  APP_SOURCE_TEXT,
  PRIORITY_OPTIONS,
  PRIORITY_TAG_TYPE,
  buildAppStepsPayload,
  formatAppStep,
  getPlatformText,
  getPriorityText,
  normalizeAppSteps,
  normalizeListPayload,
  summarizeSonicSteps,
  validateAppSteps,
} from './utils'

const props = defineProps({
  projectId: { type: Number, default: null },
})

const moduleTree = ref([])
const applications = ref([])
const applicationsLoading = ref(false)

const filters = reactive({ search: '', module: null, application: null })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

const cases = ref([])
const loading = ref(false)
const errorMessage = ref('')
const deletingId = ref(null)

const drawerVisible = ref(false)
const saving = ref(false)
const formRef = ref(null)
const form = reactive({
  id: null,
  name: '',
  module: null,
  application: null,
  description: '',
  priority: 'medium',
  is_active: true,
  steps: [],
  sonic_steps: [],
})

const rules = {
  name: [{ required: true, message: '请输入用例名称', trigger: 'blur' }],
}

const stepErrors = ref([])

const generateDialog = reactive({
  visible: false,
  loading: false,
  caseId: null,
  caseName: '',
  platform: 'android',
  requirement: '',
  result: null,
  error: '',
})

async function loadMeta() {
  if (!props.projectId) return
  applicationsLoading.value = true
  const [treeResult, appsResult] = await Promise.allSettled([
    appTestingApi.moduleTree({ project: props.projectId }),
    appTestingApi.listApplications({ project: props.projectId, page: 1, page_size: 100 }),
  ])
  moduleTree.value = treeResult.status === 'fulfilled' && Array.isArray(treeResult.value)
    ? treeResult.value
    : []
  applications.value = appsResult.status === 'fulfilled'
    ? normalizeListPayload(appsResult.value).results
    : []
  applicationsLoading.value = false
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
    if (filters.application) params.application = filters.application
    const data = await appTestingApi.listCases(params)
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
  filters.application = null
  pagination.page = 1
  loadCases()
}

function resetForm() {
  form.id = null
  form.name = ''
  form.module = filters.module ?? null
  form.application = filters.application ?? null
  form.description = ''
  form.priority = 'medium'
  form.is_active = true
  form.steps = []
  form.sonic_steps = []
  stepErrors.value = []
}

function openCreate() {
  resetForm()
  drawerVisible.value = true
  loadMeta()
  formRef.value?.clearValidate?.()
}

async function openEdit(row) {
  resetForm()
  form.id = row.id
  form.name = row.name || ''
  form.module = row.module ?? null
  form.application = row.application ?? null
  form.description = row.description || ''
  form.priority = row.priority || 'medium'
  form.is_active = row.is_active !== false
  form.steps = normalizeAppSteps(row.steps)
  form.sonic_steps = Array.isArray(row.sonic_steps) ? row.sonic_steps : []
  drawerVisible.value = true
  formRef.value?.clearValidate?.()
  try {
    const detail = await appTestingApi.retrieveCase(row.id)
    form.name = detail.name || form.name
    form.module = detail.module ?? form.module
    form.application = detail.application ?? form.application
    form.description = detail.description || ''
    form.priority = detail.priority || form.priority
    form.is_active = detail.is_active !== false
    form.steps = normalizeAppSteps(detail.steps)
    form.sonic_steps = Array.isArray(detail.sonic_steps) ? detail.sonic_steps : []
  } catch (error) {
    ElMessage.warning(error?.message || '用例详情加载失败，已使用列表数据')
  }
}

async function handleSubmit() {
  if (formRef.value) {
    try {
      await formRef.value.validate()
    } catch {
      return
    }
  }
  const stepsResult = validateAppSteps(form.steps)
  if (!stepsResult.valid) {
    stepErrors.value = stepsResult.errors
    ElMessage.error('测试步骤校验未通过，请检查后重试')
    return
  }
  stepErrors.value = []
  saving.value = true
  try {
    const payload = {
      project: props.projectId,
      name: form.name.trim(),
      module: form.module ?? null,
      application: form.application ?? null,
      description: form.description.trim(),
      priority: form.priority,
      is_active: form.is_active,
      steps: buildAppStepsPayload(form.steps),
    }
    let saved
    if (form.id) {
      saved = await appTestingApi.updateCase(form.id, payload)
      ElMessage.success('用例已更新，Sonic 步骤快照已同步')
    } else {
      saved = await appTestingApi.createCase(payload)
      ElMessage.success('用例已创建，Sonic 步骤快照已同步')
      form.id = saved?.id ?? null
    }
    form.sonic_steps = Array.isArray(saved?.sonic_steps) ? saved.sonic_steps : []
    await loadCases()
  } catch (error) {
    ElMessage.error(error?.message || '保存用例失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  deletingId.value = row.id
  try {
    await appTestingApi.removeCase(row.id)
    ElMessage.success('用例已删除')
    if (cases.value.length === 1 && pagination.page > 1) pagination.page -= 1
    await loadCases()
  } catch (error) {
    ElMessage.error(error?.message || '删除用例失败')
  } finally {
    deletingId.value = null
  }
}

function openGenerate(row) {
  const app = applications.value.find((item) => item.id === (row.application ?? null))
  generateDialog.visible = true
  generateDialog.caseId = row.id
  generateDialog.caseName = row.name
  generateDialog.platform = app?.platform || 'android'
  generateDialog.requirement = ''
  generateDialog.result = null
  generateDialog.error = ''
}

async function submitGenerate() {
  if (!generateDialog.requirement.trim()) {
    ElMessage.warning('请先填写需求描述')
    return
  }
  generateDialog.loading = true
  generateDialog.error = ''
  try {
    const data = await appTestingApi.generateSteps(generateDialog.caseId, {
      requirement: generateDialog.requirement.trim(),
      platform: generateDialog.platform,
    })
    generateDialog.result = data
    ElMessage.success('步骤已生成并覆盖用例')
    await loadCases()
  } catch (error) {
    generateDialog.error = error?.message || '步骤生成失败'
  } finally {
    generateDialog.loading = false
  }
}

watch(
  () => props.projectId,
  () => {
    filters.module = null
    filters.application = null
    pagination.page = 1
    loadMeta()
    loadCases()
  },
)

onMounted(() => {
  loadMeta()
  loadCases()
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

.step-list {
  margin: 0;
  padding-left: 20px;
  color: #334155;
  font-size: 13px;
  line-height: 1.9;
}

.section-title {
  margin: 18px 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}
</style>
