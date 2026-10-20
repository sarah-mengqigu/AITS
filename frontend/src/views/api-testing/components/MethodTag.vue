<template>
  <el-tag
    class="method-tag"
    :type="meta.tagType"
    :size="size"
    :effect="effect"
    disable-transitions
  >
    <span class="method-tag__dot" :style="{ backgroundColor: meta.color }" />
    {{ meta.label }}
  </el-tag>
</template>

<script setup>
import { computed } from 'vue'

import { getMethodMeta } from '../utils'

const props = defineProps({
  method: { type: String, default: '' },
  size: { type: String, default: 'small' },
  effect: { type: String, default: 'light' },
})

const meta = computed(() => getMethodMeta(props.method))
</script>

<style scoped>
.method-tag {
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-weight: 600;
  letter-spacing: 0.2px;
}

.method-tag__dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 4px;
  border-radius: 50%;
  vertical-align: middle;
}
</style>
