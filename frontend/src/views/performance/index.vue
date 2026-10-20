<template>
  <div class="page-container performance-page">
    <PageHeader
      title="性能测试"
      :subtitle="currentProject ? currentProject.name : '未选择项目'"
      description="负载配置、压测场景、执行报告与 AI 性能诊断"
    >
      <template #actions>
        <el-button :icon="DataLine" @click="router.push('/monitoring')">监控大盘</el-button>
        <el-button
          type="primary"
          :icon="Plus"
          :disabled="!projectId"
          @click="handleCreateScenario"
        >
          新建场景
        </el-button>
      </template>
    </PageHeader>

    <el-alert
      v-if="projectError"
      :title="projectError"
      type="error"
      show-icon
      :closable="false"
      description="项目列表加载失败，请确认后端服务已启动后点击「刷新项目」重试。"
    />

    <div class="page-card project-bar">
      <div class="project-bar__left">
        <span class="project-bar__label">当前项目</span>
        <el-select
          v-model="selectedProjectId"
          class="project-bar__select"
          placeholder="请选择当前项目"
          :loading="projectStore.loading"
          filterable
          clearable
          @change="handleProjectChange"
        >
          <el-option
            v-for="project in projectStore.projects"
            :key="project.id"
            :label="project.name"
            :value="project.id"
          />
        </el-select>
        <el-tag
          v-if="currentProject"
          :type="PROJECT_TYPE_TAG_TYPE[currentProject.project_type] || 'info'"
          effect="light"
        >
          {{ getProjectTypeText(currentProject.project_type) }}
        </el-tag>
        <span v-if="currentProject?.role" class="text-small text-muted">
          角色：{{ getRoleText(currentProject.role) }}
        </span>
        <el-button
          v-if="!projectStore.loading && !projectStore.projects.length"
          link
          type="primary"
          @click="router.push('/projects')"
        >
          去创建项目
        </el-button>
      </div>
      <div class="project-bar__right">
        <span class="text-small text-muted">负载配置、场景、执行与诊断均按当前项目隔离</span>
        <el-button :icon="Refresh" size="small" :loading="projectStore.loading" @click="ensureProjects">
          刷新项目
        </el-button>
      </div>
    </div>

    <div v-if="!projectId" class="page-card">
      <EmptyState
        title="请先选择或创建一个性能测试项目"
        description="性能测试的负载配置、场景、执行记录与 AI 诊断均按项目隔离，创建 perf 类型项目后即可开始压测。"
      >
        <el-button type="primary" :icon="Folder" @click="router.push('/projects')">
          前往项目管理
        </el-button>
        <el-button :icon="Refresh" @click="ensureProjects">刷新项目列表</el-button>
      </EmptyState>
    </div>

    <template v-else>
      <el-tabs
        v-model="activeTab"
        class="performance-tabs"
        @tab-change="handleTabChange"
      >
        <el-tab-pane label="总览" name="overview" lazy>
          <Overview
            :project-id="projectId"
            :refresh-key="refreshTokens.overview"
            @switch-tab="switchTab"
            @open-execution="handleOpenExecution"
          />
        </el-tab-pane>

        <el-tab-pane label="负载配置" name="configs" lazy>
          <Configs
            :project-id="projectId"
            :refresh-key="refreshTokens.configs"
            @changed="handleConfigChanged"
          />
        </el-tab-pane>

        <el-tab-pane label="测试场景" name="scenarios" lazy>
          <Scenarios
            :project-id="projectId"
            :refresh-key="refreshTokens.scenarios"
            :create-key="createScenarioKey"
            @create-consumed="createScenarioKey = 0"
            @changed="handleScenarioChanged"
            @run-created="handleRunCreated"
            @open-execution="handleOpenExecution"
          />
        </el-tab-pane>

        <el-tab-pane label="执行记录" name="executions" lazy>
          <Executions
            :project-id="projectId"
            :refresh-key="refreshTokens.executions"
            :initial-execution-id="pendingExecutionId"
            @initial-consumed="pendingExecutionId = null"
            @changed="bump('overview')"
            @switch-tab="switchTab"
          />
        </el-tab-pane>

        <el-tab-pane label="AI 诊断" name="diagnoses" lazy>
          <Diagnoses
            :project-id="projectId"
            :refresh-key="refreshTokens.diagnoses"
            @changed="handleDiagnosisChanged"
            @open-execution="handleOpenExecution"
          />
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DataLine, Folder, Plus, Refresh } from '@element-plus/icons-vue'

