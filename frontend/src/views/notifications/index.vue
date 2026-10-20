<template>
  <div class="page-container">
    <PageHeader
      title="通知中心"
      :subtitle="projectLabel"
      description="通知渠道、项目接收人、SMTP 邮件配置、测试发送与发送日志"
    >
      <template #actions>
        <el-tag v-if="!projectStore.currentProjectId" type="warning" effect="plain">
          未选择项目 · 可管理全局渠道与邮件
        </el-tag>
        <el-tag v-else type="info" effect="plain">当前项目：{{ projectStore.currentProjectName }}</el-tag>
      </template>
    </PageHeader>

    <div class="module-tabs" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        role="tab"
        class="module-tab"
        :class="{ 'is-active': tab.key === activeKey }"
        :aria-selected="tab.key === activeKey"
        @click="selectTab(tab)"
      >
        {{ tab.label }}
      </button>
    </div>

    <component
      :is="activeTab.component"
      :key="activeKey"
      v-bind="activeKey === 'test' ? { initialChannel: testChannel } : {}"
      @test="handleTestRequest"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PageHeader from '@/components/PageHeader.vue'
import { useProjectStore } from '@/stores/project'

import Channels from './Channels.vue'
import Receivers from './Receivers.vue'
import Email from './Email.vue'
import Logs from './Logs.vue'
import Test from './Test.vue'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

const tabs = [
  { key: 'channels', label: '渠道配置', routeName: 'notifications', component: Channels },
  { key: 'receivers', label: '接收人', routeName: 'notifications-receivers', component: Receivers },
  { key: 'email', label: '邮件配置', routeName: 'notifications-email', component: Email },
  { key: 'logs', label: '发送日志', routeName: 'notifications-logs', component: Logs },
  { key: 'test', label: '测试发送', routeName: '', component: Test },
]

const ROUTE_NAME_TO_TAB = {
  notifications: 'channels',
  'notifications-channels': 'channels',
  'notifications-receivers': 'receivers',
  'notifications-email': 'email',
  'notifications-logs': 'logs',
}

/** 「测试发送」没有独立路由，用本地状态承载。 */
const localTab = ref('')
const testChannel = ref('')

const activeKey = computed(() => localTab.value || ROUTE_NAME_TO_TAB[route.name] || 'channels')
const activeTab = computed(() => tabs.find((tab) => tab.key === activeKey.value) || tabs[0])
const projectLabel = computed(() =>
  projectStore.currentProjectName ? `项目：${projectStore.currentProjectName}` : '全局视图',
)

function selectTab(tab) {
  if (tab.key === activeKey.value) return
  if (tab.routeName) {
    localTab.value = ''
    router.push({ name: tab.routeName })
    return
  }
  localTab.value = tab.key
}

function handleTestRequest(channelCode) {
  testChannel.value = channelCode || ''
  localTab.value = 'test'
}

watch(
  () => route.name,
  () => {
    localTab.value = ''
  },
)
</script>

<style scoped>
.module-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  overflow-x: auto;
  background: #fff;
  border: 1px solid var(--aits-border);
  border-radius: var(--aits-radius);
  box-shadow: var(--aits-shadow);
}

.module-tab {
  flex-shrink: 0;
  padding: 9px 16px;
  font-size: 13.5px;
  color: var(--aits-text-secondary);
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: 8px;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.module-tab:hover {
  color: #2563eb;
  background: #f1f5f9;
}

.module-tab.is-active {
  color: #fff;
  font-weight: 600;
  background: #2563eb;
}
</style>
