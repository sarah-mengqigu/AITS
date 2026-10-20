<template>
  <div class="endpoints-pane">
    <el-alert
      v-if="errorMessage || treeError"
      :title="errorMessage || treeError"
      type="error"
      show-icon
      :closable="false"
    />

    <div class="endpoints-layout">
      <aside class="page-card module-panel">
        <div class="card-title">
          <span>接口模块</span>
          <el-button link :icon="Refresh" :loading="treeLoading" @click="loadTree">刷新</el-button>
        </div>
        <el-input
          v-model="moduleKeyword"
          size="small"
          clearable
          placeholder="搜索模块"
          :prefix-icon="Search"
          class="module-search"
        />
        <div v-loading="treeLoading" class="module-tree">
          <el-tree
            v-if="treeData.length"
            ref="treeRef"
            :data="treeData"
            node-key="id"
            :props="{ label: 'name', children: 'children' }"
            highlight-current
            default-expand-all
            :expand-on-click-node="false"
            :filter-node-method="filterModuleNode"
            @node-click="handleModuleClick"
          >
            <template #default="{ data }">
              <span class="tree-node">
                <span class="tree-node__name">{{ data.name }}</span>
                <el-tag v-if="data.children_count" size="small" type="info" effect="plain">
                  {{ data.children_count }}
                </el-tag>
              </span>
            </template>
          </el-tree>
          <EmptyState
            v-if="!treeLoading && !treeData.length"
            title="暂无模块"
            description="导入接口规范后会自动生成模块树"
            :image-size="64"
          />
        </div>
        <div class="module-panel__footer">
          <el-tag v-if="selectedModule" size="small" type="primary" effect="light" closable @close="clearModule">
            {{ selectedModule.full_path || selectedModule.name }}
          </el-tag>
          <span v-else class="text-small text-muted">未按模块筛选</span>
        </div>
      </aside>

      <section class="page-card endpoints-main">
        <div class="toolbar">
          <div class="toolbar__left">
            <el-input
              v-model="filters.search"
              class="filter-input"
              placeholder="搜索路径 / 摘要 / operationId"
              :prefix-icon="Search"
              clearable
              @keyup.enter="handleSearch"
              @clear="handleSearch"
            />
            <el-select
              v-model="filters.method"
              class="filter-select"
              placeholder="请求方法"
              clearable
              @change="handleSearch"
            >
              <el-option
                v-for="method in HTTP_METHODS"
                :key="method"
                :label="getMethodLabel(method)"
                :value="method"
              />
            </el-select>
            <el-button :icon="Search" @click="handleSearch">查询</el-button>
            <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
          </div>
          <div class="toolbar__right">
            <span class="text-small text-muted">共 {{ pagination.total }} 个端点</span>
            <el-button :icon="Refresh" :loading="loading" @click="loadEndpoints">刷新</el-button>
          </div>
        </div>

        <DataTable
          v-model:page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :data="endpoints"
          :loading="loading"
          :total="pagination.total"
          row-key="id"
          empty-text="暂无接口端点"
          @change="loadEndpoints"
        >
          <el-table-column label="方法" width="104">
            <template #default="{ row }">
              <MethodTag :method="row.method" />
            </template>
          </el-table-column>
          <el-table-column label="路径" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="mono">{{ row.path }}</span>
            </template>
          </el-table-column>
          <el-table-column label="摘要" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.summary || row.operation_id || '—' }}
            </template>
          </el-table-column>
          <el-table-column label="模块" width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.module_name || '—' }}</template>
          </el-table-column>
          <el-table-column label="规范" width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ row.spec_name || '—' }}</template>
          </el-table-column>
          <el-table-column label="用例" width="70" align="center">
            <template #default="{ row }">{{ row.case_count ?? 0 }}</template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <StatusTag :status="row.is_active ? 'active' : 'inactive'" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row)">详情</el-button>
              <el-button link type="primary" @click="openGenerator(row)">生成用例</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <EmptyState
              title="暂无接口端点"
              description="先在「接口规范」中导入 OpenAPI / Swagger / Postman 文件，解析后会在这里展示端点。"
            >
              <el-button type="primary" @click="emit('switch-tab', 'specs')">去导入规范</el-button>
            </EmptyState>
          </template>
        </DataTable>
      </section>
    </div>

    <!-- 端点详情 -->
    <el-drawer v-model="detailVisible" title="端点详情" size="56%">
      <div v-loading="detailLoading">
        <el-alert v-if="detailError" :title="detailError" type="error" show-icon :closable="false" />
        <template v-if="detailEndpoint">
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="请求方法">
              <MethodTag :method="detailEndpoint.method" />
            </el-descriptions-item>
            <el-descriptions-item label="状态">
              <StatusTag :status="detailEndpoint.is_active ? 'active' : 'inactive'" />
            </el-descriptions-item>
            <el-descriptions-item label="路径" :span="2">
              <span class="mono">{{ detailEndpoint.path }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="摘要" :span="2">
              {{ detailEndpoint.summary || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="operationId">{{ detailEndpoint.operation_id || '—' }}</el-descriptions-item>
            <el-descriptions-item label="所属模块">{{ detailEndpoint.module_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="所属规范">{{ detailEndpoint.spec_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="关联用例">{{ detailEndpoint.case_count ?? 0 }}</el-descriptions-item>
          </el-descriptions>

          <p v-if="detailEndpoint.description" class="endpoint-desc">{{ detailEndpoint.description }}</p>

          <el-collapse class="mt-16" :model-value="['parameters', 'request', 'responses', 'headers']">
            <el-collapse-item title="参数（parameters）" name="parameters">
              <el-table
                v-if="parameterRows.length"
                :data="parameterRows"
                size="small"
                border
                max-height="260"
              >
                <el-table-column prop="name" label="名称" width="150" show-overflow-tooltip />
                <el-table-column prop="in" label="位置" width="90" />
                <el-table-column prop="required" label="必填" width="70" />
                <el-table-column prop="type" label="类型" width="100" />
                <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
              </el-table>
              <EmptyState v-else title="无参数" :image-size="60" />
            </el-collapse-item>
            <el-collapse-item title="请求体（request_body）" name="request">
              <JsonViewer :value="detailEndpoint.request_body" title="request_body" :max-height="260" />
            </el-collapse-item>
            <el-collapse-item title="响应（responses）" name="responses">
              <JsonViewer :value="detailEndpoint.responses" title="responses" :max-height="260" />
            </el-collapse-item>
            <el-collapse-item title="请求头（headers）" name="headers">
              <JsonViewer :value="detailEndpoint.headers" title="headers" :max-height="220" />
            </el-collapse-item>
          </el-collapse>
        </template>
      </div>
    </el-drawer>

    <!-- 生成用例 -->
    <el-dialog
      v-model="generatorVisible"
      title="从端点生成测试用例"
      width="760px"
      :close-on-click-modal="false"
      @closed="resetGenerator"
    >
      <el-alert
        v-if="generatorError"
        class="mb-16"
        :title="generatorError"
        type="error"
        show-icon
        :closable="false"
      />
      <template v-if="generatorEndpoint">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="端点">
            <MethodTag :method="generatorEndpoint.method" />
            <span class="mono">{{ generatorEndpoint.path }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="摘要">
            {{ generatorEndpoint.summary || generatorEndpoint.operation_id || '—' }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="generator-options">
          <el-switch v-model="useAi" active-text="优先使用 AI 生成（不可用时自动降级为规则生成）" />
        </div>

        <el-button type="primary" :loading="generating" @click="handleGenerate">
          {{ generated ? '重新生成' : '开始生成' }}
        </el-button>

        <template v-if="generated">
          <el-alert
            class="mt-16"
            :title="generated.message"
            type="success"
            show-icon
            :closable="false"
          />
          <el-table :data="generated.cases" size="small" border class="mt-8" max-height="300">
            <el-table-column label="用例名称" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">{{ row.name }}</template>
            </el-table-column>
            <el-table-column label="测试类型" width="100">
              <template #default="{ row }">
                <el-tag size="small" effect="light" :type="getTestTypeTagType(row.testType)">
                  {{ row.testTypeLabel }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="优先级" width="90">
              <template #default="{ row }">{{ row.priority }}</template>
            </el-table-column>
            <el-table-column label="请求" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="mono">{{ row.method }} {{ row.url }}</span>
              </template>
            </el-table-column>
            <el-table-column label="断言" width="70" align="center">
              <template #default="{ row }">{{ row.assertionCount }}</template>
            </el-table-column>
          </el-table>
        </template>
      </template>

      <template #footer>
        <el-button @click="generatorVisible = false">关闭</el-button>
        <el-button v-if="generated" type="primary" plain @click="goCases">查看用例</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, RefreshLeft, Search } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import EmptyState from '@/components/EmptyState.vue'
import JsonViewer from '@/components/JsonViewer.vue'
import StatusTag from '@/components/StatusTag.vue'
import MethodTag from './components/MethodTag.vue'

import { apiTestingApi } from '@/api/apiTesting'
import {
  HTTP_METHODS,
  getMethodLabel,
  getTestTypeTagType,
  summarizeGeneratedCases,
} from './utils'

const props = defineProps({
  projectId: { type: [Number, String], default: null },
  refreshKey: { type: Number, default: 0 },
})

const emit = defineEmits(['switch-tab', 'cases-generated'])

const treeRef = ref(null)
const treeData = ref([])
const treeLoading = ref(false)
const treeError = ref('')
const moduleKeyword = ref('')
const selectedModule = ref(null)

const endpoints = ref([])
const loading = ref(false)
const errorMessage = ref('')
const filters = reactive({ search: '', method: '' })
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

const detailVisible = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const detailEndpoint = ref(null)

const generatorVisible = ref(false)
const generatorEndpoint = ref(null)
const generatorError = ref('')
const generating = ref(false)
const useAi = ref(false)
const generated = ref(null)

const parameterRows = computed(() => {
  const parameters = detailEndpoint.value?.parameters
  if (!Array.isArray(parameters)) return []
  return parameters.map((item) => {
    const source = item && typeof item === 'object' ? item : {}
    const schema = source.schema && typeof source.schema === 'object' ? source.schema : {}
    return {
      name: source.name || '—',
      in: source.in || '—',
      required: source.required ? '是' : '否',
      type: source.type || schema.type || '—',
      description: source.description || '—',
    }
  })
})

function filterModuleNode(value, data) {
  if (!value) return true
  return String(data?.name || '').toLowerCase().includes(String(value).toLowerCase())
}

watch(moduleKeyword, (value) => {
  treeRef.value?.filter(value)
})

async function loadTree() {
  if (!props.projectId) {
    treeData.value = []
    return
  }
  treeLoading.value = true
  treeError.value = ''
  try {
    const data = await apiTestingApi.moduleTree({ project: props.projectId })
    treeData.value = Array.isArray(data?.tree) ? data.tree : Array.isArray(data?.results) ? data.results : []
  } catch (error) {
    treeData.value = []
    treeError.value = error?.message || '模块树加载失败'
  } finally {
    treeLoading.value = false
  }
}

function handleModuleClick(data) {
  selectedModule.value = data
  pagination.page = 1
  loadEndpoints()
}

function clearModule() {
  selectedModule.value = null
  treeRef.value?.setCurrentKey(null)
  pagination.page = 1
  loadEndpoints()
}

async function loadEndpoints() {
  if (!props.projectId) {
    endpoints.value = []
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
    }
    if (filters.search.trim()) params.search = filters.search.trim()
    if (filters.method) params.method = filters.method
    if (selectedModule.value?.id) params.module = selectedModule.value.id
    const data = await apiTestingApi.listEndpoints(params)
    endpoints.value = Array.isArray(data?.results) ? data.results : []
    pagination.total = Number(data?.count ?? endpoints.value.length)
  } catch (error) {
    endpoints.value = []
    pagination.total = 0
    errorMessage.value = error?.message || '端点列表加载失败'
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadEndpoints()
}

function handleReset() {
  filters.search = ''
  filters.method = ''
  selectedModule.value = null
  treeRef.value?.setCurrentKey(null)
  pagination.page = 1
  loadEndpoints()
}

async function openDetail(row) {
  detailVisible.value = true
  detailEndpoint.value = row
  detailError.value = ''
  detailLoading.value = true
  try {
    detailEndpoint.value = await apiTestingApi.retrieveEndpoint(row.id)
  } catch (error) {
    detailError.value = error?.message || '端点详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

function openGenerator(row) {
  generatorEndpoint.value = row
  generated.value = null
  generatorError.value = ''
  useAi.value = false
  generatorVisible.value = true
}

function resetGenerator() {
  generatorEndpoint.value = null
  generated.value = null
  generatorError.value = ''
  useAi.value = false
}

async function handleGenerate() {
  if (!generatorEndpoint.value) return
  generating.value = true
  generatorError.value = ''
  try {
    const data = await apiTestingApi.generateCases(generatorEndpoint.value.id, {
      use_ai: useAi.value,
    })
    generated.value = summarizeGeneratedCases(data)
    ElMessage.success(generated.value.message)
    emit('cases-generated', generated.value.count)
    loadEndpoints()
  } catch (error) {
    generatorError.value = error?.message || '用例生成失败'
    ElMessage.error(generatorError.value)
  } finally {
    generating.value = false
  }
}

function goCases() {
  generatorVisible.value = false
  emit('switch-tab', 'cases')
}

function loadAll() {
  loadTree()
  loadEndpoints()
}

watch(
  () => props.projectId,
  () => {
    selectedModule.value = null
    moduleKeyword.value = ''
    pagination.page = 1
    loadAll()
  },
)

watch(
  () => props.refreshKey,
  () => loadAll(),
)

onMounted(loadAll)
</script>

<style scoped>
.endpoints-pane {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.endpoints-layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.module-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: calc(100vh - 260px);
}

.module-search {
  flex-shrink: 0;
}

.module-tree {
  flex: 1;
  min-height: 180px;
  overflow: auto;
}

.module-panel__footer {
  flex-shrink: 0;
  padding-top: 8px;
  border-top: 1px dashed var(--aits-border);
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.tree-node__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.endpoints-main {
  min-width: 0;
}

.endpoint-desc {
  margin: 12px 0 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f8fafc;
  color: var(--aits-text-secondary);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.generator-options {
  margin: 14px 0;
}

.mt-8 {
  margin-top: 8px;
}

@media (max-width: 1440px) {
  .endpoints-layout {
    grid-template-columns: 240px minmax(0, 1fr);
  }
}
</style>
