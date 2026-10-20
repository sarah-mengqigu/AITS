<template>
  <div class="rag">
    <el-alert
      v-if="pageError"
      type="error"
      show-icon
      :closable="false"
      :title="pageError"
      description="RAG 相关接口加载失败，请确认后端服务已启动。"
    />

    <section class="stat-grid">
      <StatCard
        label="已索引文档"
        :value="formatNumber(ragStats.documents)"
        :loading="statsLoading"
        :icon="Document"
        icon-color="#2563eb"
        icon-bg="#e9effd"
      />
      <StatCard
        label="向量分块数"
        :value="formatNumber(ragStats.chunks)"
        :loading="statsLoading"
        :icon="Files"
        icon-color="#0d9488"
        icon-bg="#ccfbf1"
      />
      <StatCard
        label="集合名称"
        :value="ragStats.collection || '—'"
        :loading="statsLoading"
        :icon="Collection"
        icon-color="#7c3aed"
        icon-bg="#ede9fe"
      />
      <StatCard
        label="RAG 配置数"
        :value="configs.length"
        :loading="configLoading"
        :icon="Setting"
        icon-color="#ea580c"
        icon-bg="#ffedd5"
        :hint="`默认 ${defaultConfigName}`"
      />
    </section>

    <div class="page-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="filters.search"
            class="filter-input"
            placeholder="搜索配置名 / 集合名"
            clearable
            :prefix-icon="Search"
            @keyup.enter="reload"
            @clear="reload"
          />
          <el-select v-model="filters.vector_store" class="filter-select" clearable placeholder="向量库" @change="reload">
            <el-option label="Chroma" value="chroma" />
            <el-option label="Milvus" value="milvus" />
          </el-select>
          <el-select v-model="filters.scope" class="filter-select" @change="reload">
            <el-option label="全部范围" value="all" />
            <el-option label="当前项目" value="current" :disabled="!projectStore.currentProjectId" />
          </el-select>
        </div>
        <div class="toolbar__right">
          <el-button :icon="Refresh" :loading="configLoading" @click="refreshAll">刷新</el-button>
          <el-button type="primary" :icon="Plus" @click="openCreate">新建 RAG 配置</el-button>
        </div>
      </div>

      <DataTable
        :data="configs"
        :loading="configLoading"
        :show-pagination="false"
        empty-text="暂无 RAG 配置，可先创建一个全局配置"
      >
        <el-table-column prop="name" label="配置名称" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="name-cell">
              {{ row.name }}
              <el-tag v-if="row.is_default" size="small" type="success" effect="plain">默认</el-tag>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="向量库" width="110">
          <template #default="{ row }">{{ row.vector_store }}</template>
        </el-table-column>
        <el-table-column label="嵌入模式" width="130">
          <template #default="{ row }">
            {{ row.embedding_mode === 'remote' ? '远程嵌入' : '本地哈希嵌入' }}
          </template>
        </el-table-column>
        <el-table-column label="分块/重叠" width="130">
          <template #default="{ row }">{{ row.chunk_size }} / {{ row.chunk_overlap }}</template>
        </el-table-column>
        <el-table-column label="集合" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.collection_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="范围" width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag v-if="!row.project" size="small" type="info" effect="plain">全局</el-tag>
            <span v-else>{{ projectName(row.project) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button
              v-if="!row.is_default"
              link
              type="success"
              size="small"
              :loading="defaultingId === row.id"
              @click="handleSetDefault(row)"
            >
              设为默认
            </el-button>
            <ConfirmButton
              text="删除"
              link
              size="small"
              :title="`删除 RAG 配置「${row.name}」`"
              content="删除配置不会清理已写入的向量数据，确定删除？"
              @confirm="handleDelete(row)"
            />
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <div class="content-grid">
      <div class="page-card">
        <div class="card-title">
          <span>索引知识库文档</span>
          <el-tag size="small" effect="plain" type="info">POST rag/index/</el-tag>
        </div>
        <div class="toolbar">
          <div class="toolbar__left">
            <el-select
              v-model="indexProjectId"
              class="filter-select"
              placeholder="选择项目"
              clearable
              @change="loadDocuments"
            >
              <el-option
                v-for="project in projectStore.projects"
                :key="project.id"
                :label="project.name"
                :value="project.id"
              />
            </el-select>
            <el-button :icon="Refresh" :loading="docLoading" :disabled="!indexProjectId" @click="loadDocuments">
              刷新文档
            </el-button>
          </div>
        </div>

        <EmptyState
          v-if="!indexProjectId"
          title="请选择项目"
          description="选择项目后可列出其知识库文档并进行索引"
        />
        <DataTable
          v-else
          :data="documents"
          :loading="docLoading"
          :show-pagination="false"
          empty-text="该项目暂无知识库文档"
          max-height="320"
        >
          <el-table-column prop="title" label="文档标题" min-width="160" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <StatusTag :status="row.status" />
            </template>
          </el-table-column>
          <el-table-column label="分块数" width="90">
            <template #default="{ row }">{{ formatNumber(row.chunk_count) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                size="small"
                :loading="indexingId === row.id"
                @click="handleIndex(row)"
              >
                索引
              </el-button>
            </template>
          </el-table-column>
        </DataTable>
      </div>

      <div class="page-card">
        <div class="card-title">
          <span>检索调试</span>
          <el-tag size="small" effect="plain" type="info">POST rag/search/</el-tag>
        </div>
        <div class="search-form">
          <el-input
            v-model="searchForm.query"
            type="textarea"
            :rows="2"
            placeholder="输入要检索的问题，例如：用户登录接口的鉴权方式"
          />
          <div class="search-form__row">
            <el-select v-model="searchForm.project" class="filter-select" clearable placeholder="全局检索">
              <el-option
                v-for="project in projectStore.projects"
                :key="project.id"
                :label="project.name"
                :value="project.id"
              />
            </el-select>
            <el-input-number v-model="searchForm.top_k" :min="1" :max="20" size="default" />
            <el-button type="primary" :loading="searching" :disabled="!searchForm.query.trim()" @click="handleSearch">
              检索
            </el-button>
          </div>
        </div>

        <el-alert
          v-if="searchError"
          class="mt-8"
          type="error"
          show-icon
          :closable="false"
          :title="searchError"
        />

        <div v-if="searchResult" class="search-result">
          <div class="search-result__meta">
            命中 <strong>{{ searchResult.count }}</strong> 个片段 · top_k={{ searchResult.top_k }}
          </div>
          <EmptyState v-if="!searchResult.results.length" title="没有命中任何片段" description="尝试更换关键词、切换项目或先索引知识库文档" />
          <div v-else class="search-result__list">
            <div v-for="(item, index) in searchResult.results" :key="index" class="search-hit">
              <div class="search-hit__head">
                <el-tag size="small" type="primary" effect="plain">#{{ index + 1 }}</el-tag>
                <span class="search-hit__score">score {{ Number(item.score ?? 0).toFixed(4) }}</span>
                <span class="search-hit__source">{{ item.source || '未知来源' }}</span>
              </div>
              <pre class="search-hit__text">{{ item.text }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 配置抽屉 -->
    <el-drawer v-model="drawerVisible" :title="drawerTitle" size="560px" :destroy-on-close="true">
      <el-form label-width="110px" class="drawer-form">
        <el-form-item label="配置范围" required>
          <el-radio-group v-model="form.scope">
            <el-radio label="global">全局配置</el-radio>
            <el-radio label="project" :disabled="!projectStore.currentProjectId">当前项目</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="配置名称" required>
          <el-input v-model="form.name" maxlength="128" placeholder="例如：默认知识库" />
        </el-form-item>
        <el-form-item label="向量库">
          <el-select v-model="form.vector_store" class="w-full">
            <el-option label="Chroma（本地默认）" value="chroma" />
            <el-option label="Milvus（远程）" value="milvus" />
          </el-select>
        </el-form-item>
        <el-form-item label="嵌入模式">
          <el-radio-group v-model="form.embedding_mode">
            <el-radio label="local">本地哈希嵌入</el-radio>
            <el-radio label="remote">远程嵌入服务</el-radio>
          </el-radio-group>
          <div class="field-hint">本地模式无需额外依赖，远程模式需配置嵌入模型与地址。</div>
        </el-form-item>
        <el-form-item label="嵌入模型">
          <el-input v-model="form.embedding_model" maxlength="128" placeholder="aits-hash-64" />
        </el-form-item>
        <el-form-item label="嵌入模型路径">
          <el-input v-model="form.embedding_path" maxlength="500" placeholder="远程/本地模型路径（可选）" />
        </el-form-item>
        <el-form-item label="分块大小">
          <el-input-number v-model="form.chunk_size" :min="1" :max="10000" :step="100" />
        </el-form-item>
        <el-form-item label="分块重叠">
          <el-input-number v-model="form.chunk_overlap" :min="0" :max="9999" :step="50" />
          <div class="field-hint">必须小于分块大小。</div>
        </el-form-item>
        <el-form-item label="集合名称">
          <el-input v-model="form.collection_name" maxlength="128" placeholder="留空使用默认集合" />
        </el-form-item>
        <el-form-item label="连接配置">
          <el-input v-model="form.connectionText" type="textarea" :rows="3" placeholder='{"uri": "http://localhost:19530"}' />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="form.is_default" />
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
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Collection, Document, Files, Plus, Refresh, Search, Setting } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import StatCard from '@/components/StatCard.vue'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmButton from '@/components/ConfirmButton.vue'
import { useProjectStore } from '@/stores/project'
import { aiCoreApi } from '@/api/aiCore'
import { projectsApi } from '@/api/projects'
import { formatNumber } from '@/utils/format'

const projectStore = useProjectStore()

const configs = ref([])
const configLoading = ref(false)
const statsLoading = ref(false)
const pageError = ref('')
const ragStats = reactive({ documents: 0, chunks: 0, collection: '' })

const filters = reactive({ search: '', vector_store: '', scope: 'all' })

const filterParams = computed(() => {
  const params = {}
  if (filters.search.trim()) params.search = filters.search.trim()
  if (filters.vector_store) params.vector_store = filters.vector_store
  if (filters.scope === 'current' && projectStore.currentProjectId) {
    params.project = projectStore.currentProjectId
  }
  return params
})

const defaultConfigName = computed(() => {
  const config = configs.value.find((item) => item.is_default)
  return config ? config.name : '无'
})

const drawerVisible = ref(false)
const mode = ref('create')
const currentId = ref(null)
const saving = ref(false)
const defaultingId = ref(null)
const form = reactive(emptyConfigForm())

const indexProjectId = ref(projectStore.currentProjectId || null)
const documents = ref([])
const docLoading = ref(false)
const indexingId = ref(null)

const searchForm = reactive({ query: '', project: projectStore.currentProjectId || null, top_k: 5 })
const searching = ref(false)
const searchError = ref('')
const searchResult = ref(null)

const drawerTitle = computed(() => (mode.value === 'create' ? '新建 RAG 配置' : '编辑 RAG 配置'))

function emptyConfigForm(values = {}) {
  return {
    scope: 'global',
    project: null,
    name: '',
    vector_store: 'chroma',
    embedding_mode: 'local',
    embedding_model: 'aits-hash-64',
    embedding_path: '',
    chunk_size: 1000,
    chunk_overlap: 200,
    collection_name: '',
    connectionText: '{}',
    is_default: false,
    ...values,
  }
}

function projectName(id) {
  return projectStore.projects.find((item) => item.id === id)?.name || `项目 #${id}`
}

async function loadConfigs() {
  configLoading.value = true
  pageError.value = ''
  try {
    const data = await aiCoreApi.listRagConfigs({ page_size: 100, ...filterParams.value })
    configs.value = Array.isArray(data?.results) ? data.results : []
  } catch (error) {
    configs.value = []
    pageError.value = error?.message || 'RAG 配置加载失败'
  } finally {
    configLoading.value = false
  }
}

async function loadStats() {
  statsLoading.value = true
  try {
    const data = await aiCoreApi.ragStats()
    ragStats.documents = Number(data?.documents ?? 0)
    ragStats.chunks = Number(data?.chunks ?? 0)
    ragStats.collection = data?.collection || ''
  } catch (error) {
    // 统计失败不影响页面其它部分
  } finally {
    statsLoading.value = false
  }
}

async function loadDocuments() {
  if (!indexProjectId.value) {
    documents.value = []
    return
  }
  docLoading.value = true
  try {
    const data = await projectsApi.listKnowledge({ project: indexProjectId.value, page_size: 100 })
    documents.value = Array.isArray(data?.results) ? data.results : []
  } catch (error) {
    documents.value = []
    ElMessage.error(error?.message || '知识库文档加载失败')
  } finally {
    docLoading.value = false
  }
}

function reload() {
  loadConfigs()
}

async function refreshAll() {
  await Promise.allSettled([loadConfigs(), loadStats(), loadDocuments()])
}

function openCreate() {
  mode.value = 'create'
  currentId.value = null
  Object.assign(form, emptyConfigForm({ scope: projectStore.currentProjectId ? 'project' : 'global', project: projectStore.currentProjectId || null }))
  drawerVisible.value = true
}

function openEdit(row) {
  mode.value = 'edit'
  currentId.value = row.id
  Object.assign(
    form,
    emptyConfigForm({
      scope: row.project ? 'project' : 'global',
      project: row.project ?? null,
      name: row.name || '',
      vector_store: row.vector_store || 'chroma',
      embedding_mode: row.embedding_mode || 'local',
      embedding_model: row.embedding_model || '',
      embedding_path: row.embedding_path || '',
      chunk_size: Number(row.chunk_size ?? 1000),
      chunk_overlap: Number(row.chunk_overlap ?? 200),
      collection_name: row.collection_name || '',
      connectionText: JSON.stringify(row.connection ?? {}, null, 2),
      is_default: Boolean(row.is_default),
    }),
  )
  drawerVisible.value = true
}

function buildPayload() {
  const name = String(form.name || '').trim()
  if (!name) return { error: '配置名称不能为空' }
  if (Number(form.chunk_overlap) >= Number(form.chunk_size)) {
    return { error: '分块重叠必须小于分块大小' }
  }
  let connection = {}
  const raw = String(form.connectionText || '').trim()
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (parsed !== null && (typeof parsed !== 'object' || Array.isArray(parsed))) {
        return { error: '连接配置必须是 JSON 对象' }
      }
      connection = parsed || {}
    } catch (error) {
      return { error: `连接配置不是合法 JSON：${error.message}` }
    }
  }
  return {
    payload: {
      project: form.scope === 'project' ? form.project ?? null : null,
      name,
      vector_store: form.vector_store,
      embedding_mode: form.embedding_mode,
      embedding_model: String(form.embedding_model || '').trim(),
      embedding_path: String(form.embedding_path || '').trim(),
      chunk_size: Number(form.chunk_size),
      chunk_overlap: Number(form.chunk_overlap),
      collection_name: String(form.collection_name || '').trim(),
      connection,
      is_default: Boolean(form.is_default),
    },
  }
}

