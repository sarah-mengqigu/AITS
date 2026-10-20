<template>
  <div class="agents">
    <el-alert
      v-if="loadError"
      type="error"
      show-icon
      :closable="false"
      :title="loadError"
      description="无法获取 Agent 列表，请确认后端 /api/ai/agents/ 接口可用。"
    />

    <div class="agents__grid">
      <div class="page-card agents__side">
        <div class="card-title">
          <span>Agent 选择</span>
          <el-button :icon="Refresh" link size="small" @click="loadAgents">刷新</el-button>
        </div>
        <el-select
          v-model="agentName"
          class="w-full"
          filterable
          placeholder="选择 Agent"
          :loading="agentsLoading"
          @change="handleAgentChange"
        >
          <el-option
            v-for="agent in agents"
            :key="agent.name"
            :label="agent.name"
            :value="agent.name"
          >
            <span class="mono">{{ agent.name }}</span>
          </el-option>
        </el-select>

        <p class="agents__desc">{{ currentAgent?.description || '选择 Agent 后查看说明与示例请求体' }}</p>

        <div class="agents__stream">
          <el-switch v-model="streamEnabled" size="small" />
          <span class="text-small">订阅流式输出（ws/&lt;channel&gt;-streaming/）</span>
        </div>
        <div v-if="streamEnabled" class="agents__stream-status">
          <el-tag size="small" :type="streamTagType" effect="plain">{{ streamStatusText }}</el-tag>
          <span class="text-small text-muted">{{ streamChannel || '该 Agent 未声明流式通道' }}</span>
        </div>

        <el-divider />

        <div class="agents__actions">
          <el-button size="small" @click="fillSample">填充示例</el-button>
          <el-button size="small" @click="formatPayload">格式化</el-button>
          <el-button size="small" @click="clearPayload">清空</el-button>
        </div>
      </div>

      <div class="page-card agents__main">
        <div class="card-title">
          <span>请求体（JSON）</span>
          <span class="text-small text-muted">POST /api/ai/agents/{{ agentName || '{name}' }}/run/</span>
        </div>
        <el-input
          v-model="payloadText"
          type="textarea"
          :rows="14"
          class="mono-input"
          placeholder="按 Agent 要求填写 JSON 请求体"
        />
        <el-alert
          v-if="payloadError"
          class="mt-8"
          type="error"
          show-icon
          :closable="false"
          :title="payloadError"
        />

        <div class="agents__run">
          <el-button
            type="primary"
            :icon="VideoPlay"
            :loading="running"
            :disabled="!agentName"
            @click="handleRun"
          >
            {{ running ? '运行中…' : '运行 Agent' }}
          </el-button>
          <span v-if="runError" class="text-danger text-small">{{ runError }}</span>
          <span v-else-if="result" class="text-small text-muted">
            耗时 {{ formatDuration(result.elapsed_ms) }} ·
            Token {{ formatNumber(usage.total_tokens) }} ·
            模型调用 {{ formatNumber(usage.calls) }} 次
          </span>
        </div>
      </div>
    </div>

    <div v-if="result" class="page-card">
      <div class="card-title">
        <span>
          运行结果
          <StatusTag class="ml-8" :status="result.status === 'success' ? 'success' : 'failed'" :text="result.status === 'success' ? '成功' : '失败'" />
        </span>
        <span class="text-small text-muted">Agent：{{ result.agent || agentName }}</span>
      </div>

      <el-alert
        v-if="result.status !== 'success'"
        type="error"
        show-icon
        :closable="false"
        :title="result.error || 'Agent 执行失败'"
        :description="result.code ? `错误码：${result.code}` : ''"
      />

      <div class="agents__result">
        <div class="agents__panel">
          <div class="agents__panel-title">结构化输出</div>
          <JsonViewer :value="result.result ?? result" title="result" :max-height="420" />
        </div>
        <div class="agents__panel">
          <div class="agents__panel-title">执行步骤时间线（{{ steps.length }} 步）</div>
          <EmptyState v-if="!steps.length" title="该 Agent 未返回步骤信息" :image-size="64" />
          <el-timeline v-else class="steps">
            <el-timeline-item
              v-for="step in steps"
              :key="step.index"
              :timestamp="`#${step.index}`"
              placement="top"
              :type="step.status === 'error' ? 'danger' : 'success'"
            >
              <div class="step-node">{{ step.node }}</div>
              <div v-if="step.summary" class="step-summary">{{ step.summary }}</div>
            </el-timeline-item>
          </el-timeline>
        </div>
      </div>

      <el-collapse class="mt-16">
        <el-collapse-item title="原始 steps / usage（JSON）" name="raw">
          <JsonViewer :value="{ steps: result.steps, usage: result.usage }" title="raw" :max-height="360" />
        </el-collapse-item>
      </el-collapse>
    </div>

    <div v-if="streamEnabled && streamEvents.length" class="page-card">
      <div class="card-title">
        <span>流式事件（{{ streamEvents.length }}）</span>
        <el-button link type="primary" size="small" @click="streamEvents = []">清空</el-button>
      </div>
      <pre class="stream-log">{{ streamLogText }}</pre>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, VideoPlay } from '@element-plus/icons-vue'

