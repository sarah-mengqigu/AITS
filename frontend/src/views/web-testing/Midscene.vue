<template>
  <div class="tab-panel">
    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="filters.search"
            class="filter-input"
            placeholder="搜索脚本名称 / 内容"
            :prefix-icon="Search"
            clearable
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
          <el-select
            v-model="filters.script_type"
            class="filter-select"
            placeholder="脚本类型"
            clearable
            @change="handleSearch"
          >
            <el-option label="YAML" value="yaml" />
            <el-option label="Python" value="python" />
          </el-select>
          <el-select
            v-model="filters.status"
            class="filter-select"
            placeholder="状态"
            clearable
            @change="handleSearch"
          >
            <el-option
              v-for="(label, value) in MIDSCENE_STATUS_TEXT"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
          <el-button :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </div>
        <div class="toolbar__right">
          <span class="text-small text-muted">共 {{ pagination.total }} 个脚本</span>
          <el-button type="primary" :icon="Plus" @click="openCreate">新建脚本</el-button>
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
        :data="scripts"
        :loading="loading"
        :total="pagination.total"
        row-key="id"
        empty-text="暂无 MidScene 脚本，点击「新建脚本」创建并关联用例"
        @change="loadScripts"
      >
        <el-table-column label="脚本名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" underline="never" @click="openPreview(row)">{{ row.name }}</el-link>
            <div v-if="row.description" class="row-desc">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="light">{{ row.script_type === 'python' ? 'Python' : 'YAML' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="关联用例" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.case_name || '未关联' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <StatusTag :status="row.status" :text="MIDSCENE_STATUS_TEXT[row.status] || row.status" />
          </template>
        </el-table-column>
        <el-table-column label="内容长度" width="100" align="right">
          <template #default="{ row }">{{ (row.content || '').length }}</template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openPreview(row)">预览</el-button>
            <el-button
              link
              type="primary"
              :loading="generatingId === row.id"
              @click="handleGenerate(row)"
            >
              生成
            </el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <ConfirmButton
              link
              type="danger"
              text="删除"
              :content="`确定删除脚本「${row.name}」吗？`"
              :loading="deletingId === row.id"
              @confirm="handleDelete(row)"
            />
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="form.id ? '编辑 MidScene 脚本' : '新建 MidScene 脚本'"
      width="720px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
        <el-form-item label="脚本名称" prop="name">
          <el-input v-model="form.name" maxlength="255" show-word-limit placeholder="例如：登录流程 MidScene" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="脚本类型" prop="script_type">
              <el-select v-model="form.script_type" style="width: 100%">
                <el-option label="YAML" value="yaml" />
                <el-option label="Python" value="python" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="关联用例">
              <el-select
                v-model="form.case"
                clearable
                filterable
                placeholder="选择 Web 用例（生成时需要）"
                style="width: 100%"
                :loading="casesLoading"
              >
                <el-option
                  v-for="item in caseOptions"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="脚本描述">
          <el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item label="脚本内容">
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="10"
            class="mono"
            placeholder="可手工编写，或保存后点击列表中的「生成」由用例生成"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" :title="preview?.name || '脚本预览'" width="880px" top="6vh">
      <div class="preview-meta">
        <el-tag size="small" effect="light">{{ preview?.script_type === 'python' ? 'Python' : 'YAML' }}</el-tag>
        <StatusTag :status="preview?.status" :text="MIDSCENE_STATUS_TEXT[preview?.status] || preview?.status" />
        <span class="text-small text-muted">关联用例：{{ preview?.case_name || '未关联' }}</span>
      </div>
      <pre class="script-preview">{{ preview?.content || '（内容为空，请点击「生成」或手工编辑）' }}</pre>
      <template #footer>
        <el-button @click="copyPreview">复制</el-button>
        <el-button @click="downloadPreview">下载</el-button>
        <el-button type="primary" @click="previewVisible = false">关闭</el-button>
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

import { webTestingApi } from '@/api/webTesting'
import { downloadText } from '@/utils/download'
import { formatDateTime } from '@/utils/format'
import {
  MIDSCENE_STATUS_TEXT,
  midsceneFileName,
  normalizeListPayload,
} from './utils'

const props = defineProps({
  projectId: { type: Number, default: null },
})

const filters = reactive({ search: '', script_type: '', status: '' })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

const scripts = ref([])
const loading = ref(false)
const errorMessage = ref('')
const generatingId = ref(null)
const deletingId = ref(null)

const caseOptions = ref([])
const casesLoading = ref(false)

const dialogVisible = ref(false)
const saving = ref(false)
const formRef = ref(null)
const form = reactive({
  id: null,
  name: '',
  description: '',
  script_type: 'yaml',
  case: null,
  content: '',
})
const rules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
}

const previewVisible = ref(false)
const preview = ref(null)

async function loadScripts() {
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
    if (filters.script_type) params.script_type = filters.script_type
    if (filters.status) params.status = filters.status
    const data = await webTestingApi.listMidsceneScripts(params)
    const { results, count } = normalizeListPayload(data)
    scripts.value = results
    pagination.total = count
  } catch (error) {
    scripts.value = []
    pagination.total = 0
    errorMessage.value = error?.message || 'MidScene 脚本加载失败'
  } finally {
    loading.value = false
  }
}