async function handleSave() {
  const { payload, error } = buildPayload()
  if (error) {
    ElMessage.warning(error)
    return
  }
  if (form.scope === 'project' && !payload.project) {
    ElMessage.warning('请先在顶部选择当前项目，或改为全局配置')
    return
  }
  saving.value = true
  try {
    if (mode.value === 'create') {
      await aiCoreApi.createRagConfig(payload)
      ElMessage.success('RAG 配置已创建')
    } else {
      await aiCoreApi.updateRagConfig(currentId.value, payload)
      ElMessage.success('RAG 配置已更新')
    }
    drawerVisible.value = false
    await loadConfigs()
  } catch (error) {
    ElMessage.error(error?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleSetDefault(row) {
  defaultingId.value = row.id
  try {
    await aiCoreApi.setDefaultRagConfig(row.id)
    ElMessage.success(`已将「${row.name}」设为默认 RAG 配置`)
    await loadConfigs()
  } catch (error) {
    ElMessage.error(error?.message || '设置默认失败')
  } finally {
    defaultingId.value = null
  }
}

async function handleDelete(row) {
  try {
    await aiCoreApi.removeRagConfig(row.id)
    ElMessage.success('已删除')
    await loadConfigs()
  } catch (error) {
    ElMessage.error(error?.message || '删除失败')
  }
}

async function handleIndex(row) {
  indexingId.value = row.id
  try {
    const data = await aiCoreApi.indexDocument({ document_id: row.id })
    ElMessage.success(`「${row.title}」索引完成，生成 ${data?.chunk_count ?? 0} 个分块`)
    await Promise.all([loadDocuments(), loadStats()])
  } catch (error) {
    ElMessage.error(error?.message || '索引失败')
  } finally {
    indexingId.value = null
  }
}

async function handleSearch() {
  const query = searchForm.query.trim()
  if (!query) return
  searching.value = true
  searchError.value = ''
  try {
    const data = await aiCoreApi.searchRag({
      query,
      top_k: Number(searchForm.top_k) || 5,
      ...(searchForm.project ? { project: searchForm.project } : {}),
    })
    searchResult.value = {
      count: Number(data?.count ?? (data?.results || []).length),
      top_k: Number(data?.top_k ?? searchForm.top_k),
      results: Array.isArray(data?.results) ? data.results : [],
    }
  } catch (error) {
    searchResult.value = null
    searchError.value = error?.message || '检索失败'
  } finally {
    searching.value = false
  }
}

onMounted(async () => {
  if (!projectStore.loaded) {
    try {
      await projectStore.fetchProjects()
    } catch (error) {
      // 忽略：无项目时仍可管理全局配置
    }
  }
  indexProjectId.value = indexProjectId.value || projectStore.currentProjectId || null
  searchForm.project = searchForm.project || projectStore.currentProjectId || null
  await Promise.all([loadConfigs(), loadStats(), loadDocuments()])
})
</script>

<style scoped>
.rag {
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

.search-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.search-form__row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.search-result {
  margin-top: 14px;
}

.search-result__meta {
  margin-bottom: 10px;
  font-size: 12.5px;
  color: var(--aits-text-secondary);
}

.search-result__list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 360px;
  overflow-y: auto;
}

.search-hit {
  padding: 10px 12px;
  background: #f8fafc;
  border: 1px solid var(--aits-border);
  border-radius: 8px;
}

.search-hit__head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--aits-text-secondary);
}

.search-hit__score {
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  color: #2563eb;
}

.search-hit__source {
  margin-left: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 50%;
}

.search-hit__text {
  margin: 0;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12.5px;
  line-height: 1.6;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 140px;
  overflow-y: auto;
}
</style>
