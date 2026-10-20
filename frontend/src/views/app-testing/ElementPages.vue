<template>
  <div class="tab-panel">
    <el-alert
      type="info"
      show-icon
      :closable="false"
      title="Sonic 元素页面映射"
      description="元素页面（ElementPages）来自 Sonic 服务，用于在用例步骤中复用页面元素定位；未配置 Sonic 时返回空列表。"
    />

    <div class="page-card">
      <div class="card-title">
        <span>元素页面（{{ pages.length }}）</span>
        <el-button size="small" :icon="Refresh" :loading="loading" @click="loadPages">刷新</el-button>
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
        :data="pages"
        :loading="loading"
        :show-pagination="false"
        empty-text="Sonic 未返回元素页面：请先配置 SONIC_BASE_URL 并在 Sonic 中创建元素页面"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand-body">
              <JsonViewer :value="row" :max-height="260" :copyable="false" />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="页面名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ pageName(row) }}</template>
        </el-table-column>
        <el-table-column label="元素数量" width="120" align="center">
          <template #default="{ row }">{{ elementCount(row) }}</template>
        </el-table-column>
        <el-table-column label="标识" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ pageId(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || row.desc || '—' }}</template>
        </el-table-column>
      </DataTable>

      <el-empty
        v-if="!pages.length && !loading"
        :description="SONIC_GUIDANCE"
        :image-size="80"
      />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import JsonViewer from '@/components/JsonViewer.vue'

import { appTestingApi } from '@/api/appTesting'
import { SONIC_GUIDANCE, describeSonicError, normalizeElementPageList } from './utils'

const props = defineProps({
  projectId: { type: Number, default: null },
})

const pages = ref([])
const loading = ref(false)
const errorMessage = ref('')

function pageName(row = {}) {
  return row.name || row.elementPageName || row.pageName || `元素页面 #${pageId(row)}`
}

function pageId(row = {}) {
  return row.id ?? row.elementPageId ?? row.pageId ?? '—'
}

function elementCount(row = {}) {
  if (Array.isArray(row.elements)) return row.elements.length
  if (Number.isFinite(Number(row.elementsCount))) return Number(row.elementsCount)
  if (Number.isFinite(Number(row.count))) return Number(row.count)
  return 0
}

async function loadPages() {
  loading.value = true
  errorMessage.value = ''
  try {
    const payload = await appTestingApi.listElementPages(
      props.projectId ? { project: props.projectId } : {},
    )
    pages.value = normalizeElementPageList(payload)
  } catch (error) {
    pages.value = []
    errorMessage.value = describeSonicError(error) || '元素页面加载失败'
  } finally {
    loading.value = false
  }
}

watch(() => props.projectId, loadPages)
onMounted(loadPages)
</script>

<style scoped>
.expand-body {
  padding: 8px 12px;
}
</style>