async function loadCases() {
  if (!props.projectId) return
  casesLoading.value = true
  try {
    const data = await webTestingApi.listCases({ project: props.projectId, page: 1, page_size: 200 })
    caseOptions.value = normalizeListPayload(data).results
  } catch (error) {
    caseOptions.value = []
  } finally {
    casesLoading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadScripts()
}

function handleReset() {
  filters.search = ''
  filters.script_type = ''
  filters.status = ''
  pagination.page = 1
  loadScripts()
}

function openCreate() {
  form.id = null
  form.name = ''
  form.description = ''
  form.script_type = 'yaml'
  form.case = null
  form.content = ''
  dialogVisible.value = true
  loadCases()
  formRef.value?.clearValidate?.()
}

function openEdit(row) {
  form.id = row.id
  form.name = row.name || ''
  form.description = row.description || ''
  form.script_type = row.script_type || 'yaml'
  form.case = row.case ?? null
  form.content = row.content || ''
  dialogVisible.value = true
  loadCases()
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
      script_type: form.script_type,
      case: form.case ?? null,
      content: form.content,
    }
    if (form.id) {
      await webTestingApi.updateMidsceneScript(form.id, payload)
      ElMessage.success('脚本已更新')
    } else {
      await webTestingApi.createMidsceneScript(payload)
      ElMessage.success('脚本已创建')
    }
    dialogVisible.value = false
    await loadScripts()
  } catch (error) {
    ElMessage.error(error?.message || '保存脚本失败')
  } finally {
    saving.value = false
  }
}

async function handleGenerate(row) {
  generatingId.value = row.id
  try {
    const data = await webTestingApi.generateMidsceneScript(row.id, { script_type: row.script_type })
    preview.value = data
    previewVisible.value = true
    ElMessage.success('脚本已生成')
    await loadScripts()
  } catch (error) {
    ElMessage.error(error?.message || '生成脚本失败')
  } finally {
    generatingId.value = null
  }
}

async function openPreview(row) {
  preview.value = row
  previewVisible.value = true
  try {
    const detail = await webTestingApi.retrieveMidsceneScript(row.id)
    preview.value = { ...row, ...detail }
  } catch (error) {
    // 列表数据已足够预览，忽略详情失败
  }
}

async function handleDelete(row) {
  deletingId.value = row.id
  try {
    await webTestingApi.removeMidsceneScript(row.id)
    ElMessage.success('脚本已删除')
    if (scripts.value.length === 1 && pagination.page > 1) pagination.page -= 1
    await loadScripts()
  } catch (error) {
    ElMessage.error(error?.message || '删除脚本失败')
  } finally {
    deletingId.value = null
  }
}

async function copyPreview() {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(preview.value?.content || '')
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = preview.value?.content || ''
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    ElMessage.error(`复制失败：${error?.message || '浏览器不支持'}`)
  }
}

function downloadPreview() {
  downloadText(preview.value?.content || '', midsceneFileName(preview.value || {}))
}

watch(
  () => props.projectId,
  () => {
    pagination.page = 1
    loadScripts()
    loadCases()
  },
)

onMounted(() => {
  loadScripts()
  loadCases()
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

.preview-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.script-preview {
  max-height: 520px;
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
</style>