import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'

import { useProjectStore } from '@/stores/project'
import { PROJECT_TYPE_TAG_TYPE, getProjectTypeText, getRoleText } from '@/utils/format'

import Overview from './Overview.vue'
import Configs from './Configs.vue'
import Scenarios from './Scenarios.vue'
import Executions from './Executions.vue'
import Diagnoses from './Diagnoses.vue'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

// 侧边栏为同一组件注册了多个子路由，这里按路由映射 tab（不改 router）。
const TAB_BY_ROUTE = {
  performance: 'overview',
  'performance-configs': 'configs',
  'performance-scenarios': 'scenarios',
  'performance-executions': 'executions',
  'performance-diagnoses': 'diagnoses',
}

const ROUTE_BY_TAB = {
  overview: 'performance',
  configs: 'performance-configs',
  scenarios: 'performance-scenarios',
  executions: 'performance-executions',
  diagnoses: 'performance-diagnoses',
}

const TAB_NAMES = Object.keys(ROUTE_BY_TAB)

const routeTab = TAB_BY_ROUTE[route.name]
const activeTab = ref(routeTab || 'overview')
const projectError = ref('')
const pendingExecutionId = ref(null)
const createScenarioKey = ref(0)

const refreshTokens = reactive({
  overview: 0,
  configs: 0,
  scenarios: 0,
  executions: 0,
  diagnoses: 0,
})

const projectId = computed(() => projectStore.currentProjectId)
const currentProject = computed(() => projectStore.currentProject)

const selectedProjectId = computed({
  get: () => projectStore.currentProjectId,
  set: (value) => projectStore.setCurrentProject(value),
})

function bump(...keys) {
  keys.forEach((key) => {
    if (key in refreshTokens) refreshTokens[key] += 1
  })
}

async function ensureProjects() {
  projectError.value = ''
  try {
    await projectStore.fetchProjects()
  } catch (error) {
    projectError.value = error?.message || '项目列表加载失败'
  }
}

function handleProjectChange(value) {
  projectStore.setCurrentProject(value)
  pendingExecutionId.value = null
  const project = projectStore.currentProject
  if (project) ElMessage.success(`已切换到项目：${project.name}`)
  if (value) bump('overview', 'configs', 'scenarios', 'executions', 'diagnoses')
}

function switchTab(name) {
  if (TAB_NAMES.includes(name)) handleTabChange(name)
}

/** 用户点击 tab：activeTab 由 v-model 更新，这里同步 URL（不改 router 配置）。 */
function handleTabChange(name) {
  if (!TAB_NAMES.includes(name)) return
  activeTab.value = name
  const routeName = ROUTE_BY_TAB[name]
  if (routeName && route.name !== routeName) {
    router.replace({ name: routeName }).catch(() => {})
  }
}

// 浏览器前进/后退或侧边栏切换时，同步激活 tab。
watch(
  () => route.name,
  (name) => {
    const tab = TAB_BY_ROUTE[name]
    if (tab && tab !== activeTab.value) activeTab.value = tab
  },
)

function handleCreateScenario() {
  createScenarioKey.value += 1
  switchTab('scenarios')
}

function handleConfigChanged() {
  bump('configs', 'overview', 'scenarios')
}

function handleScenarioChanged() {
  bump('scenarios', 'overview')
}

function handleRunCreated() {
  bump('executions', 'overview')
}

function handleDiagnosisChanged() {
  bump('diagnoses', 'overview')
}

function handleOpenExecution(id) {
  if (!id) {
    switchTab('executions')
    return
  }
  pendingExecutionId.value = id
  switchTab('executions')
  bump('executions')
}

onMounted(() => {
  if (!projectStore.loaded || !projectStore.projects.length) ensureProjects()
})
</script>

<style scoped>
.project-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 18px;
}

.project-bar__left,
.project-bar__right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.project-bar__label {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.project-bar__select {
  width: 260px;
}

.performance-tabs :deep(.el-tabs__header) {
  margin: 0 0 14px;
  padding: 0 14px;
  background: #fff;
  border: 1px solid var(--aits-border);
  border-radius: var(--aits-radius);
  box-shadow: var(--aits-shadow);
}

.performance-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 0;
}

.performance-tabs :deep(.el-tabs__item) {
  height: 46px;
  line-height: 46px;
}
</style>
