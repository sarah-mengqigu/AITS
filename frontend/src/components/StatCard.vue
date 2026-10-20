<template>
  <div class="stat-card">
    <div class="stat-card__body">
      <div class="stat-card__label">{{ label }}</div>
      <div class="stat-card__value" :style="{ color: valueColor }">
        <el-skeleton v-if="loading" animated :rows="0">
          <template #template>
            <el-skeleton-item variant="text" style="width: 60%; height: 28px" />
          </template>
        </el-skeleton>
        <template v-else>
          {{ value ?? '—' }}
          <span v-if="suffix" class="stat-card__suffix">{{ suffix }}</span>
        </template>
      </div>
      <div v-if="hint" class="stat-card__hint">{{ hint }}</div>
    </div>
    <div v-if="icon" class="stat-card__icon" :style="{ backgroundColor: iconBg, color: iconColor }">
      <el-icon :size="22"><component :is="icon" /></el-icon>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], default: null },
  suffix: { type: String, default: '' },
  hint: { type: String, default: '' },
  icon: { type: [Object, Function, String], default: null },
  color: { type: String, default: '#0f172a' },
  iconColor: { type: String, default: '#2563eb' },
  iconBg: { type: String, default: '#e9effd' },
  loading: { type: Boolean, default: false },
})

const valueColor = computed(() => props.color)
</script>

<style scoped>
.stat-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px;
  background: #fff;
  border: 1px solid var(--aits-border);
  border-radius: var(--aits-radius);
  box-shadow: var(--aits-shadow);
  transition:
    transform 0.15s ease,
    box-shadow 0.15s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(15, 23, 42, 0.08);
}

.stat-card__label {
  font-size: 13px;
  color: var(--aits-text-secondary);
}

.stat-card__value {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 600;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

.stat-card__suffix {
  margin-left: 4px;
  font-size: 13px;
  font-weight: 400;
  color: var(--aits-text-secondary);
}

.stat-card__hint {
  margin-top: 6px;
  font-size: 12px;
  color: #94a3b8;
}

.stat-card__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 46px;
  border-radius: 12px;
  flex-shrink: 0;
}
</style>
