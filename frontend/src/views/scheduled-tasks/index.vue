<template>
  <div class="page-container">
    <PageHeader
      title="定时任务"
      :subtitle="projectLabel"
      description="Cron 定时调度、套件批量执行与执行日志（Celery Beat 自动同步）"
    >
      <template #actions>
        <el-tag v-if="!projectStore.currentProjectId" type="warning" effect="plain">
          未选择项目 · 任务需归属项目
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

import Tasks from './Tasks.vue'
import Logs from './Logs.vue'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

const tabs = [
  { key: 'tasks', label: '任务列表', routeName: 'scheduled-tasks', component: Tasks },
  { key: 'logs', label: '执行日志', routeName: 'scheduled-tasks-logs', component: Logs },
]

const ROUTE_NAME_TO_TAB = tabs.reduce((acc, tab) => {
  acc[tab.routeName] = tab.key
  return acc
}, {})

const activeKey = computed(() => ROUTE_NAME_TO_TAB[route.name] || 'tasks')
const activeTab = computed(() => tabs.find((tab) => tab.key === activeKey.value) || tabs[0])
const projectLabel = computed(() =>
  projectStore.currentProjectName ? `项目：${projectStore.currentProjectName}` : '全部项目',
)

function selectTab(tab) {
  if (tab.key === activeKey.value) return
  router.push({ name: tab.routeName })
}
</script>

<style scoped>
.module-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
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
