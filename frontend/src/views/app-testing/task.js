/**
 * App 测试长任务订阅：优先 WebSocket（`ws/task-status/<task_id>/`），
 * 失败/超时后降级 2s 轮询 `GET runs/{id}/` 直到终态。
 */
import { createTaskSocket } from '@/utils/ws'

import { TERMINAL_STATUSES, normalizeTaskStatus } from './utils'

export function watchTask(taskId, options = {}) {
  const {
    fetchState,
    onProgress,
    onFinished,
    pollInterval = 2000,
    wsTimeout = 4000,
    maxDuration = 10 * 60 * 1000,
    terminalStatuses = TERMINAL_STATUSES,
  } = options

  let closed = false
  let finished = false
  let socket = null
  let pollTimer = null
  let wsTimer = null
  let durationTimer = null
  let polling = false
  let lastStatus = ''

  function cleanup() {
    clearTimeout(wsTimer)
    clearInterval(pollTimer)
    clearTimeout(durationTimer)
    wsTimer = null
    pollTimer = null
    durationTimer = null
    if (socket) {
      try {
        socket.close()
      } catch {
        // 忽略关闭异常
      }
      socket = null
    }
  }

  function emit(state) {
    if (closed || finished) return
    if (!state || !state.status) return
    if (state.status === lastStatus && state.progress === null) return
    lastStatus = state.status
    onProgress?.(state)
    if (terminalStatuses.includes(state.status)) finish(state)
  }

  function finish(state) {
    if (finished) return
    finished = true
    cleanup()
    onFinished?.(state)
  }

  async function pollOnce() {
    if (closed || finished || typeof fetchState !== 'function') return
    try {
      const result = await fetchState()
      emit(normalizeTaskStatus(result))
    } catch (error) {
      console.debug('[app-testing] 任务轮询失败，稍后重试', error?.message || error)
    }
  }

  function startPolling() {
    if (polling || closed || finished) return
    polling = true
    pollOnce()
    pollTimer = setInterval(pollOnce, pollInterval)
  }

  if (taskId !== null && taskId !== undefined && taskId !== '') {
    try {
      socket = createTaskSocket(taskId, {
        reconnect: false,
        maxRetries: 0,
        onOpen: () => {
          clearTimeout(wsTimer)
          wsTimer = null
        },
        onMessage: (payload) => emit(normalizeTaskStatus(payload)),
        onError: () => startPolling(),
        onClose: (event) => {
          if (!finished && !closed && event?.code !== 1000) startPolling()
        },
      })
      socket.connect()
    } catch (error) {
      console.debug('[app-testing] WS 订阅失败，使用轮询', error?.message || error)
      startPolling()
    }

    wsTimer = setTimeout(() => {
      if (!finished && !closed && socket?.status !== 'open') startPolling()
    }, wsTimeout)

    durationTimer = setTimeout(() => {
      if (!finished && !closed) startPolling()
    }, Math.min(wsTimeout * 4, maxDuration))
  } else if (typeof fetchState === 'function') {
    startPolling()
  }

  return {
    get finished() {
      return finished
    },
    close() {
      if (closed) return
      closed = true
      cleanup()
    },
  }
}

export default watchTask
