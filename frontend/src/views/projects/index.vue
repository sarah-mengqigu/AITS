<template>
  <div class="page-container">
    <PageHeader title="项目管理" description="创建并管理测试项目，按项目隔离用例、执行记录与环境配置">
      <template #actions>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建项目</el-button>
      </template>
    </PageHeader>

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
            placeholder="搜索项目名称 / 描述"
            :prefix-icon="Search"
            clearable
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
          <el-select
            v-model="filters.project_type"
            class="filter-select"
            placeholder="项目类型"
            clearable
            @change="handleSearch"
          >
            <el-option
              v-for="(label, value) in PROJECT_TYPE_TEXT"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
          <el-button :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </div>
        <div class="toolbar__right">
          <span class="text-small text-muted">共 {{ pagination.total }} 个项目</span>
        </div>
      </div>

      <DataTable
        v-model:page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :data="projects"
        :loading="loading"
        :total="pagination.total"
        row-key="id"
        empty-text="暂无项目，点击右上角「新建项目」开始"
        @change="loadProjects"
      >
        <el-table-column label="项目名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" :underline="false" @click="goDetail(row)">
              {{ row.name }}
            </el-link>
            <span v-if="row.description" class="project-desc">{{ row.description }}</span>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="140">
          <template #default="{ row }">
            <el-tag :type="PROJECT_TYPE_TAG_TYPE[row.project_type] || 'info'" effect="light" size="small">
              {{ getProjectTypeText(row.project_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="owner_name" label="拥有者" width="130" show-overflow-tooltip />
        <el-table-column label="成员" width="80" align="center">
          <template #default="{ row }">{{ row.member_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <StatusTag :status="row.is_active ? 'active' : 'inactive'" />
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="goDetail(row)">详情</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <ConfirmButton
              link
              type="danger"
              text="删除"
              :content="`确定删除项目「${row.name}」吗？项目下的全部测试数据将一并删除。`"
              :loading="deletingId === row.id"
              @confirm="handleDelete(row)"
            />
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="isEditing ? '编辑项目' : '新建项目'"
      width="520px"
      :close-on-click-modal="false"
      @closed="handleDialogClosed"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="88px">
        <el-form-item label="项目名称" prop="name">
          <el-input v-model="form.name" maxlength="128" show-word-limit placeholder="例如：电商平台 API 测试" />
        </el-form-item>
        <el-form-item label="项目类型" prop="project_type">
          <el-select v-model="form.project_type" style="width: 100%">
            <el-option
              v-for="(label, value) in PROJECT_TYPE_TEXT"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="项目描述" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="项目用途、被测系统说明等"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ isEditing ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, RefreshLeft, Search } from '@element-plus/icons-vue'

import PageHeader from '@/components/PageHeader.vue'
import DataTable from '@/components/DataTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import ConfirmButton from '@/components/ConfirmButton.vue'

import { projectsApi } from '@/api/projects'
import { useProjectStore } from '@/stores/project'
import {
  PROJECT_TYPE_TAG_TYPE,
  PROJECT_TYPE_TEXT,
  formatDateTime,
  getProjectTypeText,
} from '@/utils/format'

const router = useRouter()
const projectStore = useProjectStore()

const projects = ref([])
const loading = ref(false)
const errorMessage = ref('')
const deletingId = ref(null)

const filters = reactive({
  search: '',
  project_type: '',
})

const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0,
})

const dialogVisible = ref(false)
const submitting = ref(false)
const isEditing = ref(false)
const editingId = ref(null)
const formRef = ref(null)

const form = reactive({
  name: '',
  project_type: 'api',
  description: '',
})

const rules = {
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
  project_type: [{ required: true, message: '请选择项目类型', trigger: 'change' }],
}

async function loadProjects() {
  loading.value = true
  errorMessage.value = ''
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
    }
    if (filters.search.trim()) params.search = filters.search.trim()
    if (filters.project_type) params.project_type = filters.project_type

    const data = await projectsApi.list(params)
    projects.value = Array.isArray(data?.results) ? data.results : []
    pagination.total = data?.count ?? projects.value.length
  } catch (error) {
    projects.value = []
    pagination.total = 0
    errorMessage.value = error?.message || '项目列表加载失败'
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadProjects()
}

function handleReset() {
  filters.search = ''
  filters.project_type = ''
  pagination.page = 1
  loadProjects()
}

function resetForm() {
  form.name = ''
  form.project_type = 'api'
  form.description = ''
}

function openCreate() {
  isEditing.value = false
  editingId.value = null
  resetForm()
  dialogVisible.value = true
  formRef.value?.clearValidate()
}

function openEdit(row) {
  isEditing.value = true
  editingId.value = row.id
  form.name = row.name || ''
  form.project_type = row.project_type || 'api'
  form.description = row.description || ''
  dialogVisible.value = true
  formRef.value?.clearValidate()
}

function handleDialogClosed() {
  formRef.value?.resetFields()
  resetForm()
}

async function handleSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    const payload = {
      name: form.name.trim(),
      project_type: form.project_type,
      description: form.description.trim(),
    }
    if (isEditing.value) {
      const updated = await projectsApi.update(editingId.value, payload)
      projectStore.upsertProject(updated)
      ElMessage.success('项目已更新')
    } else {
      const created = await projectsApi.create(payload)
      projectStore.upsertProject(created)
      ElMessage.success('项目已创建')
    }
    dialogVisible.value = false
    await loadProjects()
  } catch (error) {
    ElMessage.error(error?.message || '保存失败')
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row) {
  deletingId.value = row.id
  try {
    await projectsApi.remove(row.id)
    projectStore.removeProject(row.id)
    ElMessage.success('项目已删除')
    if (projects.value.length === 1 && pagination.page > 1) pagination.page -= 1
    await loadProjects()
  } catch (error) {
    ElMessage.error(error?.message || '删除失败')
  } finally {
    deletingId.value = null
  }
}

function goDetail(row) {
  router.push({ name: 'project-detail', params: { id: row.id } })
}

onMounted(loadProjects)
</script>

<style scoped>
.project-desc {
  display: block;
  margin-top: 2px;
  overflow: hidden;
  color: #94a3b8;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
