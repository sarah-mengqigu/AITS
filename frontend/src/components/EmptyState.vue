<template>
  <div class="empty-state">
    <el-empty :description="description || title" :image-size="imageSize">
      <p v-if="description && title" class="empty-state__title">{{ title }}</p>
      <div v-if="$slots.default" class="empty-state__action">
        <slot />
      </div>
    </el-empty>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '暂无数据' },
  description: { type: String, default: '' },
  imageSize: { type: Number, default: 96 },
})
</script>

<style scoped>
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  padding: 18px;
}

.empty-state__title {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--aits-text-secondary);
}

.empty-state__action {
  margin-top: 10px;
}

:deep(.el-empty__description) {
  margin-top: 6px;
}
</style>
