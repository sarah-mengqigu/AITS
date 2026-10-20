<template>
  <div class="json-viewer">
    <div v-if="title || copyable" class="json-viewer__header">
      <span class="json-viewer__title">{{ title }}</span>
      <el-button v-if="copyable" link type="primary" size="small" @click="handleCopy">
        复制 JSON
      </el-button>
    </div>
    <pre class="json-viewer__body" :style="{ maxHeight: `${maxHeight}px` }">{{ text }}</pre>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  value: { type: [Object, Array, String, Number, Boolean], default: null },
  title: { type: String, default: '' },
  maxHeight: { type: Number, default: 420 },
  copyable: { type: Boolean, default: true },
})

const text = computed(() => {
  const value = props.value
  if (value === null || value === undefined || value === '') return '（空）'
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2)
    } catch {
      return value
    }
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
})

async function handleCopy() {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text.value)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = text.value
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    ElMessage.error(`复制失败：${error?.message || '浏览器不支持'}`)
  }
}
</script>

<style scoped>
.json-viewer {
  border: 1px solid var(--aits-border);
  border-radius: 8px;
  overflow: hidden;
  background: #0f172a;
}

.json-viewer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: #1e293b;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}

.json-viewer__title {
  font-size: 12px;
  color: #cbd5e1;
}

.json-viewer__body {
  margin: 0;
  padding: 14px;
  overflow: auto;
  color: #e2e8f0;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12.5px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
