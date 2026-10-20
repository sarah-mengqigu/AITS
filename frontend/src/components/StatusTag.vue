<template>
  <el-tag :type="tagType" :size="size" effect="light" disable-transitions>
    <span v-if="showDot" class="status-dot" :style="{ backgroundColor: dotColor }" />
    {{ label }}
  </el-tag>
</template>

<script setup>
import { computed } from 'vue'

import { getStatusColor, getStatusTagType, getStatusText } from '@/utils/format'

const props = defineProps({
  status: { type: [String, Number], default: '' },
  text: { type: String, default: '' },
  type: { type: String, default: '' },
  size: { type: String, default: 'default' },
  showDot: { type: Boolean, default: false },
  fallback: { type: String, default: '未知' },
})

const label = computed(() => props.text || getStatusText(props.status, props.fallback))
const tagType = computed(() => props.type || getStatusTagType(props.status))
const dotColor = computed(() => getStatusColor(props.status))
</script>

<style scoped>
.status-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 4px;
  border-radius: 50%;
  vertical-align: middle;
}
</style>
