<template>
  <ModulePlaceholder
    module-name="监控大盘"
    description="Prometheus 指标与 Grafana 面板、性能趋势与告警联动"
    :features="features"
    api-module="src/api/performance.js（/api/performance/dashboard/）"
  />
</template>

<script setup>
import ModulePlaceholder from '@/components/ModulePlaceholder.vue'

const features = [
  '性能执行指标总览（TPS / P95 / 错误率）',
  'Prometheus targets（Windows Exporter 自动注册）',
  'Grafana 面板嵌入与告警链接',
  'AI 诊断记录与处理状态',
  '按项目 / 时间范围筛选',
  '无监控栈时的空态与配置指引',
]
</script>
