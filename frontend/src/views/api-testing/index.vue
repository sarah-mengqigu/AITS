<template>
  <ModulePlaceholder
    module-name="API 测试"
    description="OpenAPI / Postman 规范导入、模块树、端点、用例、套件与执行报告"
    :features="features"
    api-module="src/api/apiTesting.js"
  />
</template>

<script setup>
import ModulePlaceholder from '@/components/ModulePlaceholder.vue'

const features = [
  'OpenAPI / Swagger / Postman 规范导入与解析',
  '接口模块树与端点列表（按 method / module / search 过滤）',
  'AI / 规则生成 API 测试用例',
  'HttpRunner YAML 脚本生成与单用例执行',
  '测试套件批量执行与 WebSocket 实时进度',
  '执行详情、报告查看与失败用例定位',
]
</script>
