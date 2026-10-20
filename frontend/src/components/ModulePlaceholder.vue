<template>
  <div class="page-container">
    <PageHeader :title="pageTitle" :description="description">
      <template #actions>
        <el-button @click="router.push('/dashboard')">返回仪表盘</el-button>
      </template>
    </PageHeader>

    <div class="page-card">
      <EmptyState
        :title="`${pageTitle} 将在下一轮交付`"
        description="本轮已完成工程脚手架、路由、布局、鉴权与通用组件，业务页面按里程碑 M2 并行补齐。"
      >
        <el-button type="primary" @click="router.push('/dashboard')">返回仪表盘</el-button>
      </EmptyState>

      <div class="planned">
        <h3 class="planned__title">计划中的能力</h3>
        <ul class="planned__list">
          <li v-for="feature in features" :key="feature">
            <el-icon><CircleCheck /></el-icon>
            <span>{{ feature }}</span>
          </li>
        </ul>
      </div>

      <el-alert
        class="planned__api"
        type="info"
        :closable="false"
        show-icon
        :title="`接口层已就绪：${apiModule}`"
        description="方法已按 docs/ARCHITECTURE.md §2 契约实现，业务页面可直接调用；后端未启动时请求会给出可读错误，不会白屏。"
      />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CircleCheck } from '@element-plus/icons-vue'

import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'

const props = defineProps({
  moduleName: { type: String, required: true },
  description: { type: String, default: '' },
  features: { type: Array, default: () => [] },
  apiModule: { type: String, default: 'src/api/client.js' },
})

const route = useRoute()
const router = useRouter()

const pageTitle = computed(() => route.meta?.title || props.moduleName)
</script>

<style scoped>
.planned {
  margin-top: 4px;
  padding: 18px 22px;
  border-top: 1px dashed var(--aits-border);
}

.planned__title {
  margin: 0 0 12px;
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
}

.planned__list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 24px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.planned__list li {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #475569;
  font-size: 13px;
}

.planned__list .el-icon {
  color: #16a34a;
}

.planned__api {
  margin-top: 18px;
}
</style>
