<template>
  <div class="page-container api-testing-page">
    <PageHeader
      title="API 测试"
      :subtitle="currentProject ? currentProject.name : '未选择项目'"
      description="OpenAPI / Postman 规范导入、模块树、端点、用例、套件与执行报告"
    >
      <template #actions>
        <el-button :icon="Upload" :disabled="!projectId" @click="postmanVisible = true">
          Postman 导入
        </el-button>
        <el-button :icon="MagicStick" :disabled="!projectId" @click="aiVisible = true">
          AI 场景生成
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
        <el-tag v-if="currentProject" :type="PROJECT_TYPE_TAG_TYPE[currentProject.project_type] || 'info'" effect="light">
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
        <span class="text-small text-muted">所有列表与操作均按当前项目隔离</span>
        <el-button :icon="Refresh" size="small" :loading="projectStore.loading" @click="ensureProjects">
          刷新项目
        </el-button>
      </div>
    </div>

    <div v-if="!projectId" class="page-card">
      <EmptyState
        title="请先选择或创建一个项目"
        description="API 测试的规范、模块、用例、套件与执行记录均按项目隔离，创建项目后即可开始导入接口规范。"
      >
        <el-button type="primary" :icon="Folder" @click="router.push('/projects')">
          前往项目管理
        </el-button>
        <el-button :icon="Refresh" @click="ensureProjects">刷新项目列表</el-button>
      </EmptyState>
    </div>

    <template v-else>
      <el-tabs v-model="activeTab" class="api-testing-tabs" @tab-change="handleTabChange">
        <el-tab-pane label="总览" name="overview" lazy>
          <Overview
            :project-id="projectId"
            :refresh-key="refreshTokens.overview"
            @switch-tab="switchTab"
            @open-postman="postmanVisible = true"
            @open-ai="aiVisible = true"
            @open-execution="handleOpenExecution"
          />
        </el-tab-pane>

        <el-tab-pane label="接口规范" name="specs" lazy>
          <Specs
            :project-id="projectId"
            :refresh-key="refreshTokens.specs"
            @open-postman="postmanVisible = true"
            @changed="handleSpecsChanged"
            @open-endpoints="switchTab('endpoints')"
          />
        </el-tab-pane>

        <el-tab-pane label="模块与端点" name="endpoints" lazy>
          <Endpoints
            :project-id="projectId"
            :refresh-key="refreshTokens.endpoints"
            @switch-tab="switchTab"
            @cases-generated="handleCasesGenerated"
          />
        </el-tab-pane>

        <el-tab-pane label="用例管理" name="cases" lazy>
          <Cases
            :project-id="projectId"
            :refresh-key="refreshTokens.cases"
            @execution-created="handleExecutionCreated"
            @open-execution="handleOpenExecution"
            @changed="bump('overview')"
            @switch-tab="switchTab"
          />
        </el-tab-pane>

        <el-tab-pane label="测试套件" name="suites" lazy>
          <Suites
            :project-id="projectId"
            :refresh-key="refreshTokens.suites"
            @execution-created="handleExecutionCreated"
            @open-execution="handleOpenExecution"
            @changed="bump('overview')"
          />
        </el-tab-pane>

        <el-tab-pane label="执行记录" name="executions" lazy>
          <Executions
            :project-id="projectId"
            :refresh-key="refreshTokens.executions"
            :initial-execution-id="pendingExecutionId"
            :active="activeTab === 'executions'"
            @initial-consumed="pendingExecutionId = null"
            @changed="bump('overview')"
            @switch-tab="switchTab"
          />
        </el-tab-pane>
      </el-tabs>
    </template>

    <PostmanImportDialog
      v-model="postmanVisible"
      :project-id="projectId"
      @imported="handlePostmanImported"
    />

    <AiScenarioDialog
      v-model="aiVisible"
      :project-id="projectId"
      @generated="handleScenarioGenerated"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Folder, MagicStick, Refresh, Upload } from '@element-plus/icons-vue'

import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'

import { useProjectStore } from '@/stores/project'
import {
  PROJECT_TYPE_TAG_TYPE,
  getProjectTypeText,
  getRoleText,
} from '@/utils/format'

import Overview from './Overview.vue'
import Specs from './Specs.vue'
import Endpoints from './Endpoints.vue'
import Cases from './Cases.vue'
import Suites from './Suites.vue'
import Executions from './Executions.vue'
import PostmanImportDialog from './components/PostmanImportDialog.vue'
import AiScenarioDialog from './components/AiScenarioDialog.vue'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

// 侧边栏为同一组件注册了多个子路由，这里按路由映射初始子视图（不改 router）
const TAB_BY_ROUTE = {
  'api-testing': 'overview',
  'api-testing-specs': 'specs',
  'api-testing-modules': 'endpoints',
  'api-testing-cases': 'cases',
  'api-testing-suites': 'suites',
  'api-testing-executions': 'executions',
}

const TAB_NAMES = ['overview', 'specs', 'endpoints', 'cases', 'suites', 'executions']

const activeTab = ref(TAB_BY_ROUTE[route.name] || 'overview')
const projectError = ref('')
const postmanVisible = ref(false)
const aiVisible = ref(false)
const pendingExecutionId = ref(null)

const refreshTokens = reactive({
  overview: 0,
  specs: 0,
  endpoints: 0,
  cases: 0,
  suites: 0,
  executions: 0,
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
  if (value) bump('overview', 'specs', 'endpoints', 'cases', 'suites', 'executions')
}

function switchTab(name) {
  if (TAB_NAMES.includes(name)) activeTab.value = name
}

function handleTabChange(name) {
  if (TAB_NAMES.includes(name)) activeTab.value = name
}

function handleSpecsChanged() {
  bump('specs', 'endpoints', 'overview')
}

function handleCasesGenerated() {
  bump('cases', 'endpoints', 'overview')
}

function handlePostmanImported() {
  bump('specs', 'endpoints', 'cases', 'overview')
  switchTab('specs')
}

function handleScenarioGenerated() {
  bump('cases', 'overview')
}

function handleExecutionCreated() {
  bump('executions', 'overview')
}

function handleOpenExecution(id) {
  if (!id) {
    switchTab('executions')
    return
  }
  pendingExecutionId.value = id
  activeTab.value = 'executions'
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

.api-testing-tabs :deep(.el-tabs__header) {
  margin: 0 0 14px;
  padding: 0 14px;
  background: #fff;
  border: 1px solid var(--aits-border);
  border-radius: var(--aits-radius);
  box-shadow: var(--aits-shadow);
}

.api-testing-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 0;
}

.api-testing-tabs :deep(.el-tabs__item) {
  height: 46px;
  line-height: 46px;
}
</style>
