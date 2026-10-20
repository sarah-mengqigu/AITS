<template>
  <div class="app-shell">
    <aside class="app-sidebar" :class="{ 'is-collapsed': collapsed }">
      <div class="sidebar-brand">
        <div class="brand-logo">A</div>
        <div v-show="!collapsed" class="brand-text">
          <span class="brand-title">AITS 智能测试平台</span>
          <span class="brand-subtitle">AI Testing System v2</span>
        </div>
      </div>

      <div class="sidebar-menu-wrap">
        <el-menu
          class="sidebar-menu"
          :collapse="collapsed"
          :collapse-transition="false"
          :default-active="activeMenu"
          :default-openeds="openedGroups"
          router
        >
          <template v-for="entry in menuItems" :key="entry.key">
            <el-menu-item v-if="entry.type === 'item'" :index="entry.path">
              <el-icon><component :is="entry.icon" /></el-icon>
              <template #title>{{ entry.title }}</template>
            </el-menu-item>

            <el-sub-menu v-else :index="entry.key">
              <template #title>
                <el-icon><component :is="entry.icon" /></el-icon>
                <span>{{ entry.title }}</span>
              </template>
              <el-menu-item
                v-for="child in entry.children"
                :key="child.path"
                :index="child.path"
              >
                {{ child.title }}
              </el-menu-item>
            </el-sub-menu>
          </template>
        </el-menu>
      </div>

      <div v-if="!collapsed" class="sidebar-footer">
        <span>AITS v2.0</span>
        <span class="sidebar-footer__dot">·</span>
        <span>智能测试平台</span>
      </div>
    </aside>

    <div class="app-body">
      <header class="app-header">
        <div class="header-left">
          <button
            class="header-icon-btn"
            type="button"
            :title="collapsed ? '展开侧边栏' : '收起侧边栏'"
            @click="appStore.toggleSidebar()"
          >
            <el-icon :size="18">
              <Expand v-if="collapsed" />
              <Fold v-else />
            </el-icon>
          </button>

          <el-breadcrumb separator="/" class="header-breadcrumb">
            <el-breadcrumb-item v-for="(item, index) in breadcrumbs" :key="index">
              {{ item }}
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>

        <div class="header-right">
          <div class="header-project">
            <el-select
              v-model="selectedProjectId"
              class="project-select"
              size="default"
              placeholder="选择当前项目"
              :loading="projectStore.loading"
              filterable
              clearable
              @change="handleProjectChange"
            >
              <el-option
                v-for="option in projectStore.options"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </div>

          <div class="header-divider" />

          <div class="header-actions">
            <el-tooltip content="项目列表" placement="bottom">
              <button class="header-icon-btn" type="button" @click="router.push('/projects')">
                <el-icon :size="18"><Folder /></el-icon>
              </button>
            </el-tooltip>
          </div>

          <div class="header-divider" />

          <el-dropdown trigger="click" @command="handleUserCommand">
            <div class="user-trigger">
              <el-avatar :size="30" :src="authStore.avatar || undefined">
                {{ authStore.initials }}
              </el-avatar>
              <span class="user-name">{{ authStore.displayName }}</span>
              <el-icon :size="12"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  <el-icon><User /></el-icon>
                  个人中心
                </el-dropdown-item>
                <el-dropdown-item command="projects">
                  <el-icon><Folder /></el-icon>
                  项目管理
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><SwitchButton /></el-icon>
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <main class="app-main">
        <router-view v-slot="{ Component, route }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" :key="route.path" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowDown,
  Bell,
  Connection,
  Expand,
  Fold,
  Folder,
  Iphone,
  MagicStick,
  Monitor,
  Odometer,
  SwitchButton,
  Timer,
  TrendCharts,
  User,
} from '@element-plus/icons-vue'

import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()
const projectStore = useProjectStore()

const collapsed = computed(() => appStore.sidebarCollapsed)

