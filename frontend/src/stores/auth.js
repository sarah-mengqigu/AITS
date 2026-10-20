import { defineStore } from 'pinia'

import { authApi } from '@/api/auth'
import {
  clearAuthTokens,
  getAuthTokens,
  setAuthTokens,
  subscribeAuthTokens,
} from '@/api/client'

const tokenSubscribedStores = new WeakSet()

/** 登录态：token / refreshToken / user，持久化到 localStorage。 */
export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: '',
    refreshToken: '',
    user: null,
    loading: false,
  }),

  getters: {
    isLoggedIn: (state) => Boolean(state.token),
    displayName: (state) =>
      state.user?.display_name ||
      state.user?.nickname ||
      state.user?.username ||
      '未登录',
    username: (state) => state.user?.username || '',
    avatar: (state) => state.user?.avatar || '',
    initials: (state) => {
      const name = state.user?.display_name || state.user?.nickname || state.user?.username || 'A'
      return String(name).slice(0, 1).toUpperCase()
    },
    isSuperuser: (state) => Boolean(state.user?.is_superuser),
  },

  actions: {
    /**
     * 页面刷新后 pinia 从 localStorage 恢复 token，这里把它同步到 axios 客户端，
     * 并订阅 401 刷新后的 token 变化，保证 store 与请求层一致。
     */
    syncTokens() {
      if (!tokenSubscribedStores.has(this)) {
        subscribeAuthTokens(({ access, refresh }) => {
          this.token = access
          this.refreshToken = refresh
        })
        tokenSubscribedStores.add(this)
      }
      if (!this.token) {
        const { access, refresh } = getAuthTokens()
        if (access) {
          this.token = access
          this.refreshToken = refresh
        }
        return
      }
      const current = getAuthTokens()
      if (current.access !== this.token || current.refresh !== this.refreshToken) {
        setAuthTokens({ access: this.token, refresh: this.refreshToken })
      }
    },

    async login(credentials) {
      this.loading = true
      try {
        const data = await authApi.login(credentials)
        if (!data?.access) throw new Error('登录响应缺少 access token')
        this.token = data.access
        this.refreshToken = data.refresh || ''
        this.user = data.user || null
        setAuthTokens({ access: this.token, refresh: this.refreshToken })
        if (!this.user) await this.fetchMe()
        return data
      } finally {
        this.loading = false
      }
    },

    async register(payload) {
      const data = await authApi.register(payload)
      if (data?.access) {
        this.token = data.access
        this.refreshToken = data.refresh || ''
        this.user = data.user || null
        setAuthTokens({ access: this.token, refresh: this.refreshToken })
      }
      return data
    },

    async fetchMe() {
      const user = await authApi.me()
      this.user = user
      return user
    },

    async updateMe(payload) {
      const user = await authApi.updateMe(payload)
      this.user = user
      return user
    },

    async changePassword(payload) {
      return authApi.changePassword(payload)
    },

    /** 退出登录：先尝试服务端拉黑 refresh，失败也不阻塞本地清理。 */
    async logout({ remote = true } = {}) {
      const refresh = this.refreshToken
      if (remote && refresh) {
        try {
          await authApi.logout(refresh)
        } catch (error) {
          console.warn('[auth] 服务端登出失败，继续清理本地登录态', error)
        }
      }
      this.clearSession()
    },

    clearSession() {
      this.token = ''
      this.refreshToken = ''
      this.user = null
      clearAuthTokens()
    },
  },

  persist: {
    key: 'aits-auth',
    paths: ['token', 'refreshToken', 'user'],
  },
})
