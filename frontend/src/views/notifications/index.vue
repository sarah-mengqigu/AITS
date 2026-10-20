<template>
  <ModulePlaceholder
    module-name="通知中心"
    description="通知渠道、接收人、SMTP 邮件配置与发送日志"
    :features="features"
    api-module="src/api/notifications.js"
  />
</template>

<script setup>
import ModulePlaceholder from '@/components/ModulePlaceholder.vue'

const features = [
  '钉钉 / 企业微信 / 飞书 / 邮件 / 通用 Webhook 渠道',
  '项目级通知接收人与目标地址维护',
  'SMTP 邮件配置单例管理',
  '单渠道测试发送',
  '通知发送日志与失败原因排查',
  '定时任务与性能诊断结果联动推送',
]
</script>
