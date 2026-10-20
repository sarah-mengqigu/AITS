<template>
  <div class="module-layout">
    <div class="page-card module-tree-card">
      <div class="card-title">
        <span>模块树</span>
        <div class="flex-between">
          <el-button size="small" :icon="Refresh" @click="loadTree">刷新</el-button>
          <el-button size="small" type="primary" :icon="Plus" @click="openCreate()">新增根模块</el-button>
        </div>
      </div>

      <el-alert
        v-if="treeError"
        :title="treeError"
        type="error"
        show-icon
        :closable="false"
        class="mb-16"
      />

      <el-tree
        v-loading="treeLoading"
        :data="tree"
        node-key="id"
        :props="treeProps"
        default-expand-all
        highlight-current
        :expand-on-click-node="false"
        empty-text="暂无模块，点击「新增根模块」创建"
        @node-click="handleNodeClick"
      >
        <template #default="{ data }">
          <div class="tree-node">
            <span class="tree-node__label">{{ data.name }}</span>
            <span class="tree-node__count">{{ data.case_count ?? 0 }}</span>
            <span class="tree-node__ops" @click.stop>
              <el-button link :icon="Plus" title="新增子模块" @click="openCreate(data)" />
              <el-button link :icon="Edit" title="编辑模块" @click="openEdit(data)" />
              <el-button
                link
                type="danger"
                :icon="Delete"
                title="删除模块"
                @click="handleDelete(data)"
              />
            </span>
          </div>
        </template>
      </el-tree>
    </div>

    <div class="page-card module-cases-card">
      <div class="card-title">
        <span>
          {{ selectedModule ? `模块：${selectedModule.name}` : '全部用例' }}
          <span class="text-small text-muted">（{{ casesTotal }} 条）</span>
        </span>
        <div class="flex-between">
          <el-button link type="primary" :icon="Refresh" @click="loadCases">刷新</el-button>
          <el-button link type="primary" @click="clearSelection">查看全部用例</el-button>
        </div>
      </div>

      <el-alert
        v-if="casesError"
        :title="casesError"
        type="error"
        show-icon
        :closable="false"
        class="mb-16"
      />

      <DataTable
        :data="cases"
        :loading="casesLoading"
        :show-pagination="false"
        empty-text="该模块下暂无用例"
      >
        <el-table-column prop="name" label="用例名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="应用" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.application_name || '未绑定' }}</template>
        </el-table-column>
        <el-table-column label="步骤" width="70" align="center">
          <template #default="{ row }">{{ row.step_count ?? (row.steps || []).length }}</template>
        </el-table-column>
        <el-table-column label="Sonic 步骤" width="100" align="center">
          <template #default="{ row }">{{ (row.sonic_steps || []).length }}</template>
        </el-table-column>
        <el-table-column label="优先级" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="PRIORITY_TAG_TYPE[row.priority] || 'info'" effect="light">
              {{ getPriorityText(row.priority) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="110">
          <template #default="{ row }">{{ APP_SOURCE_TEXT[row.source] || row.source || '—' }}</template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openCaseDetail(row)">查看</el-button>
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="form.id ? '编辑模块' : (parentPreset ? '新增子模块' : '新增根模块')"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="88px">
        <el-form-item label="模块名称" prop="name">
          <el-input v-model="form.name" maxlength="128" show-word-limit placeholder="例如：登录模块" />
        </el-form-item>
        <el-form-item label="上级模块" prop="parent">
          <el-tree-select
            v-model="form.parent"
            :data="parentOptions"
            :props="{ label: 'name', value: 'id', children: 'children' }"
            check-strictly
            clearable
            placeholder="不选则为根模块"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="模块描述">
          <el-input v-model="form.description" type="textarea" :rows="3" maxlength="500" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ form.id ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="caseDrawerVisible" :title="caseDetail?.name || '用例详情'" size="680px">
      <template v-if="caseDetail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="所属模块">{{ caseDetail.module_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="关联应用">{{ caseDetail.application_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ APP_SOURCE_TEXT[caseDetail.source] || caseDetail.source || '—' }}</el-descriptions-item>
          <el-descriptions-item label="优先级">{{ getPriorityText(caseDetail.priority) }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <StatusTag :status="caseDetail.is_active ? 'active' : 'inactive'" />
          </el-descriptions-item>
          <el-descriptions-item label="描述">{{ caseDetail.description || '—' }}</el-descriptions-item>
        </el-descriptions>

        <h4 class="section-title">AITS 步骤（{{ normalizeAppSteps(caseDetail.steps).length }}）</h4>
        <el-empty
          v-if="!normalizeAppSteps(caseDetail.steps).length"
          description="暂未编排步骤"
          :image-size="60"
        />
        <ol v-else class="step-list">
          <li v-for="(step, index) in normalizeAppSteps(caseDetail.steps)" :key="index">
            {{ formatAppStep(step, index + 1) }}
          </li>
        </ol>

        <h4 class="section-title">Sonic 步骤快照（只读）</h4>
        <DataTable
          :data="summarizeSonicSteps(caseDetail.sonic_steps)"
          :show-pagination="false"
          empty-text="无 Sonic 步骤快照"
        >
          <el-table-column prop="index" label="#" width="50" />
          <el-table-column prop="typeLabel" label="类型" width="70" />
          <el-table-column prop="action" label="动作" width="90" />
          <el-table-column prop="target" label="目标" min-width="120" show-overflow-tooltip />
          <el-table-column prop="value" label="值" min-width="120" show-overflow-tooltip />
        </DataTable>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Edit, Plus, Refresh } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import StatusTag from '@/components/StatusTag.vue'

import { appTestingApi } from '@/api/appTesting'
import { formatDateTime } from '@/utils/format'
import {
  APP_SOURCE_TEXT,
  PRIORITY_TAG_TYPE,
  flattenTree,
  formatAppStep,
  getPriorityText,
  normalizeAppSteps,
  normalizeListPayload,
  summarizeSonicSteps,
} from './utils'

const props = defineProps({
  projectId: { type: Number, default: null },
})

const treeProps = { label: 'name', children: 'children' }

const tree = ref([])
const treeLoading = ref(false)
const treeError = ref('')
const selectedModule = ref(null)

const cases = ref([])
const casesTotal = ref(0)
const casesLoading = ref(false)
const casesError = ref('')

const dialogVisible = ref(false)
const submitting = ref(false)
const parentPreset = ref(null)
const formRef = ref(null)
const form = reactive({ id: null, name: '', parent: null, description: '' })
const rules = {
  name: [{ required: true, message: '请输入模块名称', trigger: 'blur' }],
}

const caseDrawerVisible = ref(false)
const caseDetail = ref(null)

const parentOptions = computed(() => {
  if (!form.id) return tree.value
  const exclude = (nodes) =>
    (Array.isArray(nodes) ? nodes : [])
      .filter((node) => node.id !== form.id)
      .map((node) => ({ ...node, children: exclude(node.children) }))
  return exclude(tree.value)
})

async function loadTree() {
  if (!props.projectId) return
  treeLoading.value = true
  treeError.value = ''
  try {
    const data = await appTestingApi.moduleTree({ project: props.projectId })
    tree.value = Array.isArray(data) ? data : []
    if (selectedModule.value) {
      const found = flattenTree(tree.value).find((node) => node.id === selectedModule.value.id)
      selectedModule.value = found || null
    }
  } catch (error) {
    tree.value = []
    treeError.value = error?.message || '模块树加载失败'
  } finally {
    treeLoading.value = false
  }
}

async function loadCases() {
  if (!props.projectId) return
  casesLoading.value = true
  casesError.value = ''
  try {
    const params = { project: props.projectId, page: 1, page_size: 100 }
    if (selectedModule.value?.id) params.module = selectedModule.value.id
    const data = await appTestingApi.listCases(params)
    const { results, count } = normalizeListPayload(data)
    cases.value = results
    casesTotal.value = count
  } catch (error) {
    cases.value = []
    casesTotal.value = 0
    casesError.value = error?.message || '用例加载失败'
  } finally {
    casesLoading.value = false
  }
}

function handleNodeClick(data) {
  selectedModule.value = data
  loadCases()
}

function clearSelection() {
  selectedModule.value = null
  loadCases()
}

function openCreate(parent = null) {
  form.id = null
  form.name = ''
  form.parent = parent?.id ?? null
  form.description = ''
  parentPreset.value = parent
  dialogVisible.value = true
  formRef.value?.clearValidate?.()
}

function openEdit(node) {
  form.id = node.id
  form.name = node.name || ''
  form.parent = node.parent ?? null
  form.description = node.description || ''
  parentPreset.value = null
  dialogVisible.value = true
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
  submitting.value = true
  try {
    const payload = {
      project: props.projectId,
      name: form.name.trim(),
      parent: form.parent ?? null,
      description: form.description.trim(),
    }
    if (form.id) {
      await appTestingApi.updateModule(form.id, payload)
      ElMessage.success('模块已更新')
    } else {
      await appTestingApi.createModule(payload)
      ElMessage.success('模块已创建')
    }
    dialogVisible.value = false
    await loadTree()
    await loadCases()
  } catch (error) {
    ElMessage.error(error?.message || '保存模块失败')
  } finally {
    submitting.value = false
  }
}

async function handleDelete(node) {
  try {
    await ElMessageBox.confirm(
      `确定删除模块「${node.name}」吗？其下子模块将一并删除，用例会变为未归类。`,
      '删除模块',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await appTestingApi.removeModule(node.id)
    ElMessage.success('模块已删除')
    if (selectedModule.value?.id === node.id) selectedModule.value = null
    await loadTree()
    await loadCases()
  } catch (error) {
    ElMessage.error(error?.message || '删除模块失败')
  }
}

async function openCaseDetail(row) {
  caseDetail.value = row
  caseDrawerVisible.value = true
  try {
    const detail = await appTestingApi.retrieveCase(row.id)
    caseDetail.value = { ...row, ...detail }
  } catch (error) {
    ElMessage.error(error?.message || '用例详情加载失败')
  }
}

watch(
  () => props.projectId,
  () => {
    selectedModule.value = null
    loadTree()
    loadCases()
  },
)

onMounted(() => {
  loadTree()
  loadCases()
})
</script>

<style scoped>
.module-layout {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding-right: 6px;
}

.tree-node__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-node__count {
  padding: 0 6px;
  border-radius: 8px;
  background: #eef2f7;
  color: var(--aits-text-secondary);
  font-size: 11px;
}

.tree-node__ops {
  display: none;
  gap: 2px;
  margin-left: auto;
}

.tree-node:hover .tree-node__ops {
  display: flex;
}

.section-title {
  margin: 18px 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.step-list {
  margin: 0;
  padding-left: 20px;
  color: #334155;
  font-size: 13px;
  line-height: 1.9;
}

@media (max-width: 1440px) {
  .module-layout {
    grid-template-columns: 300px minmax(0, 1fr);
  }
}
</style>
