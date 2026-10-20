<template>
  <el-dialog
    :model-value="modelValue"
    :title="title || '执行进度'"
    width="620px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    @update:model-value="handleVisibleChange"
    @closed="handleClosed"
  >
    <div class="progress-dialog">
      <el-progress
        :percentage="watcher.state.progress"
        :status="progressStatus"
        :stroke-width="12"
        :duration="3"
      />
      <div class="progress-dialog__meta">
        <el-tag :type="watcher.state.tagType" size="small" effect="light">
          {{ watcher.state.statusLabel || '准备中' }}
        </el-tag>
        <span class="text-small text-muted">{{ watcher.state.message || '正在等待执行结果…' }}</span>
      </div>

      <el-alert
        v-if="watcher.state.error"
        class="mt-16"
        :title="watcher.state.error"
        type="error"
        show-icon
        :closable="false"
      />

      <el-descriptions
        v-if="watcher.state.execution"
        class="mt-16"
        :column="2"
        size="small"
        border
      >
        <el-descriptions-item label="执行名称">
          {{ watcher.state.execution.name || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          {{ watcher.state.statusLabel }}
        </el-descriptions-item>
        <el-descriptions-item label="用例总数">
          {{ watcher.state.execution.total ?? 0 }}
        </el-descriptions-item>
        <el-descriptions-item label="通过 / 失败">
          {{ watcher.state.execution.passed ?? 0 }} / {{ watcher.state.execution.failed ?? 0 }}
        </el-descriptions-item>
        <el-descriptions-item label="通过率">
          {{ formatPercent(watcher.state.execution.pass_rate) }}
        </el-descriptions-item>
        <el-descriptions-item label="耗时">
          {{ formatDuration(watcher.state.execution.duration_ms) }}
        </el-descriptions-item>
      </el-descriptions>

      <p class="progress-dialog__hint">
        优先通过 WebSocket 订阅实时进度；连接不可用时自动降级为每 2 秒轮询执行详情。
      </p>
    </div>

    <template #footer>
      <el-button v-if="watcher.state.running" @click="handleStop">停止跟踪</el-button>
      <el-button
        v-if="watcher.state.executionId"
        type="primary"
        plain
        @click="emit('open-detail', watcher.state.executionId)"
      >
        查看执行详情
      </el-button>
      <el-button type="primary" @click="close">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, watch } from 'vue'

import { formatDuration, formatPercent } from '@/utils/format'
import { useExecutionWatcher } from '../useExecutionWatcher'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  executionId: { type: [Number, String], default: null },
  title: { type: String, default: '执行进度' },
})

const emit = defineEmits(['update:modelValue', 'finished', 'open-detail'])

const watcher = useExecutionWatcher({
  onFinish: (execution) => emit('finished', execution),
})

const progressStatus = computed(() => {
  const status = watcher.state.status
  if (status === 'passed') return 'success'
  if (status === 'failed' || status === 'error') return 'exception'
  if (status === 'cancelled') return 'warning'
  return undefined
})

function handleVisibleChange(value) {
  emit('update:modelValue', value)
}

watch(
  () => [props.modelValue, props.executionId],
  ([visible, executionId]) => {
    if (visible && executionId) watcher.start(executionId)
    if (!visible) watcher.stop()
  },
  { immediate: true },
)

function handleStop() {
  watcher.stop()
}

function close() {
  emit('update:modelValue', false)
}

function handleClosed() {
  watcher.stop()
}
</script>

<style scoped>
.progress-dialog__meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.progress-dialog__hint {
  margin: 16px 0 0;
  font-size: 12px;
  color: var(--aits-text-secondary);
  line-height: 1.6;
}
</style>
