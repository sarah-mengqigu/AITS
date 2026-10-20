/**
 * 性能执行进度跟踪。
 *
 * 优先订阅 WebSocket：`ws/task-status/<execution_id>/`（`utils/ws.js`
 * 的 createTaskSocket）。4 秒内未建立连接、连接异常/断开、或连接后长时间
 * 收不到进度帧时，自动降级为每 2 秒轮询 `executions/<id>/`，直到执行进入
 * 终态（passed / failed / error / cancelled）。
 *
 * 组件卸载或显式 stop() 时释放 socket / 定时器，避免泄漏。
 */
import { onBeforeUnmount, reactive } from 'vue'

import { performanceApi } from '@/api/performance'
import { createTaskSocket } from '@/utils/ws'
import {
  clampProgress,
  getExecutionStatusMeta,
  isExecutionTerminal,
  progressFromExecution,
  readErrorMessage,
} from './index'

/** 建连超时：4 秒未连上即降级轮询。 */
export const WS_CONNECT_TIMEOUT = 4000
/** 连接成功后 6 秒没有进度帧也降级（任务可能在订阅前已结束）。 */
export const WS_IDLE_TIMEOUT = 6000
/** 降级轮询间隔。 */
export const POLL_INTERVAL = 2000
/** 最大轮询次数（约 5 分钟），避免无限轮询。 */
export const MAX_POLL_ATTEMPTS = 150

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
  let connectTimer = null
  let idleTimer = null
  let pollAttempts = 0

  function clearTimers() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    if (connectTimer) {
      clearTimeout(connectTimer)
      connectTimer = null
    }
    if (idleTimer) {
      clearTimeout(idleTimer)
      idleTimer = null
    }
  }

  function closeSocket() {
    if (!socket) return
    try {
      socket.close(1000, 'performance watcher finished')
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
        console.warn('[performance] onFinish handler failed', error)
      }
    }
  }

  function applyStatus(status, { progress, message } = {}) {
    const meta = getExecutionStatusMeta(status)
    if (meta.status) {
      state.status = meta.status
      state.statusLabel = meta.label
      state.tagType = meta.tagType
    }
    if (progress !== undefined && progress !== null) {
      state.progress = clampProgress(progress)
    }
    if (message) state.message = message
    if (isExecutionTerminal(state.status)) {
      state.progress = 100
      state.message = message || `执行结束：${meta.label}`
      finish(state.execution)
    }
  }

  function applyExecution(execution) {
    if (!state.running || !execution || typeof execution !== 'object') return
    state.execution = execution
    state.error = ''
    const progress = progressFromExecution(execution)
    // 轮询得到的进度是状态估算值，不回退 WebSocket 已推送的更高进度。
    state.progress = Math.max(state.progress, progress)
    applyStatus(execution.status, {
      progress: state.progress,
      message:
        execution.error_message ||
        (execution.status === 'running' ? '压测执行中，正在收集指标…' : ''),
    })
  }

  function startPolling(reason = '') {
    if (pollTimer) return
    state.channel = 'polling'
    if (reason) state.message = reason
    closeSocket()
    clearTimers()
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
      const execution = await performanceApi.retrieveExecution(state.executionId)
      applyExecution(execution)
    } catch (error) {
      state.error = readErrorMessage(error, '执行状态获取失败')
      state.message = '执行状态获取失败，正在重试…'
    }
  }

  function armIdleWatchdog() {
    if (idleTimer) clearTimeout(idleTimer)
    idleTimer = setTimeout(() => {
      idleTimer = null
      if (state.running && state.channel === 'ws') {
        startPolling('未收到实时进度，已切换为轮询执行状态')
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
    if (state.running) armIdleWatchdog()
  }

  function handleSocketStatus(status) {
    if (!state.running || state.channel !== 'ws') return
    if (status === 'open') {
      if (connectTimer) {
        clearTimeout(connectTimer)
        connectTimer = null
      }
      state.message = '实时进度已连接，等待压测结果…'
      armIdleWatchdog()
      return
    }
    if (['failed', 'closed', 'error', 'unsupported'].includes(status)) {
      startPolling('实时连接不可用，已切换为轮询执行状态')
    }
  }

  /** 开始跟踪一条执行记录；executionId 即后端返回的 execution_id / task_id。 */
  function start(executionId) {
    teardown()
    pollAttempts = 0
    state.executionId = executionId ?? null
    state.running = Boolean(executionId)
    state.status = 'pending'
    state.statusLabel = '等待中'
    state.tagType = 'info'
    state.progress = 2
    state.message = '压测任务已提交，等待执行器启动…'
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
      connectTimer = setTimeout(() => {
        connectTimer = null
        if (state.running && state.channel === 'ws') {
          startPolling('实时连接超时，已切换为轮询执行状态')
        }
      }, WS_CONNECT_TIMEOUT)
      // 兜底：Celery eager / 极短任务可能在订阅前已结束，先主动拉一次详情。
      pollOnce()
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
    state.message = '已停止跟踪执行进度，压测仍会在后台继续'
    teardown()
  }

  onBeforeUnmount(teardown)

  return { state, start, stop, refresh: pollOnce }
}

export default useExecutionWatcher
