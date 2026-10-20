<template>
  <div class="not-found">
    <el-result icon="warning" title="404" sub-title="抱歉，你访问的页面不存在或已被移除">
      <template #extra>
        <el-button @click="router.back()">返回上一页</el-button>
        <el-button type="primary" @click="router.push('/dashboard')">回到仪表盘</el-button>
      </template>
    </el-result>
    <p class="not-found__path">
      请求路径：<code>{{ route.fullPath }}</code>
    </p>
  </div>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
</script>

<style scoped>
.not-found {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: 40px 20px;
  background: #fff;
  border: 1px solid var(--aits-border);
  border-radius: var(--aits-radius);
}

.not-found__path {
  margin: 0;
  color: #94a3b8;
  font-size: 12.5px;
}

.not-found__path code {
  padding: 2px 6px;
  border-radius: 4px;
  background: #f1f5f9;
  color: #475569;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
}
</style>