import StatusTag from '@/components/StatusTag.vue'
import EmptyState from '@/components/EmptyState.vue'
import JsonViewer from '@/components/JsonViewer.vue'
import { aiCoreApi } from '@/api/aiCore'
import { createStreamSocket } from '@/utils/ws'
import { formatDuration, formatNumber } from '@/utils/format'

import {
  AGENT_STREAM_CHANNELS,
  createStreamTaskId,
  normalizeAgentSteps,
  parsePayloadText,
  samplePayloadFor,
  stringifyPayload,
} from './utils/agent'

const route = useRoute()

const agents = ref([])
const agentsLoading = ref(false)
const loadError = ref('')
const agentName = ref('')
const payloadText = ref('{}')
const payloadError = ref('')
const running = ref(false)
const runError = ref('')
const result = ref(null)
const steps = ref([])
const streamEnabled = ref(true)
const streamStatus = ref('idle')
const streamEvents = ref([])

let socket = null

const currentAgent = computed(() => agents.value.find((agent) => agent.name === agentName.value) || null)
const usage = computed(() => result.value?.usage || {})
const streamChannel = computed(() => AGENT_STREAM_CHANNELS[agentName.value] || '')
const streamStatusText = computed(() => {
  const map = {
    idle: '未连接',
    connecting: '连接中',
    open: '已连接',
    closed: '已关闭',
    reconnecting: '重连中',
    failed: '连接失败',
    unsupported: '浏览器不支持',
  }
  return map[streamStatus.value] || streamStatus.value
})
const streamTagType = computed(() => {
  if (streamStatus.value === 'open') return 'success'
  if (streamStatus.value === 'failed') return 'danger'
  if (streamStatus.value === 'connecting' || streamStatus.value === 'reconnecting') return 'warning'
  return 'info'
})
const streamLogText = computed(() =>
  streamEvents.value
    .map((event, index) => {
      let body = ''
      try {
        body = JSON.stringify(event.data)
      } catch (error) {
        body = String(event.data)
      }
      return `#${index + 1} ${body}`
    })
    .join('\n'),
)

async function loadAgents() {
  agentsLoading.value = true
  loadError.value = ''
  try {
    const data = await aiCoreApi.listAgents()
    agents.value = Array.isArray(data?.results) ? data.results : Array.isArray(data) ? data : []
    if (!agents.value.length) {
      loadError.value = 'Agent 列表为空'
    }
    const preferred = route.query.agent
    if (!agentName.value) {
      const matched = agents.value.find((agent) => agent.name === preferred)
      agentName.value = matched?.name || agents.value[0]?.name || ''
    }
    if (agentName.value && payloadText.value.trim() === '{}') {
      fillSample()
    }
  } catch (error) {
    agents.value = []
    loadError.value = error?.message || 'Agent 列表加载失败'
  } finally {
    agentsLoading.value = false
  }
}

