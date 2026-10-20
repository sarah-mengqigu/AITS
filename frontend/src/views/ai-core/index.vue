<template>
  <div class="page-container">
    <PageHeader
      title="AI 中心"
      :subtitle="projectLabel"
      description="LLM 模型配置、RAG 知识库、MCP 工具、Token 用量与 Agent 在线调试"
    >
      <template #actions>
        <el-tag v-if="!projectStore.currentProjectId" type="warning" effect="plain">
          未选择项目 · 仍可管理全局配置
        </el-tag>
        <el-tag v-else type="info" effect="plain">当前项目：{{ projectStore.currentProjectName }}</el-tag>
      </template>
    </PageHeader>

    <div class="module-tabs" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        role="tab"
        class="module-tab"
        :class="{ 'is-active': tab.key === activeKey }"
        :aria-selected="tab.key === activeKey"
        @click="selectTab(tab)"
      >
        {{ tab.label }}
      </button>
    </div>

    <component :is="activeTab.component" :key="activeKey" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PageHeader from '@/components/PageHeader.vue'
import { useProjectStore } from '@/stores/project'

import Overview from './Overview.vue'
import Models from './Models.vue'
import Rag from './Rag.vue'
import Mcp from './Mcp.vue'
import Usage from './Usage.vue'
import Agents from './Agents.vue'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

const tabs = [
  { key: 'overview', label: '能力总览', routeName: 'ai-core', component: Overview },
  { key: 'models', label: '模型配置', routeName: 'ai-core-models', component: Models },
  { key: 'rag', label: 'RAG 配置', routeName: 'ai-core-rag', component: Rag },
  { key: 'mcp', label: 'MCP 工具', routeName: 'ai-core-mcp', component: Mcp },
  { key: 'usage', label: '用量统计', routeName: 'ai-core-usage', component: Usage },
  { key: 'playground', label: 'Agent 调试', routeName: 'ai-core-playground', component: Agents },
]

const ROUTE_NAME_TO_TAB = tabs.reduce((acc, tab) => {
  acc[tab.routeName] = tab.key
  return acc
}, {})

const activeKey = computed(() => ROUTE_NAME_TO_TAB[route.name] || 'overview')
const activeTab = computed(() => tabs.find((tab) => tab.key === activeKey.value) || tabs[0])
const projectLabel = computed(() =>
  projectStore.currentProjectName ? `项目：${projectStore.currentProjectName}` : '全局视图',
)

function selectTab(tab) {
  if (tab.key === activeKey.value) return
  router.push({ name: tab.routeName || 'ai-core' })
}
</script>

<style scoped>
.module-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  overflow-x: auto;
  background: #fff;
  border: 1px solid var(--aits-border);
  border-radius: var(--aits-radius);
  box-shadow: var(--aits-shadow);
}

.module-tab {
  flex-shrink: 0;
  padding: 9px 16px;
  font-size: 13.5px;
  color: var(--aits-text-secondary);
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: 8px;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.module-tab:hover {
  color: #2563eb;
  background: #f1f5f9;
}

.module-tab.is-active {
  color: #fff;
  font-weight: 600;
  background: #2563eb;
}
</style>
