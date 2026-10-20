<template>
  <div class="pom-layout">
    <div class="page-card pom-pages">
      <div class="card-title">
        <span>页面对象（{{ pages.length }}）</span>
        <div class="flex-between">
          <el-button link type="primary" :icon="Refresh" @click="loadPages">刷新</el-button>
          <el-button size="small" type="primary" :icon="Plus" @click="openPageCreate">新增页面</el-button>
        </div>
      </div>

      <el-alert
        v-if="pagesError"
        :title="pagesError"
        type="error"
        show-icon
        :closable="false"
        class="mb-16"
      />

      <div v-loading="pagesLoading" class="page-list">
        <el-empty
          v-if="!pages.length && !pagesLoading"
          description="暂无页面，点击「新增页面」创建"
          :image-size="70"
        />
        <div
          v-for="page in pages"
          :key="page.id"
          class="page-item"
          :class="{ 'is-active': selectedPage?.id === page.id }"
          @click="selectPage(page)"
        >
          <div class="page-item__main">
            <div class="page-item__name">{{ page.name }}</div>
            <div class="page-item__url mono">{{ page.url || '未填写地址' }}</div>
          </div>
          <div class="page-item__meta">
            <span class="badge">{{ page.element_count ?? 0 }}</span>
            <span class="page-item__ops" @click.stop>
              <el-button link :icon="Edit" title="编辑页面" @click="openPageEdit(page)" />
              <el-button link type="danger" :icon="Delete" title="删除页面" @click="handlePageDelete(page)" />
            </span>
          </div>
        </div>
      </div>
    </div>

    <div class="page-card pom-elements">
      <div class="card-title">
        <span>
          {{ selectedPage ? `元素：${selectedPage.name}` : '元素列表' }}
          <span class="text-small text-muted">（{{ elements.length }}）</span>
        </span>
        <div class="flex-between">
          <el-button link type="primary" :icon="Refresh" @click="loadElements">刷新</el-button>
          <el-button size="small" :icon="Upload" :disabled="!selectedPage" @click="openBulk">批量导入</el-button>
          <el-button size="small" type="primary" :icon="Plus" :disabled="!selectedPage" @click="openElementCreate">
            新增元素
          </el-button>
        </div>
      </div>

      <el-alert
        v-if="elementsError"
        :title="elementsError"
        type="error"
        show-icon
        :closable="false"
        class="mb-16"
      />
      <el-alert
        v-if="!selectedPage"
        type="info"
        show-icon
        :closable="false"
        title="请选择左侧页面以查看和维护元素"
      />

      <DataTable
        v-else
        :data="elements"
        :loading="elementsLoading"
        :show-pagination="false"
        empty-text="该页面暂无元素，可「新增元素」或「批量导入」"
      >
        <el-table-column prop="name" label="元素名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="定位方式" width="110">
          <template #default="{ row }">
            <el-tag size="small" effect="light">{{ LOCATOR_TYPE_TEXT[row.locator_type] || row.locator_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="定位值" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.locator_value }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备选定位" min-width="200">
          <template #default="{ row }">
            <div v-if="!(row.alternatives || []).length" class="text-muted text-small">—</div>
            <div v-else class="alt-list">
              <el-tag
                v-for="(alt, index) in row.alternatives"
                :key="index"
                size="small"
                type="info"
                effect="plain"
              >
                {{ LOCATOR_TYPE_TEXT[alt.locator_type] || alt.locator_type }}: {{ alt.locator_value }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="描述" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openElementEdit(row)">编辑</el-button>
            <ConfirmButton
              link
              type="danger"
              text="删除"
              :content="`确定删除元素「${row.name}」吗？`"
              @confirm="handleElementDelete(row)"
            />
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <el-dialog
      v-model="pageDialogVisible"
      :title="pageForm.id ? '编辑页面' : '新增页面'"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-form ref="pageFormRef" :model="pageForm" :rules="pageRules" label-width="88px">
        <el-form-item label="页面名称" prop="name">
          <el-input v-model="pageForm.name" maxlength="128" show-word-limit placeholder="例如：登录页" />
        </el-form-item>
        <el-form-item label="页面地址" prop="url">
          <el-input v-model="pageForm.url" maxlength="500" placeholder="例如：/login 或 https://demo.example.com/login" />
        </el-form-item>
        <el-form-item label="页面描述">
          <el-input v-model="pageForm.description" type="textarea" :rows="3" maxlength="500" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pageDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="pageSaving" @click="handlePageSubmit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="elementDialogVisible"
      :title="elementForm.id ? '编辑元素' : '新增元素'"
      width="640px"
      :close-on-click-modal="false"
    >
      <el-form ref="elementFormRef" :model="elementForm" :rules="elementRules" label-width="96px">
        <el-form-item label="元素名称" prop="name">
          <el-input v-model="elementForm.name" maxlength="128" placeholder="例如：用户名输入框" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="9">
            <el-form-item label="定位方式" prop="locator_type">
              <el-select v-model="elementForm.locator_type" style="width: 100%">
                <el-option
                  v-for="option in LOCATOR_TYPE_OPTIONS"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="15">
            <el-form-item label="定位值" prop="locator_value">
              <el-input v-model="elementForm.locator_value" class="mono" placeholder="例如：#username" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="元素描述">
          <el-input v-model="elementForm.description" maxlength="255" placeholder="元素用途说明" />
        </el-form-item>
        <el-form-item label="备选定位">
          <div class="alt-editor">
            <div v-for="(row, index) in elementForm.alternatives" :key="index" class="alt-editor__row">
              <el-select v-model="row.locator_type" style="width: 130px">
                <el-option
                  v-for="option in LOCATOR_TYPE_OPTIONS"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
              <el-input v-model="row.locator_value" class="mono" placeholder="备选定位值" />
              <el-button link type="danger" :icon="Delete" @click="removeAlternative(index)" />
            </div>
            <el-button size="small" :icon="Plus" @click="addAlternative">添加备选定位</el-button>
            <div class="text-small text-muted">
              备选定位会在主定位失败时依次尝试（保存为 alternatives JSON 数组）。
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="elementDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="elementSaving" @click="handleElementSubmit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="bulkVisible" title="批量导入元素" width="720px" :close-on-click-modal="false">
      <el-alert
        type="info"
        show-icon
        :closable="false"
        title="按元素名称 upsert（同名覆盖），JSON 数组格式"
        description='示例：[{"name":"用户名","locator_type":"css","locator_value":"#username","alternatives":[{"locator_type":"xpath","locator_value":"//input[@id=\"username\"]"}]}]'
        class="mb-16"
      />
      <el-input
        v-model="bulkText"
        type="textarea"
        :rows="12"
        class="mono"
        placeholder="粘贴元素 JSON 数组"
      />
      <div class="bulk-footer">
        <el-button size="small" @click="fillBulkSample">填入示例</el-button>
        <span class="text-small text-muted">目标页面：{{ selectedPage?.name || '未选择' }}</span>
      </div>
      <template #footer>
        <el-button @click="bulkVisible = false">取消</el-button>
        <el-button type="primary" :loading="bulkSaving" @click="handleBulkSubmit">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Edit, Plus, Refresh, Upload } from '@element-plus/icons-vue'

import ConfirmButton from '@/components/ConfirmButton.vue'
import DataTable from '@/components/DataTable.vue'

import { webTestingApi } from '@/api/webTesting'
import {
  LOCATOR_TYPE_OPTIONS,
  LOCATOR_TYPE_TEXT,
  buildAlternatives,
  normalizeElementList,
  normalizeListPayload,
  parseBulkElements,
} from './utils'

const props = defineProps({
  projectId: { type: Number, default: null },
})

const pages = ref([])
const pagesLoading = ref(false)
const pagesError = ref('')
const selectedPage = ref(null)

const elements = ref([])
const elementsLoading = ref(false)
const elementsError = ref('')

const pageDialogVisible = ref(false)
const pageSaving = ref(false)
const pageFormRef = ref(null)
const pageForm = reactive({ id: null, name: '', url: '', description: '' })
const pageRules = {
  name: [{ required: true, message: '请输入页面名称', trigger: 'blur' }],
}

const elementDialogVisible = ref(false)
const elementSaving = ref(false)
const elementFormRef = ref(null)
const elementForm = reactive({
  id: null,
  name: '',
  locator_type: 'css',
  locator_value: '',
  description: '',
  alternatives: [],
})
const elementRules = {
  name: [{ required: true, message: '请输入元素名称', trigger: 'blur' }],
  locator_value: [{ required: true, message: '请输入定位值', trigger: 'blur' }],
}

const bulkVisible = ref(false)
const bulkSaving = ref(false)
const bulkText = ref('')

async function loadPages() {
  if (!props.projectId) return
  pagesLoading.value = true
  pagesError.value = ''
  try {
    const data = await webTestingApi.listPages({ project: props.projectId, page: 1, page_size: 100 })
    const { results } = normalizeListPayload(data)
    pages.value = results
    if (selectedPage.value) {
      const found = results.find((item) => item.id === selectedPage.value.id)
      selectedPage.value = found || null
      if (!found) elements.value = []
    } else if (results.length) {
      selectedPage.value = results[0]
      await loadElements()
    }
  } catch (error) {
    pages.value = []
    pagesError.value = error?.message || '页面列表加载失败'
  } finally {
    pagesLoading.value = false
  }
}

async function loadElements() {
  if (!props.projectId || !selectedPage.value) {
    elements.value = []
    return
  }
  elementsLoading.value = true
  elementsError.value = ''
  try {
    let data
    try {
      // 优先后端列表过滤（?page=<页面 id>）
      data = await webTestingApi.listElements({ page: selectedPage.value.id, page_size: 200 })
    } catch (error) {
      // 分页参数与 page 过滤同名时可能 404，降级到 pages/{id}/elements/
      data = await webTestingApi.pageElements(selectedPage.value.id)
    }
    elements.value = normalizeElementList(data)
  } catch (error) {
    elements.value = []
    elementsError.value = error?.message || '元素列表加载失败'
  } finally {
    elementsLoading.value = false
  }
}

function selectPage(page) {
  selectedPage.value = page
  loadElements()
}

function openPageCreate() {
  pageForm.id = null
  pageForm.name = ''
  pageForm.url = ''
  pageForm.description = ''
  pageDialogVisible.value = true
  pageFormRef.value?.clearValidate?.()
}

function openPageEdit(page) {
  pageForm.id = page.id
  pageForm.name = page.name || ''
  pageForm.url = page.url || ''
  pageForm.description = page.description || ''
  pageDialogVisible.value = true
  pageFormRef.value?.clearValidate?.()
}

async function handlePageSubmit() {
  if (pageFormRef.value) {
    try {
      await pageFormRef.value.validate()
    } catch {
      return
    }
  }
  pageSaving.value = true
  try {
    const payload = {
      project: props.projectId,
      name: pageForm.name.trim(),
      url: pageForm.url.trim(),
      description: pageForm.description.trim(),
    }
    if (pageForm.id) {
      await webTestingApi.updatePage(pageForm.id, payload)
      ElMessage.success('页面已更新')
    } else {
      await webTestingApi.createPage(payload)
      ElMessage.success('页面已创建')
    }
    pageDialogVisible.value = false
    await loadPages()
  } catch (error) {
    ElMessage.error(error?.message || '保存页面失败')
  } finally {
    pageSaving.value = false
  }
}

async function handlePageDelete(page) {
  try {
    await ElMessageBox.confirm(
      `确定删除页面「${page.name}」吗？其下元素将一并删除。`,
      '删除页面',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await webTestingApi.removePage(page.id)
    ElMessage.success('页面已删除')
    if (selectedPage.value?.id === page.id) {
      selectedPage.value = null
      elements.value = []
    }
    await loadPages()
  } catch (error) {
    ElMessage.error(error?.message || '删除页面失败')
  }
}

function openElementCreate() {
  elementForm.id = null
  elementForm.name = ''
  elementForm.locator_type = 'css'
  elementForm.locator_value = ''
  elementForm.description = ''
  elementForm.alternatives = []
  elementDialogVisible.value = true
  elementFormRef.value?.clearValidate?.()
}

function openElementEdit(row) {
  elementForm.id = row.id
  elementForm.name = row.name || ''
  elementForm.locator_type = row.locator_type || 'css'
  elementForm.locator_value = row.locator_value || ''
  elementForm.description = row.description || ''
  elementForm.alternatives = (row.alternatives || []).map((item) => ({
    locator_type: item.locator_type || 'css',
    locator_value: item.locator_value || '',
  }))
  elementDialogVisible.value = true
  elementFormRef.value?.clearValidate?.()
}

function addAlternative() {
  elementForm.alternatives.push({ locator_type: 'xpath', locator_value: '' })
}

function removeAlternative(index) {
  elementForm.alternatives.splice(index, 1)
}

async function handleElementSubmit() {
  if (elementFormRef.value) {
    try {
      await elementFormRef.value.validate()
    } catch {
      return
    }
  }
  if (!selectedPage.value) {
    ElMessage.warning('请先选择页面')
    return
  }
  elementSaving.value = true
  try {
    const payload = {
      page: selectedPage.value.id,
      name: elementForm.name.trim(),
      locator_type: elementForm.locator_type,
      locator_value: elementForm.locator_value.trim(),
      description: elementForm.description.trim(),
      alternatives: buildAlternatives(elementForm.alternatives),
    }
    if (elementForm.id) {
      const { page, ...rest } = payload
      await webTestingApi.updateElement(elementForm.id, rest)
      ElMessage.success('元素已更新')
    } else {
      await webTestingApi.createElement(payload)
      ElMessage.success('元素已创建')
    }
    elementDialogVisible.value = false
    await loadElements()
    await loadPages()
  } catch (error) {
    ElMessage.error(error?.message || '保存元素失败')
  } finally {
    elementSaving.value = false
  }
}

async function handleElementDelete(row) {
  try {
    await webTestingApi.removeElement(row.id)
    ElMessage.success('元素已删除')
    await loadElements()
    await loadPages()
  } catch (error) {
    ElMessage.error(error?.message || '删除元素失败')
  }
}

function openBulk() {
  bulkText.value = ''
  bulkVisible.value = true
}

function fillBulkSample() {
  bulkText.value = JSON.stringify(
    [
      {
        name: '用户名输入框',
        locator_type: 'css',
        locator_value: '#username',
        description: '登录页用户名',
        alternatives: [{ locator_type: 'xpath', locator_value: '//input[@id="username"]' }],
      },
      {
        name: '登录按钮',
        locator_type: 'text',
        locator_value: '登录',
        alternatives: [],
      },
    ],
    null,
    2,
  )
}

async function handleBulkSubmit() {
  const parsed = parseBulkElements(bulkText.value, selectedPage.value?.id)
  if (!parsed.ok) {
    ElMessage.error(parsed.error)
    return
  }
  bulkSaving.value = true
  try {
    const data = await webTestingApi.bulkUpsertElements(parsed.value)
    ElMessage.success(`导入完成：新增 ${data.created ?? 0} 个，更新 ${data.updated ?? 0} 个`)
    bulkVisible.value = false
    await loadElements()
    await loadPages()
  } catch (error) {
    ElMessage.error(error?.message || '批量导入失败')
  } finally {
    bulkSaving.value = false
  }
}

watch(
  () => props.projectId,
  () => {
    selectedPage.value = null
    elements.value = []
    loadPages()
  },
)

onMounted(loadPages)
</script>

<style scoped>
.pom-layout {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.page-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 120px;
}

.page-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--aits-border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.page-item:hover {
  border-color: var(--el-color-primary-light-5);
  background: #f8fbff;
}

.page-item.is-active {
  border-color: var(--aits-primary);
  background: #eef4ff;
}

.page-item__main {
  min-width: 0;
  flex: 1;
}

.page-item__name {
  overflow: hidden;
  font-size: 13px;
  font-weight: 500;
  color: #0f172a;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page-item__url {
  overflow: hidden;
  color: #94a3b8;
  font-size: 11.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page-item__meta {
  display: flex;
  align-items: center;
  gap: 6px;
}

.page-item__ops {
  display: none;
  gap: 2px;
}

.page-item:hover .page-item__ops {
  display: flex;
}

.badge {
  padding: 0 7px;
  border-radius: 9px;
  background: #eef2f7;
  color: var(--aits-text-secondary);
  font-size: 11px;
  line-height: 18px;
}

.alt-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.alt-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.alt-editor__row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bulk-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}

@media (max-width: 1440px) {
  .pom-layout {
    grid-template-columns: 280px minmax(0, 1fr);
  }
}
</style>
