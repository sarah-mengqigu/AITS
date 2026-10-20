<template>
  <ModulePlaceholder
    module-name="App 测试"
    description="移动端应用、Sonic 设备代理、用例步骤转换与运行记录"
    :features="features"
    api-module="src/api/appTesting.js"
  />
</template>

<script setup>
import ModulePlaceholder from '@/components/ModulePlaceholder.vue'

const features = [
  'Android / iOS 应用信息管理',
  'Sonic 设备列表与实时远控（jmuxer）',
  'AITS 步骤 ↔ Sonic 步骤双向转换',
  '自然语言生成用例步骤（AI + 规则降级）',
  '测试套件在指定设备上执行',
  '运行记录与 Sonic 报告跳转',
]
</script>
