<template>
  <ModulePlaceholder
    module-name="Web 测试"
    description="模块树、UI 用例、POM 页面对象、MidScene 脚本与 Playwright 执行"
    :features="features"
    api-module="src/api/webTesting.js"
  />
</template>

<script setup>
import ModulePlaceholder from '@/components/ModulePlaceholder.vue'

const features = [
  'Web UI 测试模块树管理',
  'UI / 混合用例编辑与步骤编排',
  'Playwright 脚本 AI 生成（失败降级模板）',
  'POM 页面与元素定位器管理',
  'MidScene 自然语言脚本生成',
  '测试套件执行、截图与 Allure 报告查看',
]
</script>
