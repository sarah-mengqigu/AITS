import { createRouter, createWebHistory } from 'vue-router'
import NProgress from 'nprogress'

import { useAuthStore } from '@/stores/auth'

NProgress.configure({ showSpinner: false, minimum: 0.15 })

// 业务页面组件（本轮占位，下一轮并行补齐）
const ApiTestingView = () => import('@/views/api-testing/index.vue')
const WebTestingView = () => import('@/views/web-testing/index.vue')
const AppTestingView = () => import('@/views/app-testing/index.vue')
const PerformanceView = () => import('@/views/performance/index.vue')
const AiCoreView = () => import('@/views/ai-core/index.vue')
const ScheduledTasksView = () => import('@/views/scheduled-tasks/index.vue')
const NotificationsView = () => import('@/views/notifications/index.vue')
const MonitoringView = () => import('@/views/monitoring/index.vue')

export const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录', public: true, breadcrumb: ['登录'] },
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: { title: '仪表盘', icon: 'Odometer', breadcrumb: ['仪表盘'] },
      },
      {
        path: 'projects',
        name: 'projects',
        component: () => import('@/views/projects/index.vue'),
        meta: { title: '项目管理', icon: 'Folder', breadcrumb: ['项目管理'] },
      },
      {
        path: 'projects/:id',
        name: 'project-detail',
        component: () => import('@/views/projects/detail.vue'),
        meta: {
          title: '项目详情',
          icon: 'Folder',
          breadcrumb: ['项目管理', '项目详情'],
          activeMenu: '/projects',
          hidden: true,
        },
      },

      // API 测试
      {
        path: 'api-testing',
        name: 'api-testing',
        component: ApiTestingView,
        meta: { title: 'API 测试', icon: 'Connection', breadcrumb: ['API 测试', '测试总览'] },
      },
      {
        path: 'api-testing/specs',
        name: 'api-testing-specs',
        component: ApiTestingView,
        meta: { title: '接口规范', icon: 'Document', breadcrumb: ['API 测试', '接口规范'] },
      },
      {
        path: 'api-testing/modules',
        name: 'api-testing-modules',
        component: ApiTestingView,
        meta: { title: '模块与端点', icon: 'Grid', breadcrumb: ['API 测试', '模块与端点'] },
      },
      {
        path: 'api-testing/cases',
        name: 'api-testing-cases',
        component: ApiTestingView,
        meta: { title: '用例管理', icon: 'Tickets', breadcrumb: ['API 测试', '用例管理'] },
      },
      {
        path: 'api-testing/suites',
        name: 'api-testing-suites',
        component: ApiTestingView,
        meta: { title: '测试套件', icon: 'Collection', breadcrumb: ['API 测试', '测试套件'] },
      },
      {
        path: 'api-testing/executions',
        name: 'api-testing-executions',
        component: ApiTestingView,
        meta: { title: '执行记录', icon: 'VideoPlay', breadcrumb: ['API 测试', '执行记录'] },
      },

      // Web 测试
      {
        path: 'web-testing',
        name: 'web-testing',
        component: WebTestingView,
        meta: { title: 'Web 测试', icon: 'Monitor', breadcrumb: ['Web 测试', '测试总览'] },
      },
      {
        path: 'web-testing/modules',
        name: 'web-testing-modules',
        component: WebTestingView,
        meta: { title: '模块管理', icon: 'Grid', breadcrumb: ['Web 测试', '模块管理'] },
      },
      {
        path: 'web-testing/cases',
        name: 'web-testing-cases',
        component: WebTestingView,
        meta: { title: '用例管理', icon: 'Tickets', breadcrumb: ['Web 测试', '用例管理'] },
      },
      {
        path: 'web-testing/suites',
        name: 'web-testing-suites',
        component: WebTestingView,
        meta: { title: '测试套件', icon: 'Collection', breadcrumb: ['Web 测试', '测试套件'] },
      },
      {
        path: 'web-testing/executions',
        name: 'web-testing-executions',
        component: WebTestingView,
        meta: { title: '执行记录', icon: 'VideoPlay', breadcrumb: ['Web 测试', '执行记录'] },
      },
      {
        path: 'web-testing/pom',
        name: 'web-testing-pom',
        component: WebTestingView,
        meta: { title: 'POM 管理', icon: 'Files', breadcrumb: ['Web 测试', 'POM 管理'] },
      },
      {
        path: 'web-testing/midscene',
        name: 'web-testing-midscene',
        component: WebTestingView,
        meta: { title: 'MidScene 脚本', icon: 'Cpu', breadcrumb: ['Web 测试', 'MidScene 脚本'] },
      },

      // App 测试
      {
        path: 'app-testing',
        name: 'app-testing',
        component: AppTestingView,
        meta: { title: 'App 测试', icon: 'Iphone', breadcrumb: ['App 测试', '测试总览'] },
      },
      {
        path: 'app-testing/applications',
        name: 'app-testing-applications',
        component: AppTestingView,
        meta: { title: '应用管理', icon: 'Platform', breadcrumb: ['App 测试', '应用管理'] },
      },
      {
        path: 'app-testing/cases',
        name: 'app-testing-cases',
        component: AppTestingView,
        meta: { title: '用例管理', icon: 'Tickets', breadcrumb: ['App 测试', '用例管理'] },
      },
      {
        path: 'app-testing/suites',
        name: 'app-testing-suites',
        component: AppTestingView,
        meta: { title: '测试套件', icon: 'Collection', breadcrumb: ['App 测试', '测试套件'] },
      },
      {
        path: 'app-testing/runs',
        name: 'app-testing-runs',
        component: AppTestingView,
        meta: { title: '运行记录', icon: 'VideoPlay', breadcrumb: ['App 测试', '运行记录'] },
      },
      {
        path: 'app-testing/devices',
        name: 'app-testing-devices',
        component: AppTestingView,
        meta: { title: '设备管理', icon: 'Cellphone', breadcrumb: ['App 测试', '设备管理'] },
      },

      // 性能测试
      {
        path: 'performance',
        name: 'performance',
        component: PerformanceView,
        meta: { title: '性能测试', icon: 'TrendCharts', breadcrumb: ['性能测试', '测试总览'] },
      },
      {
        path: 'performance/configs',
        name: 'performance-configs',
        component: PerformanceView,
        meta: { title: '负载配置', icon: 'SetUp', breadcrumb: ['性能测试', '负载配置'] },
      },
      {
        path: 'performance/scenarios',
        name: 'performance-scenarios',
        component: PerformanceView,
        meta: { title: '测试场景', icon: 'Aim', breadcrumb: ['性能测试', '测试场景'] },
      },
      {
        path: 'performance/executions',
        name: 'performance-executions',
        component: PerformanceView,
        meta: { title: '执行记录', icon: 'VideoPlay', breadcrumb: ['性能测试', '执行记录'] },
      },
      {
        path: 'performance/diagnoses',
        name: 'performance-diagnoses',
        component: PerformanceView,
        meta: { title: 'AI 诊断', icon: 'MagicStick', breadcrumb: ['性能测试', 'AI 诊断'] },
      },
      {
        path: 'monitoring',
        name: 'monitoring',
        component: MonitoringView,
        meta: { title: '监控大盘', icon: 'DataLine', breadcrumb: ['性能测试', '监控大盘'] },
      },

      // AI 中心
      {
        path: 'ai-core',
        name: 'ai-core',
        component: AiCoreView,
        meta: { title: 'AI 中心', icon: 'MagicStick', breadcrumb: ['AI 中心', '能力总览'] },
      },
      {
        path: 'ai-core/models',
        name: 'ai-core-models',
        component: AiCoreView,
        meta: { title: '模型配置', icon: 'Cpu', breadcrumb: ['AI 中心', '模型配置'] },
      },
      {
        path: 'ai-core/rag',
        name: 'ai-core-rag',
        component: AiCoreView,
        meta: { title: 'RAG 配置', icon: 'Search', breadcrumb: ['AI 中心', 'RAG 配置'] },
      },
      {
        path: 'ai-core/mcp',
        name: 'ai-core-mcp',
        component: AiCoreView,
        meta: { title: 'MCP 工具', icon: 'Tools', breadcrumb: ['AI 中心', 'MCP 工具'] },
      },
      {
        path: 'ai-core/usage',
        name: 'ai-core-usage',
        component: AiCoreView,
        meta: { title: '用量统计', icon: 'DataAnalysis', breadcrumb: ['AI 中心', '用量统计'] },
      },
      {
        path: 'ai-core/playground',
        name: 'ai-core-playground',
        component: AiCoreView,
        meta: { title: 'Agent 调试', icon: 'ChatDotRound', breadcrumb: ['AI 中心', 'Agent 调试'] },
      },

      // 定时任务
      {
        path: 'scheduled-tasks',
        name: 'scheduled-tasks',
        component: ScheduledTasksView,
        meta: { title: '定时任务', icon: 'Timer', breadcrumb: ['定时任务', '任务列表'] },
      },
      {
        path: 'scheduled-tasks/logs',
        name: 'scheduled-tasks-logs',
        component: ScheduledTasksView,
        meta: { title: '执行日志', icon: 'Document', breadcrumb: ['定时任务', '执行日志'] },
      },

      // 通知中心
      {
        path: 'notifications',
        name: 'notifications',
        component: NotificationsView,
        meta: { title: '通知中心', icon: 'Bell', breadcrumb: ['通知中心', '通知总览'] },
      },
      {
        path: 'notifications/channels',
        name: 'notifications-channels',
        component: NotificationsView,
        meta: { title: '渠道配置', icon: 'SetUp', breadcrumb: ['通知中心', '渠道配置'] },
      },
      {
        path: 'notifications/receivers',
        name: 'notifications-receivers',
        component: NotificationsView,
        meta: { title: '接收人', icon: 'User', breadcrumb: ['通知中心', '接收人'] },
      },
      {
        path: 'notifications/email',
        name: 'notifications-email',
        component: NotificationsView,
        meta: { title: '邮件配置', icon: 'Message', breadcrumb: ['通知中心', '邮件配置'] },
      },
      {
        path: 'notifications/logs',
        name: 'notifications-logs',
        component: NotificationsView,
        meta: { title: '发送日志', icon: 'Document', breadcrumb: ['通知中心', '发送日志'] },
      },

      // 个人中心
      {
        path: 'profile',
        name: 'profile',
        component: () => import('@/views/profile/index.vue'),
        meta: { title: '个人中心', icon: 'User', breadcrumb: ['个人中心'], hidden: true },
      },

      // 404
      {
        path: ':pathMatch(.*)*',
        name: 'not-found',
        component: () => import('@/views/not-found/index.vue'),
        meta: { title: '页面不存在', breadcrumb: ['页面不存在'], hidden: true },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL || '/'),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

const DEFAULT_TITLE = 'AITS 智能测试平台'

router.beforeEach(async (to) => {
  NProgress.start()
  document.title = to.meta?.title ? `${to.meta.title} - ${DEFAULT_TITLE}` : DEFAULT_TITLE

  const auth = useAuthStore()
  auth.syncTokens()

  if (to.meta?.public) {
    if (auth.isLoggedIn && to.name === 'login') {
      return { name: 'dashboard' }
    }
    return true
  }

  if (!auth.isLoggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch (error) {
      console.warn('[router] 获取当前用户失败，跳转登录', error)
      auth.clearSession()
      return { name: 'login', query: { redirect: to.fullPath } }
    }
  }

  return true
})

router.afterEach(() => {
  NProgress.done()
})

router.onError((error) => {
  NProgress.done()
  console.error('[router] navigation error', error)
})

export default router
