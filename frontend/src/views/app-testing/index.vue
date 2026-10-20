<template>
  <div class="page-container">
    <PageHeader
      title="App 测试"
      :subtitle="projectId ? `当前项目：${projectName || '未命名'}` : '未选择项目'"
      description="Android / iOS 应用、模块与用例、Sonic 设备与套件运行、元素页面映射"
    >
      <template #actions>
        <el-button :icon="Refresh" :loading="refreshing" @click="refreshAll">刷新</el-button>
      </template>
    </PageHeader>

    <el-empty v-if="!projectId" :description="emptyDescription">
      <div class="empty-actions">
        <el-button type="primary" @click="goProjects">去项目管理</el-button>
        <el-button v-if="!projectStore.loaded" :loading="projectStore.loading" @click="reloadProjects">
          重新加载项目
        </el-button>
      </div>
    </el-empty>

    <div v-else class="page-card is-flush">
      <el-tabs v-model="activeTab" class="module-tabs" @tab-change="handleTabChange">
        <el-tab-pane label="测试总览" name="overview" lazy>
          <Overview :key="paneKey('overview')" :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="应用管理" name="applications" lazy>
          <Applications :key="paneKey('applications')" :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="模块管理" name="modules" lazy>
          <Modules :key="paneKey('modules')" :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="用例管理" name="cases" lazy>
          <Cases :key="paneKey('cases')" :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="测试套件" name="suites" lazy>
          <Suites :key="paneKey('suites')" :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="运行记录" name="runs" lazy>
          <Runs :key="paneKey('runs')" :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="设备管理" name="devices" lazy>
          <Devices :key="paneKey('devices')" :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="元素页面" name="element-pages" lazy>
          <ElementPages :key="paneKey('element-pages')" :project-id="projectId" />
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { computed, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'

import PageHeader from '@/components/PageHeader.vue'

import Overview from './Overview.vue'
import Applications from './Applications.vue'
import Modules from './Modules.vue'
import Cases from './Cases.vue'
import Suites from './Suites.vue'
import Runs from './Runs.vue'
import Devices from './Devices.vue'
import ElementPages from './ElementPages.vue'
import { useProjectStore } from '@/stores/project'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

/**
 * 模块内部 Tab ↔ 路由名映射。
 * 「模块管理」与「元素页面」没有独立路由，分别复用
 * `app-testing-cases` / `app-testing-devices` 并带 `?sub=` 标记。
 */
const TAB_ROUTE_MAP = {
  overview: 'app-testing',
  applications: 'app-testing-applications',
  modules: 'app-testing-cases',
  cases: 'app-testing-cases',
  suites: 'app-testing-suites',
  runs: 'app-testing-runs',
  devices: 'app-testing-devices',
  'element-pages': 'app-testing-devices',
}

const TAB_SUB_MAP = {
  modules: 'modules',
  'element-pages': 'elements',
}

const ROUTE_TAB_MAP = {
  'app-testing': 'overview',
  'app-testing-applications': 'applications',
  'app-testing-suites': 'suites',
  'app-testing-runs': 'runs',
  'app-testing-devices': 'devices',
}

function resolveRouteTab() {
  const sub = route.query?.sub || ''
  if (route.name === 'app-testing-cases') {
    return sub === 'modules' ? 'modules' : 'cases'
  }
  if (route.name === 'app-testing-devices') {
    return sub === 'elements' ? 'element-pages' : 'devices'
  }
  return ROUTE_TAB_MAP[route.name] || 'overview'
}

const activeTab = ref(resolveRouteTab())
const refreshing = ref(false)
const refreshSeed = ref(0)

const projectId = computed(() => projectStore.currentProjectId)
const projectName = computed(() => projectStore.currentProjectName)
const emptyDescription = computed(() =>
  projectStore.loaded
    ? '当前没有可用项目，请先在「项目管理」中创建项目后回到本页'
    : '正在加载项目列表…若长时间无响应请点击「重新加载项目」',
)

function paneKey(tab) {
  return `${tab}-${projectId.value}-${refreshSeed.value}`
}

watch([() => route.name, () => route.query?.sub], () => {
  const tab = resolveRouteTab()
  if (tab !== activeTab.value) activeTab.value = tab
})

function handleTabChange(tab) {
  const name = TAB_ROUTE_MAP[tab]
  if (!name) return
  const targetSub = TAB_SUB_MAP[tab] || ''
  const currentSub = route.query?.sub || ''
  if (route.name === name && currentSub === targetSub) return
  router.push({ name, query: targetSub ? { sub: targetSub } : {} }).catch(() => {})
}

function switchTab(tab) {
  if (!tab) return
  activeTab.value = tab
  handleTabChange(tab)
}

provide('appTestingSwitchTab', switchTab)

async function refreshAll() {
  refreshing.value = true
  refreshSeed.value += 1
  try {
    await projectStore.fetchProjects()
  } catch (error) {
    // 保留现有数据，子视图会展示各自的错误
  } finally {
    refreshing.value = false
  }
}

async function reloadProjects() {
  try {
    await projectStore.fetchProjects()
  } catch (error) {
    // 由空态提示
  }
}

function goProjects() {
  router.push({ name: 'projects' })
}
</script>

<style scoped>
.module-tabs {
  padding: 6px 18px 18px;
}

.empty-actions {
  display: flex;
  gap: 8px;
  justify-content: center;
}
</style>
