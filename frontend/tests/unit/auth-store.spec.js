import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'

vi.mock('@/api/auth', () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
    me: vi.fn(),
    updateMe: vi.fn(),
    changePassword: vi.fn(),
    logout: vi.fn(),
  },
}))

import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { clearAuthTokens, getAuthTokens, setAuthTokens } from '@/api/client'

const USER = {
  id: 1,
  username: 'alice',
  nickname: 'Alice',
  display_name: 'Alice',
  email: 'alice@example.com',
}

function createTestPinia() {
  const pinia = createPinia()
  pinia.use(piniaPluginPersistedstate)
  // Pinia 插件只有在安装到 app 后才会真正生效
  createApp({}).use(pinia)
  setActivePinia(pinia)
  return pinia
}

describe('stores/auth', () => {
  beforeEach(() => {
    createTestPinia()
    clearAuthTokens()
    vi.clearAllMocks()
  })

  it('登录成功后写入 token / 用户，并同步到请求层与 localStorage', async () => {
    authApi.login.mockResolvedValue({
      access: 'access-token',
      refresh: 'refresh-token',
      user: USER,
    })

    const store = useAuthStore()
    await store.login({ username: 'alice', password: 'secret' })

    expect(authApi.login).toHaveBeenCalledWith({ username: 'alice', password: 'secret' })
    expect(store.token).toBe('access-token')
    expect(store.refreshToken).toBe('refresh-token')
    expect(store.user).toEqual(USER)
    expect(store.isLoggedIn).toBe(true)
    expect(store.displayName).toBe('Alice')
    expect(store.loading).toBe(false)
    expect(getAuthTokens()).toEqual({ access: 'access-token', refresh: 'refresh-token' })

    const persisted = JSON.parse(localStorage.getItem('aits-auth'))
    expect(persisted.token).toBe('access-token')
    expect(persisted.refreshToken).toBe('refresh-token')
    expect(persisted.user.username).toBe('alice')
  })

  it('登录失败时记录错误且不写入登录态', async () => {
    authApi.login.mockRejectedValue(new Error('用户名或密码错误'))

    const store = useAuthStore()
    await expect(store.login({ username: 'alice', password: 'bad' })).rejects.toThrow(
      '用户名或密码错误',
    )

    expect(store.token).toBe('')
    expect(store.user).toBeNull()
    expect(store.loading).toBe(false)
    expect(store.isLoggedIn).toBe(false)
  })

  it('登录响应缺少 access 时抛出错误', async () => {
    authApi.login.mockResolvedValue({ refresh: 'refresh-token' })
    const store = useAuthStore()
    await expect(store.login({ username: 'alice', password: 'secret' })).rejects.toThrow(
      '登录响应缺少 access token',
    )
    expect(store.token).toBe('')
  })

  it('登录未返回 user 时自动调用 me 拉取当前用户', async () => {
    authApi.login.mockResolvedValue({ access: 'a', refresh: 'r' })
    authApi.me.mockResolvedValue(USER)

    const store = useAuthStore()
    await store.login({ username: 'alice', password: 'secret' })

    expect(authApi.me).toHaveBeenCalledTimes(1)
    expect(store.user).toEqual(USER)
  })

  it('登出调用服务端接口并清空登录态（含请求层与持久化）', async () => {
    authApi.login.mockResolvedValue({ access: 'a', refresh: 'r', user: USER })
    authApi.logout.mockResolvedValue({ detail: '已退出登录' })

    const store = useAuthStore()
    await store.login({ username: 'alice', password: 'secret' })
    await store.logout()

    expect(authApi.logout).toHaveBeenCalledWith('r')
    expect(store.token).toBe('')
    expect(store.refreshToken).toBe('')
    expect(store.user).toBeNull()
    expect(getAuthTokens()).toEqual({ access: '', refresh: '' })
    expect(JSON.parse(localStorage.getItem('aits-auth')).token).toBe('')
  })

  it('服务端登出失败时仍清理本地登录态', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    authApi.login.mockResolvedValue({ access: 'a', refresh: 'r', user: USER })
    authApi.logout.mockRejectedValue(new Error('network down'))

    const store = useAuthStore()
    await store.login({ username: 'alice', password: 'secret' })
    await store.logout()

    expect(store.token).toBe('')
    expect(store.user).toBeNull()
    warnSpy.mockRestore()
  })

  it('syncTokens 将持久化的 token 同步到请求层', () => {
    const store = useAuthStore()
    store.token = 'persisted-access'
    store.refreshToken = 'persisted-refresh'
    clearAuthTokens()

    store.syncTokens()

    expect(getAuthTokens()).toEqual({
      access: 'persisted-access',
      refresh: 'persisted-refresh',
    })
  })

  it('刷新 token 时 store 通过订阅同步更新', () => {
    const store = useAuthStore()
    store.token = 'old'
    store.refreshToken = 'r'
    store.syncTokens()

    // 模拟 client 在 401 refresh 后更新 token
    setAuthTokens({ access: 'new', refresh: 'r2' })

    expect(store.token).toBe('new')
    expect(store.refreshToken).toBe('r2')
  })
})
