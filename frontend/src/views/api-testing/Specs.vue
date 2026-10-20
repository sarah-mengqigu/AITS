<template>
  <div class="specs-pane">
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
            placeholder="搜索规范名称 / Base URL"
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
              v-for="option in SPEC_SOURCE_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-button :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </div>
        <div class="toolbar__right">
          <span class="text-small text-muted">共 {{ pagination.total }} 个规范</span>
          <el-button :icon="Refresh" :loading="loading" @click="loadSpecs">刷新</el-button>
          <el-button :icon="Upload" @click="emit('open-postman')">Postman 导入</el-button>
          <el-button type="primary" :icon="Plus" @click="openImport">导入规范</el-button>
        </div>
      </div>

      <DataTable
        v-model:page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :data="specs"
        :loading="loading"
        :total="pagination.total"
        row-key="id"
        empty-text="暂无接口规范"
        @change="loadSpecs"
      >
        <el-table-column label="规范名称" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" :underline="false" @click="openDetail(row)">
              {{ row.name }}
            </el-link>
            <div v-if="row.base_url" class="mono text-muted">{{ row.base_url }}</div>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="170">
          <template #default="{ row }">
            <el-tag size="small" effect="light" type="info">{{ getSpecSourceLabel(row.source_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="版本" width="100" show-overflow-tooltip>
          <template #default="{ row }">{{ row.version || '—' }}</template>
        </el-table-column>
        <el-table-column label="端点" width="80" align="center">
          <template #default="{ row }">{{ row.endpoint_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="模块" width="80" align="center">
          <template #default="{ row }">{{ row.module_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tooltip
              :disabled="!row.error_message"
              :content="row.error_message"
              placement="top"
            >
              <el-tag size="small" effect="light" :type="getSpecStatusMeta(row.status).tagType">
                {{ getSpecStatusMeta(row.status).label }}
              </el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">解析结果</el-button>
            <el-button
              link
              type="primary"
              :loading="reparsingId === row.id"
              @click="handleReparse(row)"
            >
              重新解析
            </el-button>
            <ConfirmButton
              link
              type="danger"
              text="删除"
              :content="`确定删除规范「${row.name}」吗？该规范下的端点将一并删除。`"
              :loading="deletingId === row.id"
              @confirm="handleDelete(row)"
            />
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState
            title="暂无接口规范"
            description="上传 OpenAPI / Swagger / Postman 文件，或粘贴规范内容后解析端点。"
          >
            <el-button type="primary" :icon="Upload" @click="openImport">导入规范</el-button>
          </EmptyState>
        </template>
      </DataTable>
    </div>

    <!-- 导入规范 -->
    <el-dialog
      v-model="importVisible"
      title="导入接口规范"
      width="680px"
      :close-on-click-modal="false"
      @closed="resetImport"
    >
      <el-alert
        v-if="importError"
        class="mb-16"
        :title="importError"
        type="error"
        show-icon
        :closable="false"
      />

      <el-tabs v-model="importMode">
        <el-tab-pane label="上传文件" name="file">
          <el-upload
            ref="uploadRef"
            drag
            :auto-upload="false"
            :limit="1"
            accept=".json,.yaml,.yml,application/json"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
            :on-exceed="handleExceed"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">将规范文件拖到此处，或<em>点击选择</em></div>
            <template #tip>
              <div class="el-upload__tip">支持 OpenAPI 3 / Swagger 2 / Postman Collection（JSON / YAML）。</div>
            </template>
          </el-upload>
        </el-tab-pane>

        <el-tab-pane label="粘贴内容" name="text">
          <el-input
            v-model="importForm.content"
            type="textarea"
            :rows="10"
            class="mono"
            placeholder="粘贴 OpenAPI / Swagger JSON 或 YAML，或 Postman Collection JSON"
          />
          <div class="text-small text-muted mt-8">
            粘贴 JSON 时会先做格式校验；YAML 由后端解析。
          </div>
        </el-tab-pane>
      </el-tabs>

      <el-form class="mt-16" label-width="92px" @submit.prevent>
        <el-form-item label="解析格式">
          <el-select v-model="importForm.format" style="width: 100%">
            <el-option label="自动识别" value="auto" :disabled="importMode === 'text'" />
            <el-option
              v-for="option in SPEC_SOURCE_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="规范名称">
          <el-input v-model="importForm.name" clearable maxlength="128" placeholder="可选，默认读取规范标题" />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="importForm.base_url" clearable placeholder="可选，例如 https://api.example.com" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importSubmitting" @click="handleImport">开始导入</el-button>
      </template>
    </el-dialog>

    <!-- 解析结果 -->
    <el-dialog v-model="detailVisible" title="规范解析结果" width="760px">
      <div v-loading="detailLoading">
        <el-alert
          v-if="detailError"
          :title="detailError"
          type="error"
          show-icon
          :closable="false"
        />
        <template v-if="detailSpec">
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="规范名称">{{ detailSpec.name }}</el-descriptions-item>
            <el-descriptions-item label="来源类型">
              {{ getSpecSourceLabel(detailSpec.source_type) }}
            </el-descriptions-item>
            <el-descriptions-item label="版本">{{ detailSpec.version || '—' }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag size="small" effect="light" :type="getSpecStatusMeta(detailSpec.status).tagType">
                {{ getSpecStatusMeta(detailSpec.status).label }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Base URL" :span="2">
              <span class="mono">{{ detailSpec.base_url || '—' }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="端点数量">
              <strong>{{ detailSpec.endpoint_count ?? 0 }}</strong>
            </el-descriptions-item>
            <el-descriptions-item label="模块数量">
              <strong>{{ detailSpec.module_count ?? 0 }}</strong>
            </el-descriptions-item>
            <el-descriptions-item label="源文件">{{ detailSpec.file_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatDateTime(detailSpec.created_at) }}</el-descriptions-item>
          </el-descriptions>

          <el-alert
            v-if="detailSpec.error_message"
            class="mt-16"
            :title="detailSpec.error_message"
            type="error"
            show-icon
            :closable="false"
          />

          <div class="mt-16">
            <div class="card-title">
              <span>规范摘要</span>
              <span class="text-small text-muted">原始内容不在此展示，避免大文件卡顿</span>
            </div>
            <JsonViewer :value="specDataSummary" title="spec_data 摘要" :max-height="240" />
          </div>
        </template>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="primary" @click="goEndpoints">查看端点</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Plus,
  Refresh,
  RefreshLeft,
  Search,
  Upload,
  UploadFilled,
} from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmButton from '@/components/ConfirmButton.vue'
import JsonViewer from '@/components/JsonViewer.vue'

import { apiTestingApi } from '@/api/apiTesting'
import { formatDateTime } from '@/utils/format'
import {
  SPEC_SOURCE_OPTIONS,
  getSpecSourceLabel,
  getSpecStatusMeta,
  isValidHttpUrl,
  validateSpecContent,
} from './utils'

const props = defineProps({
  projectId: { type: [Number, String], default: null },
  refreshKey: { type: Number, default: 0 },
})

const emit = defineEmits(['open-postman', 'changed', 'open-endpoints'])

const specs = ref([])
const loading = ref(false)
const errorMessage = ref('')
const deletingId = ref(null)
const reparsingId = ref(null)

const filters = reactive({ search: '', source_type: '' })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

const importVisible = ref(false)
const importMode = ref('file')
const importSubmitting = ref(false)
const importError = ref('')
const importForm = reactive({ name: '', base_url: '', format: 'auto', content: '' })
const selectedFile = ref(null)
const uploadRef = ref(null)

const detailVisible = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const detailSpec = ref(null)

const specDataSummary = computed(() => {
  const data = detailSpec.value?.spec_data
  if (!data || typeof data !== 'object') return { 说明: '规范内容缺失或格式异常' }
  const summary = {
    format: data.format || '',
    title: data.title || '',
    version: data.version || '',
    description: data.description || '',
  }
  const raw = data.raw
  if (typeof raw === 'string') summary.raw_length = `${raw.length} 字符`
  else if (raw !== undefined) summary.raw_type = Array.isArray(raw) ? 'array' : typeof raw
  return summary
})

function buildParams() {
  const params = {
    project: props.projectId,
    page: pagination.page,
    page_size: pagination.pageSize,
  }
  if (filters.search.trim()) params.search = filters.search.trim()
  if (filters.source_type) params.source_type = filters.source_type
  return params
}

async function loadSpecs() {
  if (!props.projectId) {
    specs.value = []
    pagination.total = 0
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await apiTestingApi.listSpecs(buildParams())
    specs.value = Array.isArray(data?.results) ? data.results : []
    pagination.total = Number(data?.count ?? specs.value.length)
  } catch (error) {
    specs.value = []
    pagination.total = 0
    errorMessage.value = error?.message || '接口规范加载失败'
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadSpecs()
}

function handleReset() {
  filters.search = ''
  filters.source_type = ''
  pagination.page = 1
  loadSpecs()
}

function openImport() {
  importError.value = ''
  importMode.value = 'file'
  importForm.name = ''
  importForm.base_url = ''
  importForm.format = 'auto'
  importForm.content = ''
  selectedFile.value = null
  uploadRef.value?.clearFiles()
  importVisible.value = true
}

function resetImport() {
  selectedFile.value = null
  importForm.content = ''
  importError.value = ''
  uploadRef.value?.clearFiles()
}

function handleFileChange(uploadFile) {
  importError.value = ''
  const raw = uploadFile?.raw || null
  if (raw && !/\.(json|ya?ml)$/i.test(raw.name || '')) {
    importError.value = '仅支持 .json / .yaml / .yml 规范文件'
    selectedFile.value = null
    uploadRef.value?.clearFiles()
    return
  }
  if (raw && raw.size > 10 * 1024 * 1024) {
    importError.value = '文件大小不能超过 10MB'
    selectedFile.value = null
    uploadRef.value?.clearFiles()
    return
  }
  selectedFile.value = raw
}

function handleFileRemove() {
  selectedFile.value = null
}

function handleExceed(files) {
  uploadRef.value?.clearFiles()
  const latest = files?.[0]
  if (latest) {
    selectedFile.value = latest
    uploadRef.value?.handleStart(latest)
    importError.value = ''
  }
}

async function handleImport() {
  if (!props.projectId) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (importMode.value === 'file') {
    if (!selectedFile.value) {
      importError.value = '请先选择规范文件'
      return
    }
  } else {
    const checked = validateSpecContent(importForm.content)
    if (!checked.valid) {
      importError.value = checked.message
      return
    }
  }
  if (importForm.base_url.trim() && !isValidHttpUrl(importForm.base_url)) {
    importError.value = 'Base URL 必须是 http(s) 开头的完整地址'
    return
  }

  importSubmitting.value = true
  importError.value = ''
  try {
    let data
    if (importMode.value === 'file') {
      const payload = {
        project: props.projectId,
        file: selectedFile.value,
        name: importForm.name.trim() || undefined,
        base_url: importForm.base_url.trim() || undefined,
      }
      let format = importForm.format
      if (format === 'auto' && /postman/i.test(selectedFile.value.name || '')) {
        // 后端只有显式 format=postman 才走 Collection 解析
        format = 'postman'
      }
      if (format !== 'auto') payload.format = format
      data = await apiTestingApi.importSpec(payload)
    } else {
      data = await apiTestingApi.importSpec({
        project: props.projectId,
        content: importForm.content,
        format: importForm.format === 'auto' ? 'openapi' : importForm.format,
        name: importForm.name.trim() || undefined,
        base_url: importForm.base_url.trim() || undefined,
      })
    }
    const endpointCount = data?.endpoint_count ?? 0
    ElMessage.success(
      `导入成功：新增 ${data?.created ?? 0} 个、更新 ${data?.updated ?? 0} 个端点，共 ${endpointCount} 个端点`,
    )
    importVisible.value = false
    pagination.page = 1
    await loadSpecs()
    emit('changed', data)
  } catch (error) {
    importError.value = error?.message || '规范导入失败'
    ElMessage.error(importError.value)
  } finally {
    importSubmitting.value = false
  }
}

async function openDetail(row) {
  detailVisible.value = true
  detailSpec.value = row
  detailError.value = ''
  detailLoading.value = true
  try {
    detailSpec.value = await apiTestingApi.retrieveSpec(row.id)
  } catch (error) {
    detailError.value = error?.message || '解析结果加载失败'
  } finally {
    detailLoading.value = false
  }
}

function goEndpoints() {
  detailVisible.value = false
  emit('open-endpoints')
}

async function handleReparse(row) {
  reparsingId.value = row.id
  try {
    const data = await apiTestingApi.reparseSpec(row.id)
    ElMessage.success(
      `重新解析完成：新增 ${data?.created ?? 0} 个、更新 ${data?.updated ?? 0} 个端点，共 ${data?.endpoint_count ?? 0} 个端点`,
    )
    await loadSpecs()
    emit('changed', data)
  } catch (error) {
    ElMessage.error(error?.message || '重新解析失败')
  } finally {
    reparsingId.value = null
  }
}

async function handleDelete(row) {
  deletingId.value = row.id
  try {
    await apiTestingApi.removeSpec(row.id)
    ElMessage.success('规范已删除')
    if (specs.value.length === 1 && pagination.page > 1) pagination.page -= 1
    await loadSpecs()
    emit('changed')
  } catch (error) {
    ElMessage.error(error?.message || '删除规范失败')
  } finally {
    deletingId.value = null
  }
}

watch(
  () => props.projectId,
  () => {
    pagination.page = 1
    loadSpecs()
  },
)

watch(importMode, (mode) => {
  if (mode === 'text' && importForm.format === 'auto') importForm.format = 'openapi'
})

watch(
  () => props.refreshKey,
  () => loadSpecs(),
)

onMounted(loadSpecs)
</script>

<style scoped>
.specs-pane {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.mt-8 {
  margin-top: 8px;
}

:deep(.mono) {
  font-size: 12px;
}
</style>
