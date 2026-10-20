<template>
  <ModulePlaceholder
    module-name="性能测试"
    description="负载配置、压测场景、执行报告与 AI 性能诊断"
    :features="features"
    api-module="src/api/performance.js"
  />
</template>

<script setup>
import ModulePlaceholder from '@/components/ModulePlaceholder.vue'

const features = [
  '负载配置（并发用户 / 加压速率 / 持续时间）',
  '基于 API 套件或自定义脚本的性能场景',
  'Locustfile 脚本生成与压测执行',
  'TPS、P50 / P95 / P99、错误率与状态码分布',
  'Grafana 告警 Webhook 与 AI 诊断记录',
  'Prometheus / Grafana 监控大盘',
]
</script>
