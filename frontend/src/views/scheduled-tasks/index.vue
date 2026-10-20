<template>
  <ModulePlaceholder
    module-name="定时任务"
    description="Cron 定时调度、套件批量执行与执行日志"
    :features="features"
    api-module="src/api/scheduledTasks.js"
  />
</template>

<script setup>
import ModulePlaceholder from '@/components/ModulePlaceholder.vue'

const features = [
  '定时任务 CRUD 与 Cron 表达式预览',
  '按 suite_type 选择 API / Web / App 套件',
  '启用 / 禁用与立即执行',
  'Celery Beat 周期任务自动同步',
  '执行日志、通过率与报告链接',
  '执行结果联动通知渠道',
]
</script>
