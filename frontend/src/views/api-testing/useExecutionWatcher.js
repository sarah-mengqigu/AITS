/**
 * 执行进度跟踪：优先 WebSocket（`ws/task-status/<execution_id>/`），
 * 连接失败 / 3 秒无进度 / 连接中断时自动降级为 2s 轮询执行详情，
 * 直到执行进入终态（passed / failed / error / cancelled）。
 */
import { onBeforeUnmount, reactive } from 'vue'

import { apiTestingApi } from '@/api/apiTesting'
import { createTaskSocket } from '@/utils/ws'
import {
  clampProgress,
  getExecutionStatusMeta,
  isExecutionTerminal,
  progressFromExecution,
} from './utils'

const POLL_INTERVAL = 2000
const WS_IDLE_TIMEOUT = 3000
const MAX_POLL_ATTEMPTS = 150

export function useExecutionWatcher({ onFinish } = {}) {
  const state = reactive({
    executionId: null,
    running: false,
    status: '',
    statusLabel: '',
    tagType: 'info',
    progress: 0,
    message: '',
    execution: null,
    channel: 'idle',
    error: '',
  })

  let socket = null
  let pollTimer = null
  let watchdogTimer = null
  let pollAttempts = 0

  function clearTimers() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    if (watchdogTimer) {
      clearTimeout(watchdogTimer)
      watchdogTimer = null
    }
  }

  function closeSocket() {
    if (!socket) return
    try {
      socket.close(1000, 'watcher finished')
    } catch {
      // 忽略关闭异常
    }
    socket = null
  }

  function teardown() {
    clearTimers()
    closeSocket()
  }

  function finish(execution) {
    if (!state.running) return
    state.running = false
    state.channel = 'done'
    teardown()
    if (typeof onFinish === 'function') {
      try {
        onFinish(execution || state.execution, state)
      } catch (error) {
        console.warn('[api-testing] onFinish handler failed', error)
      }
    }
  }

  function applyStatus(status, { progress, message } = {}) {
    const meta = getExecutionStatusMeta(status)
    state.status = meta.status || state.status
    state.statusLabel = meta.label
    state.tagType = meta.tagType
    if (progress !== undefined) state.progress = clampProgress(progress)
    if (message) state.message = message
    if (isExecutionTerminal(state.status)) {
      state.progress = 100
      if (!state.message) state.message = `执行结束：${meta.label}`
      finish(state.execution)
    }
  }

  function applyExecution(execution) {
    if (!execution || typeof execution !== 'object') return
    state.execution = execution
    const progress = progressFromExecution(execution)
    state.progress = progress
    applyStatus(execution.status, {
      progress,
      message:
        execution.error_message ||
        (execution.status === 'running' ? '执行中，正在收集用例结果…' : ''),
    })
  }

  function startPolling(reason = '') {
    if (pollTimer) return
    state.channel = 'polling'
    if (reason) state.message = reason
    closeSocket()
    pollOnce()
    pollTimer = setInterval(pollOnce, POLL_INTERVAL)
  }

  async function pollOnce() {
    if (!state.running || !state.executionId) return
    pollAttempts += 1
    if (pollAttempts > MAX_POLL_ATTEMPTS) {
      state.running = false
      state.channel = 'timeout'
      state.message = '长时间未获取到执行结果，已停止跟踪，可稍后在执行记录中查看'
      teardown()
      return
    }
    try {
      const execution = await apiTestingApi.retrieveExecution(state.executionId)
      state.error = ''
      applyExecution(execution)
    } catch (error) {
      state.error = error?.message || '执行状态获取失败'
      state.message = '执行状态获取失败，正在重试…'
    }
  }

  function armWatchdog() {
    if (watchdogTimer) clearTimeout(watchdogTimer)
    watchdogTimer = setTimeout(() => {
      watchdogTimer = null
      if (state.running && state.channel === 'ws') {
        startPolling('实时进度中断，已切换为轮询执行状态')
      }
    }, WS_IDLE_TIMEOUT)
  }

  function handleSocketMessage(payload) {
    if (!state.running || !payload || typeof payload !== 'object') return
    if (payload.type && payload.type !== 'task_status') return
    if (payload.task_id !== undefined && String(payload.task_id) !== String(state.executionId)) {
      return
    }
    applyStatus(payload.status, {
      progress: payload.progress,
      message: payload.message,
    })
    if (state.running) armWatchdog()
  }

  function handleSocketStatus(status) {
    if (!state.running) return
    if (state.channel !== 'ws') return
    if (['failed', 'closed', 'error', 'unsupported'].includes(status)) {
      startPolling('实时连接不可用，已切换为轮询执行状态')
    }
  }

  function start(executionId) {
    teardown()
    pollAttempts = 0
    state.executionId = executionId ?? null
    state.running = Boolean(executionId)
    state.status = 'pending'
    state.statusLabel = '等待中'
    state.tagType = 'info'
    state.progress = 1
    state.message = '任务已提交，等待执行…'
    state.execution = null
    state.channel = 'ws'
    state.error = ''
    if (!executionId) {
      state.running = false
      state.error = '缺少执行 ID，无法跟踪进度'
      return
    }
    try {
      socket = createTaskSocket(String(executionId), {
        reconnect: false,
        maxRetries: 0,
        onMessage: handleSocketMessage,
        onStatusChange: handleSocketStatus,
      })
      socket.connect()
      armWatchdog()
    } catch (error) {
      startPolling('无法建立实时连接，已切换为轮询执行状态')
    }
  }

  function stop() {
    if (!state.running) {
      teardown()
      return
    }
    state.running = false
    state.channel = 'stopped'
    state.message = '已停止跟踪执行进度，执行仍会在后台继续'
    teardown()
  }

  onBeforeUnmount(teardown)

  return { state, start, stop, refresh: pollOnce }
}

export default useExecutionWatcher
