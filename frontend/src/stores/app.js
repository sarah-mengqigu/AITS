import { defineStore } from 'pinia'

/** 应用外壳状态：侧边栏折叠、面包屑。 */
export const useAppStore = defineStore('app', {
  state: () => ({
    sidebarCollapsed: false,
    breadcrumb: [],
  }),

  actions: {
    toggleSidebar(value) {
      this.sidebarCollapsed = typeof value === 'boolean' ? value : !this.sidebarCollapsed
    },

    setSidebarCollapsed(value) {
      this.sidebarCollapsed = Boolean(value)
    },

    setBreadcrumb(items = []) {
      this.breadcrumb = Array.isArray(items) ? items : []
    },
  },

  persist: {
    key: 'aits-app',
    paths: ['sidebarCollapsed'],
  },
})
