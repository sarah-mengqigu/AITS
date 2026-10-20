<template>
  <el-button
    :type="type"
    :size="size"
    :plain="plain"
    :link="link"
    :disabled="disabled"
    :loading="loading"
    @click="handleClick"
  >
    <el-icon v-if="icon" style="margin-right: 4px"><component :is="icon" /></el-icon>
    <slot>{{ text }}</slot>
  </el-button>
</template>

<script setup>
import { ElMessageBox } from 'element-plus'

const props = defineProps({
  text: { type: String, default: '删除' },
  title: { type: String, default: '操作确认' },
  content: { type: String, default: '确定执行该操作吗？该操作不可撤销。' },
  confirmButtonText: { type: String, default: '确定' },
  cancelButtonText: { type: String, default: '取消' },
  type: { type: String, default: 'danger' },
  size: { type: String, default: 'default' },
  icon: { type: [Object, Function, String], default: null },
  plain: { type: Boolean, default: false },
  link: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['confirm'])

async function handleClick() {
  try {
    await ElMessageBox.confirm(props.content, props.title, {
      confirmButtonText: props.confirmButtonText,
      cancelButtonText: props.cancelButtonText,
      type: props.type === 'danger' ? 'warning' : 'info',
      autofocus: false,
    })
    emit('confirm')
  } catch (error) {
    // 用户取消或关闭弹窗
  }
}
</script>
