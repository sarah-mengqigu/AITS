<template>
  <div class="step-editor">
    <div v-if="!rows.length" class="step-editor__empty">
      暂无步骤，点击「添加步骤」开始编排（AITS 步骤保存后会自动生成 Sonic 快照）
    </div>

    <div v-for="(row, index) in rows" :key="index" class="step-editor__row">
      <span class="step-editor__index">{{ index + 1 }}</span>
      <el-select
        v-model="row.action"
        class="step-editor__action"
        placeholder="动作"
        :disabled="disabled"
      >
        <el-option
          v-for="option in APP_STEP_ACTION_OPTIONS"
          :key="option.value"
          :label="option.label"
          :value="option.value"
        />
      </el-select>
      <el-input
        v-model="row.target"
        class="step-editor__field"
        placeholder="target：元素名 / 控件 / 方向"
        :disabled="disabled"
      />
      <el-input
        v-model="row.value"
        class="step-editor__field"
        placeholder="value：输入内容 / 断言值"
        :disabled="disabled"
      />
      <el-input
        v-model="row.expect"
        class="step-editor__field"
        placeholder="expect：期望结果"
        :disabled="disabled"
      />
      <div class="step-editor__ops">
        <el-button
          link
          type="primary"
          :icon="Top"
          :disabled="disabled || index === 0"
          title="上移"
          @click="move(index, -1)"
        />
        <el-button
          link
          type="primary"
          :icon="Bottom"
          :disabled="disabled || index === rows.length - 1"
          title="下移"
          @click="move(index, 1)"
        />
        <el-button
          link
          type="danger"
          :icon="Delete"
          :disabled="disabled"
          title="删除"
          @click="remove(index)"
        />
      </div>
    </div>

    <div class="step-editor__footer">
      <el-button size="small" :icon="Plus" :disabled="disabled" @click="add">添加步骤</el-button>
      <span class="text-small text-muted">共 {{ rows.length }} 步</span>
    </div>

    <el-alert
      v-if="errors.length"
      class="mt-8"
      type="error"
      :closable="false"
      show-icon
      title="步骤校验未通过"
    >
      <ul class="step-editor__errors">
        <li v-for="(message, index) in errors" :key="index">{{ message }}</li>
      </ul>
    </el-alert>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Bottom, Delete, Plus, Top } from '@element-plus/icons-vue'

import { APP_STEP_ACTION_OPTIONS, emptyAppStep, normalizeAppSteps } from './utils'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
  errors: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue'])

const rows = computed(() => normalizeAppSteps(props.modelValue))

function update(next) {
  emit('update:modelValue', next)
}

function add() {
  update([...rows.value, emptyAppStep()])
}

function remove(index) {
  update(rows.value.filter((_, position) => position !== index))
}

function move(index, offset) {
  const target = index + offset
  if (target < 0 || target >= rows.value.length) return
  const next = [...rows.value]
  const [item] = next.splice(index, 1)
  next.splice(target, 0, item)
  update(next)
}
</script>

<style scoped>
.step-editor__empty {
  padding: 14px;
  border: 1px dashed var(--aits-border);
  border-radius: 8px;
  color: var(--aits-text-secondary);
  font-size: 13px;
  text-align: center;
}

.step-editor__row {
  display: grid;
  grid-template-columns: 26px 150px repeat(3, minmax(0, 1fr)) 96px;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.step-editor__index {
  color: var(--aits-text-secondary);
  font-size: 12px;
  text-align: center;
}

.step-editor__ops {
  display: flex;
  gap: 2px;
}

.step-editor__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
}

.step-editor__errors {
  margin: 0;
  padding-left: 18px;
  font-size: 12.5px;
}
</style>