const menuItems = [
  { key: 'dashboard', type: 'item', title: '仪表盘', path: '/dashboard', icon: Odometer },
  { key: 'projects', type: 'item', title: '项目管理', path: '/projects', icon: Folder },
  {
    key: 'api-testing',
    type: 'group',
    title: 'API 测试',
    icon: Connection,
    children: [
      { title: '测试总览', path: '/api-testing' },
      { title: '接口规范', path: '/api-testing/specs' },
      { title: '模块与端点', path: '/api-testing/modules' },
      { title: '用例管理', path: '/api-testing/cases' },
      { title: '测试套件', path: '/api-testing/suites' },
      { title: '执行记录', path: '/api-testing/executions' },
    ],
  },
  {
    key: 'web-testing',
    type: 'group',
    title: 'Web 测试',
    icon: Monitor,
    children: [
      { title: '测试总览', path: '/web-testing' },
      { title: '模块管理', path: '/web-testing/modules' },
      { title: '用例管理', path: '/web-testing/cases' },
      { title: '测试套件', path: '/web-testing/suites' },
      { title: '执行记录', path: '/web-testing/executions' },
      { title: 'POM 管理', path: '/web-testing/pom' },
      { title: 'MidScene 脚本', path: '/web-testing/midscene' },
    ],
  },
  {
    key: 'app-testing',
    type: 'group',
    title: 'App 测试',
    icon: Iphone,
    children: [
      { title: '测试总览', path: '/app-testing' },
      { title: '应用管理', path: '/app-testing/applications' },
      { title: '用例管理', path: '/app-testing/cases' },
      { title: '测试套件', path: '/app-testing/suites' },
      { title: '运行记录', path: '/app-testing/runs' },
      { title: '设备管理', path: '/app-testing/devices' },
    ],
  },
  {
    key: 'performance',
    type: 'group',
    title: '性能测试',
    icon: TrendCharts,
    children: [
      { title: '测试总览', path: '/performance' },
      { title: '负载配置', path: '/performance/configs' },
      { title: '测试场景', path: '/performance/scenarios' },
      { title: '执行记录', path: '/performance/executions' },
      { title: 'AI 诊断', path: '/performance/diagnoses' },
      { title: '监控大盘', path: '/monitoring' },
    ],
  },
  {
    key: 'ai-core',
    type: 'group',
    title: 'AI 中心',
    icon: MagicStick,
    children: [
      { title: '能力总览', path: '/ai-core' },
      { title: '模型配置', path: '/ai-core/models' },
      { title: 'RAG 配置', path: '/ai-core/rag' },
      { title: 'MCP 工具', path: '/ai-core/mcp' },
      { title: '用量统计', path: '/ai-core/usage' },
      { title: 'Agent 调试', path: '/ai-core/playground' },
    ],
  },
  {
    key: 'scheduled-tasks',
    type: 'group',
    title: '定时任务',
    icon: Timer,
    children: [
      { title: '任务列表', path: '/scheduled-tasks' },
      { title: '执行日志', path: '/scheduled-tasks/logs' },
    ],
  },
  {
    key: 'notifications',
    type: 'group',
    title: '通知中心',
    icon: Bell,
    children: [
      { title: '通知总览', path: '/notifications' },
      { title: '渠道配置', path: '/notifications/channels' },
      { title: '接收人', path: '/notifications/receivers' },
      { title: '邮件配置', path: '/notifications/email' },
      { title: '发送日志', path: '/notifications/logs' },
    ],
  },
]

const activeMenu = computed(() => route.meta?.activeMenu || route.path)

const breadcrumbs = computed(() => {
  const meta = route.meta?.breadcrumb
  if (Array.isArray(meta) && meta.length) return meta
  if (route.meta?.title) return [route.meta.title]
  return ['AITS']
})

const openedGroups = ref([findGroupKey(route.path)])

function findGroupKey(path) {
  const entry = menuItems.find(
    (item) =>
      item.type === 'group' &&
      item.children.some((child) => path === child.path || path.startsWith(`${child.path}/`)),
  )
  return entry?.key || ''
}

watch(
  () => route.path,
  (path) => {
    const key = findGroupKey(path)
    if (key && !openedGroups.value.includes(key)) openedGroups.value.push(key)
  },
)

watch(
  breadcrumbs,
  (items) => appStore.setBreadcrumb(items),
  { immediate: true },
)

const selectedProjectId = computed({
  get: () => projectStore.currentProjectId,
  set: (value) => projectStore.setCurrentProject(value),
})

function handleProjectChange(value) {
  projectStore.setCurrentProject(value)
  const project = projectStore.currentProject
  if (project) ElMessage.success(`已切换到项目：${project.name}`)
}

async function handleUserCommand(command) {
  if (command === 'profile') {
    router.push('/profile')
    return
  }
  if (command === 'projects') {
    router.push('/projects')
    return
  }
  if (command === 'logout') {
    await authStore.logout()
    projectStore.clear()
    ElMessage.success('已退出登录')
    router.replace({ name: 'login' })
  }
}

onMounted(async () => {
  if (!authStore.isLoggedIn || projectStore.loaded) return
  try {
    await projectStore.fetchProjects()
  } catch (error) {
    console.warn('[layout] 项目列表加载失败，稍后可重试', error)
  }
})
</script>

<style scoped>
.sidebar-footer {
  flex-shrink: 0;
  padding: 12px 18px;
  border-top: 1px solid rgba(148, 163, 184, 0.14);
  color: #64748b;
  font-size: 11.5px;
  white-space: nowrap;
}

.sidebar-footer__dot {
  margin: 0 6px;
}
</style>
