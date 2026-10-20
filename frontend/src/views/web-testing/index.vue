<template>
  <div class="page-container">
    <PageHeader
      title="Web 测试"
      :subtitle="projectId ? `当前项目：${projectName || '未命名'}` : '未选择项目'"
      description="Web UI 模块树、Playwright / MidScene 用例、POM 元素、测试套件与执行报告"
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
        <el-tab-pane label="模块管理" name="modules" lazy>
          <Modules :key="paneKey('modules')" :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="用例管理" name="cases" lazy>
          <Cases :key="paneKey('cases')" :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="测试套件" name="suites" lazy>
          <Suites :key="paneKey('suites')" :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="执行记录" name="executions" lazy>
          <Executions :key="paneKey('executions')" :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="POM 管理" name="pom" lazy>
          <Pom :key="paneKey('pom')" :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="MidScene 脚本" name="midscene" lazy>
          <Midscene :key="paneKey('midscene')" :project-id="projectId" />
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
import Modules from './Modules.vue'
import Cases from './Cases.vue'
import Suites from './Suites.vue'
import Executions from './Executions.vue'
import Pom from './Pom.vue'
import Midscene from './Midscene.vue'
import { useProjectStore } from '@/stores/project'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

/** 模块内部 Tab ↔ 路由名映射（路由由 router/index.js 固定，本页只切换子视图）。 */
const TAB_ROUTE_MAP = {
  overview: 'web-testing',
  modules: 'web-testing-modules',
  cases: 'web-testing-cases',
  suites: 'web-testing-suites',
  executions: 'web-testing-executions',
  pom: 'web-testing-pom',
  midscene: 'web-testing-midscene',
}

const ROUTE_TAB_MAP = Object.entries(TAB_ROUTE_MAP).reduce((acc, [tab, name]) => {
  acc[name] = tab
  return acc
}, {})

const activeTab = ref(ROUTE_TAB_MAP[route.name] || 'overview')
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

watch(
  () => route.name,
  (name) => {
    const tab = ROUTE_TAB_MAP[name]
    if (tab && tab !== activeTab.value) activeTab.value = tab
  },
)

function handleTabChange(tab) {
  const name = TAB_ROUTE_MAP[tab]
  if (name && route.name !== name) {
    router.push({ name }).catch(() => {})
  }
}

function switchTab(tab) {
  if (!tab) return
  activeTab.value = tab
  handleTabChange(tab)
}

provide('webTestingSwitchTab', switchTab)

async function refreshAll() {
  refreshing.value = true
  refreshSeed.value += 1
  try {
    await projectStore.fetchProjects()
  } catch (error) {
    // 刷新失败保留现有数据，由子视图提示具体错误
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