function handleAgentChange() {
  payloadError.value = ''
  fillSample()
}

function fillSample() {
  const sample = samplePayloadFor(agentName.value)
  payloadText.value = stringifyPayload(sample)
  payloadError.value = ''
}

function formatPayload() {
  const parsed = parsePayloadText(payloadText.value)
  if (parsed.error) {
    payloadError.value = parsed.error
    return
  }
  payloadText.value = stringifyPayload(parsed.value)
  payloadError.value = ''
  ElMessage.success('已格式化')
}

function clearPayload() {
  payloadText.value = '{}'
  payloadError.value = ''
}

function closeSocket() {
  if (socket) {
    try {
      socket.close()
    } catch (error) {
      // 忽略关闭异常
    }
    socket = null
  }
}

function openSocket(name, taskId) {
  const channel = AGENT_STREAM_CHANNELS[name]
  if (!channel) return
  closeSocket()
  streamEvents.value = []
  socket = createStreamSocket(channel, {
    reconnect: false,
    maxRetries: 0,
    onStatusChange: (status) => {
      streamStatus.value = status
    },
    onMessage: (message) => {
      streamEvents.value.push({ at: Date.now(), data: message })
      if (streamEvents.value.length > 120) streamEvents.value.shift()
    },
  })
  socket.connect()
}

async function handleRun() {
  if (!agentName.value) {
    ElMessage.warning('请先选择 Agent')
    return
  }
  const parsed = parsePayloadText(payloadText.value)
  if (parsed.error) {
    payloadError.value = parsed.error
    ElMessage.warning(parsed.error)
    return
  }
  payloadError.value = ''
  runError.value = ''
  result.value = null
  steps.value = []
  running.value = true

  const streamTaskId = streamEnabled.value ? createStreamTaskId(agentName.value) : ''
  if (streamTaskId) openSocket(agentName.value, streamTaskId)

  try {
    const body = { payload: parsed.value }
    if (streamTaskId) body.stream_task_id = streamTaskId
    const data = await aiCoreApi.runAgent(agentName.value, body)
    result.value = data
    steps.value = normalizeAgentSteps(data?.steps)
    if (data?.status === 'success') {
      ElMessage.success('Agent 执行完成')
    } else {
      runError.value = data?.error || 'Agent 执行失败'
    }
    // 后端若返回自有 stream_task_id，则以它为准再订阅一次（兼容未来的流式协议）
    if (data?.stream_task_id && data.stream_task_id !== streamTaskId) {
      openSocket(agentName.value, data.stream_task_id)
    }
  } catch (error) {
    runError.value = error?.message || 'Agent 运行失败'
    ElMessage.error(runError.value)
  } finally {
    running.value = false
  }
}

onMounted(loadAgents)

onUnmounted(closeSocket)
</script>

<style scoped>
.agents {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.agents__grid {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
}

.agents__desc {
  margin: 12px 0 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--aits-text-secondary);
}

.agents__stream {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
}

.agents__stream-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.agents__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.agents__main {
  display: flex;
  flex-direction: column;
}

.mono-input :deep(textarea) {
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12.5px;
  line-height: 1.6;
}

.agents__run {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.agents__result {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 12px;
}

.agents__panel-title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.steps {
  max-height: 480px;
  overflow-y: auto;
  padding-right: 4px;
}

.step-node {
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12.5px;
  font-weight: 600;
  color: #1e293b;
}

.step-summary {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--aits-text-secondary);
  word-break: break-word;
}

.stream-log {
  max-height: 280px;
  margin: 0;
  padding: 12px;
  overflow: auto;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #e2e8f0;
  background: #0f172a;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
}

.ml-8 {
  margin-left: 8px;
}

.text-danger {
  color: #dc2626;
}

@media (max-width: 1200px) {
  .agents__grid {
    grid-template-columns: 1fr;
  }

  .agents__result {
    grid-template-columns: 1fr;
  }
}
</style>
