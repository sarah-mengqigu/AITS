<template>
  <ModulePlaceholder
    module-name="个人中心"
    description="个人资料、密码修改与账号信息"
    :features="features"
    api-module="src/api/auth.js"
  />
</template>

<script setup>
import ModulePlaceholder from '@/components/ModulePlaceholder.vue'

const features = [
  '查看与修改昵称 / 邮箱 / 手机 / 部门',
  '修改登录密码',
  '头像展示',
  '查看所属项目与角色',
  '退出登录',
]
</script>
