import axios from 'axios'

/**
 * 全局 axios 实例。
 *
 * - baseURL 固定为 `/api`（通过 Vite 代理到后端），生产由网关反代。
 * - 请求拦截注入 `Authorization: Bearer <access>`。
 * - 401 时使用 refresh token 换新 access（单飞：并发 401 只发起一次刷新）。
 * - 刷新失败：清空登录态，并回调由应用注册的未授权处理器（跳转登录页）。
 */

const RAW_API_BASE = import.meta.env?.VITE_API_BASE || '/api'
export const API_BASE = RAW_API_BASE.replace(/\/+$/, '') || '/api'

const REFRESH_URL = '/auth/refresh/'
const AUTH_URL_HINTS = ['/auth/login/', '/auth/register/', '/auth/refresh/']

let tokens = { access: '', refresh: '' }
const tokenListeners = new Set()
let unauthorizedHandler = null

export function getAuthTokens() {
  return { ...tokens }
}

export function setAuthTokens(next = {}) {
  tokens = {
    access: next.access ?? tokens.access ?? '',
    refresh: next.refresh ?? tokens.refresh ?? '',
  }
  tokenListeners.forEach((listener) => {
    try {
      listener(getAuthTokens())
    } catch (error) {
      // 订阅者异常不应影响请求流程
      console.warn('[auth] token listener failed', error)
    }
  })
  return getAuthTokens()
}

export function clearAuthTokens() {
  tokens = { access: '', refresh: '' }
  tokenListeners.forEach((listener) => {
    try {
      listener(getAuthTokens())
    } catch (error) {
      console.warn('[auth] token listener failed', error)
    }
  })
}

/** 订阅 token 变化（刷新后同步 Pinia store），返回取消订阅函数。 */
export function subscribeAuthTokens(listener) {
  if (typeof listener !== 'function') return () => {}
  tokenListeners.add(listener)
  return () => tokenListeners.delete(listener)
}

/** 注册 401 且刷新失败后的处理器（由 main.js 注入路由跳转逻辑）。 */
export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = typeof handler === 'function' ? handler : null
}

function handleUnauthorized(reason) {
  clearAuthTokens()
  if (unauthorizedHandler) {
    try {
      unauthorizedHandler(reason)
    } catch (error) {
      console.warn('[auth] unauthorized handler failed', error)
    }
  }
}

/** 从任意 DRF/业务错误结构中提取一条可读 message。 */
export function extractErrorMessage(error) {
  if (!error) return '未知错误'
  const data = error.response?.data
  if (data !== undefined && data !== null) {
    if (typeof data === 'string' && data.trim()) return data
    if (typeof data === 'object') {
      if (typeof data.message === 'string' && data.message) return data.message
      if (typeof data.detail === 'string' && data.detail) return data.detail
      const nested = firstErrorMessage(data.errors)
      if (nested) return nested
      const direct = firstErrorMessage(data)
      if (direct) return direct
    }
  }
  if (error.code === 'ECONNABORTED') return '请求超时，请稍后重试'
  if (!error.response) return '无法连接后端服务，请确认服务已启动或网络正常'
  if (error.response.status === 401) return '登录状态已失效，请重新登录'
  if (error.response.status === 403) return '没有权限执行该操作'
  if (error.response.status === 404) return '请求的资源不存在'
  if (error.response.status >= 500) return '服务器内部错误，请稍后重试'
  return error.message || `请求失败（${error.response.status}）`
}

function firstErrorMessage(value) {
  if (!value) return ''
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    for (const item of value) {
      const message = firstErrorMessage(item)
      if (message) return message
    }
    return ''
  }
  if (typeof value === 'object') {
    for (const key of Object.keys(value)) {
      const message = firstErrorMessage(value[key])
      if (message) return message
    }
  }
  return ''
}

export const client = axios.create({
  baseURL: API_BASE,
  timeout: 60000,
  headers: { Accept: 'application/json' },
})

client.interceptors.request.use((config) => {
  if (tokens.access && !config.skipAuth) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${tokens.access}`
  }
  return config
})

let refreshPromise = null

/** 使用 refresh token 换取新 access（单飞）。 */
export function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = performRefresh().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

async function performRefresh() {
  const refresh = tokens.refresh
  if (!refresh) {
    throw new Error('登录状态已失效，请重新登录')
  }
  // 使用裸 axios，避免与拦截器递归。
  const { data } = await axios.post(
    `${API_BASE}${REFRESH_URL}`,
    { refresh },
    { headers: { 'Content-Type': 'application/json' }, timeout: 20000 },
  )
  const access = data?.access
  if (!access) {
    throw new Error('刷新登录状态失败，请重新登录')
  }
  setAuthTokens({ access, refresh: data?.refresh || refresh })
  return access
}

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const { response, config } = error
    error.message = extractErrorMessage(error)
    if (!response || !config) return Promise.reject(error)

    const url = config.url || ''
    const isAuthRequest = AUTH_URL_HINTS.some((hint) => url.includes(hint))
    if (response.status !== 401 || config._retry || isAuthRequest) {
      return Promise.reject(error)
    }

    if (!tokens.refresh) {
      handleUnauthorized(error)
      return Promise.reject(error)
    }

    config._retry = true
    try {
      const access = await refreshAccessToken()
      config.headers = config.headers || {}
      config.headers.Authorization = `Bearer ${access}`
      return client(config)
    } catch (refreshError) {
      handleUnauthorized(refreshError)
      return Promise.reject(refreshError)
    }
  },
)

export default client
