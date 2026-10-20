import { getAuthTokens } from '@/api/client'

/**
 * WebSocket 封装：带 token 连接、指数退避重连、消息订阅与主动关闭。
 *
 * 后端通道：
 * - 任务进度：ws/task-status/<task_id>/?token=<access>
 * - 流式生成：ws/<channel>-streaming/?token=<access>
 *   channel ∈ scenario_generation / midscene_script_generation /
 *            webui_test_generation / webui_auto_test
 */

const WS_BASE = import.meta.env?.VITE_WS_BASE || '/ws'

function defaultOrigin() {
  if (typeof window === 'undefined' || !window.location) return 'ws://127.0.0.1:8000'
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}`
}

/** 构造完整 ws URL；path 可为相对路径或完整 ws(s):// 地址。 */
export function buildWsUrl(path, token) {
  const raw = String(path ?? '').trim()
  let base = String(WS_BASE)
  const absolutePath = /^wss?:\/\//i.test(raw)
  let url

  if (absolutePath) {
    url = raw
  } else {
    if (!/^wss?:\/\//i.test(base)) {
      base = `${defaultOrigin()}${base.startsWith('/') ? '' : '/'}${base}`
    }
    let relative = raw.startsWith('/') ? raw.slice(1) : raw
    // 避免 /ws/ws/... 重复前缀
    if (base.endsWith('/ws') && relative.startsWith('ws/')) relative = relative.slice(3)
    url = `${base.replace(/\/+$/, '')}/${relative}`
  }

  if (token) {
    const separator = url.includes('?') ? '&' : '?'
    url = `${url}${separator}token=${encodeURIComponent(token)}`
  }
  return url
}

export function taskStatusSocketUrl(taskId, token) {
  return buildWsUrl(`task-status/${taskId}/`, token)
}

export function streamSocketUrl(channel, token) {
  return buildWsUrl(`${channel}-streaming/`, token)
}

function parseMessage(event) {
  const data = event?.data
  if (typeof data !== 'string') return data
  try {
    return JSON.parse(data)
  } catch {
    return data
  }
}

export class AITSWebSocket {
  constructor(path, options = {}) {
    this.path = path
    this.options = {
      reconnect: true,
      maxRetries: 5,
      baseDelay: 1000,
      maxDelay: 30000,
      token: null,
      ...options,
    }
    this.socket = null
    this.status = 'idle'
    this.retries = 0
    this.manualClosed = false
    this.reconnectTimer = null
    this.listeners = new Set()
    this.lastMessage = null
  }

  get handlers() {
    const { onMessage, onOpen, onClose, onError, onStatusChange } = this.options
    return { onMessage, onOpen, onClose, onError, onStatusChange }
  }

  setStatus(status) {
    this.status = status
    const { onStatusChange } = this.handlers
    if (typeof onStatusChange === 'function') onStatusChange(status)
    return status
  }

  connect() {
    if (typeof WebSocket === 'undefined') {
      this.setStatus('unsupported')
      return this
    }
    if (
      this.socket &&
      (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)
    ) {
      return this
    }
    this.manualClosed = false
    const token = this.options.token || getAuthTokens().access || ''
    const url = buildWsUrl(this.path, token)
    this.setStatus(this.retries > 0 ? 'reconnecting' : 'connecting')

    try {
      this.socket = new WebSocket(url)
    } catch (error) {
      this.setStatus('error')
      this.scheduleReconnect()
      return this
    }

    this.socket.onopen = (event) => {
      this.retries = 0
      this.setStatus('open')
      this.handlers.onOpen?.(event)
    }

    this.socket.onmessage = (event) => {
      const payload = parseMessage(event)
      this.lastMessage = payload
      this.handlers.onMessage?.(payload)
      this.listeners.forEach((listener) => {
        try {
          listener(payload)
        } catch (error) {
          console.warn('[ws] listener failed', error)
        }
      })
    }

    this.socket.onerror = (event) => {
      this.handlers.onError?.(event)
    }

    this.socket.onclose = (event) => {
      this.setStatus('closed')
      this.handlers.onClose?.(event)
      if (!this.manualClosed && this.options.reconnect) this.scheduleReconnect()
    }

    return this
  }

  scheduleReconnect() {
    if (this.manualClosed || !this.options.reconnect) return
    if (this.retries >= this.options.maxRetries) {
      this.setStatus('failed')
      return
    }
    this.retries += 1
    const delay = Math.min(
      this.options.baseDelay * 2 ** (this.retries - 1),
      this.options.maxDelay,
    )
    this.setStatus('reconnecting')
    clearTimeout(this.reconnectTimer)
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }

  send(payload) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return false
    const body = typeof payload === 'string' ? payload : JSON.stringify(payload)
    this.socket.send(body)
    return true
  }

  /** 订阅消息，返回取消订阅函数。 */
  subscribe(listener) {
    if (typeof listener !== 'function') return () => {}
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  close(code = 1000, reason = 'client closed') {
    this.manualClosed = true
    clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    if (this.socket) {
      try {
        this.socket.close(code, reason)
      } catch {
        // 忽略关闭异常
      }
      this.socket = null
    }
    this.setStatus('closed')
  }
}

export function createTaskSocket(taskId, options = {}) {
  return new AITSWebSocket(`task-status/${taskId}/`, options)
}

export function createStreamSocket(channel, options = {}) {
  return new AITSWebSocket(`${channel}-streaming/`, options)
}

export default AITSWebSocket
