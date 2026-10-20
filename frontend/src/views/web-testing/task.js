/**
 * 长任务订阅：优先 WebSocket（`ws/task-status/<task_id>/`），
 * 连接失败/超时后降级为 2s 轮询直到终态。
 *
 * 后端契约：执行/套件运行返回 202 `{task_id, execution_id}`，进度通过
 * `task_id` 对应的 WS 通道推送；轮询使用 `GET executions/{id}/`。
 */
import { createTaskSocket } from '@/utils/ws'

import { TERMINAL_STATUSES, normalizeTaskStatus } from './utils'

/**
 * @param {string|number} taskId
 * @param {object} options
 * @param {Function} options.fetchState 轮询函数，返回 `{status, progress, message}`
 * @param {Function} [options.onProgress]
 * @param {Function} [options.onFinished]
 * @param {number} [options.pollInterval=2000]
 * @param {number} [options.wsTimeout=4000]
 * @param {number} [options.maxDuration=600000]
 */
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
      // 轮询失败保持静默重试，避免打断用户操作
      console.debug('[web-testing] 任务轮询失败，稍后重试', error?.message || error)
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
          // 异常关闭（非终态）→ 降级轮询
          if (!finished && !closed && event?.code !== 1000) startPolling()
        },
      })
      socket.connect()
    } catch (error) {
      console.debug('[web-testing] WS 订阅失败，使用轮询', error?.message || error)
      startPolling()
    }

    // WS 未在预期时间内建立 → 降级轮询（后端 channels 未启动等）
    wsTimer = setTimeout(() => {
      if (!finished && !closed && socket?.status !== 'open') startPolling()
    }, wsTimeout)

    // WS 已建立但长时间无终态消息 → 兜底轮询
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
