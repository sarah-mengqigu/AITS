<template>
  <div class="test">
    <el-alert
      v-if="pageError"
      type="error"
      show-icon
      :closable="false"
      :title="pageError"
      description="测试发送相关数据加载失败，请确认后端服务已启动。"
    />

    <div class="page-card">
      <div class="card-title">
        <span>发送测试通知</span>
        <span class="text-small text-muted">POST /api/notifications/test/</span>
      </div>

      <el-form label-width="110px" class="test-form">
        <el-form-item label="发送方式">
          <el-radio-group v-model="form.mode">
            <el-radio label="receiver">使用接收人</el-radio>
            <el-radio label="channel">直接指定渠道</el-radio>
          </el-radio-group>
        </el-form-item>

        <template v-if="form.mode === 'receiver'">
          <el-form-item label="通知接收人">
            <el-select
              v-model="form.receiverId"
              class="w-full"
              filterable
              clearable
              placeholder="选择接收人（项目接收人优先）"
              :loading="receiverLoading"
            >
              <el-option
                v-for="receiver in receivers"
                :key="receiver.id"
                :label="`${receiver.name}（${receiver.channel_name || receiver.channel_code}）`"
                :value="receiver.id"
              >
                <span>{{ receiver.name }}</span>
                <span class="option-hint">{{ receiverTargetLabel(receiver) }}</span>
              </el-option>
            </el-select>
            <div class="field-hint">
              使用接收人时会沿用其渠道与目标地址，无需再填写 Webhook。
            </div>
          </el-form-item>
        </template>

        <template v-else>
          <el-form-item label="通知渠道" required>
            <el-select v-model="form.channelCode" class="w-full" placeholder="选择渠道">
              <el-option
                v-for="channel in channels"
                :key="channel.id"
                :label="`${channel.name}（${channel.channel_code}）`"
                :value="channel.channel_code"
                :disabled="!channel.is_active"
              />
            </el-select>
            <div class="field-hint">直接使用渠道发送需要管理员（staff）权限。</div>
          </el-form-item>
          <el-form-item v-if="isWebhook" label="Webhook 地址" required>
            <el-input v-model="form.webhookUrl" placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." />
          </el-form-item>
          <el-form-item v-if="isEmail" label="收件邮箱" required>
            <el-input v-model="form.targetAddress" type="textarea" :rows="2" placeholder="多个邮箱用逗号分隔" />
          </el-form-item>
        </template>

        <el-form-item label="标题">
          <el-input v-model="form.title" maxlength="255" placeholder="通知测试" />
        </el-form-item>
        <el-form-item label="内容（Markdown）">
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="6"
            placeholder="留空则发送内置测试模板"
          />
          <div class="field-hint">按纯文本提交，后端会作为 Markdown 投递到对应渠道。</div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="sending" @click="handleSend">发送测试通知</el-button>
          <el-button @click="fillTemplate">填充示例内容</el-button>
          <el-button @click="goLogs">查看发送日志</el-button>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="result"
        class="mt-8"
        :type="result.failed ? 'warning' : 'success'"
        show-icon
        :closable="false"
        :title="result.failed ? '部分或全部发送失败' : '发送成功'"
        :description="`成功 ${result.sent} 条 · 失败 ${result.failed} 条`"
      />

      <div v-if="result" class="result">
        <el-table :data="result.results || []" border size="small">
          <el-table-column prop="channel_code" label="渠道" width="140">
            <template #default="{ row }">{{ channelLabel(row.channel_code) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <StatusTag :status="row.status" :text="notificationStatusText(row.status)" />
            </template>
          </el-table-column>
          <el-table-column prop="log_id" label="日志 ID" width="120" />
          <el-table-column prop="error" label="错误" min-width="180">
            <template #default="{ row }">{{ row.error || row.error_message || '—' }}</template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import StatusTag from '@/components/StatusTag.vue'
import { useProjectStore } from '@/stores/project'
import { notificationsApi } from '@/api/notifications'

import {
  channelLabel,
  isEmailChannel,
  isWebhookChannel,
  notificationStatusText,
  receiverTargetLabel,
  buildTestPayload,
} from './utils'

const props = defineProps({
  initialChannel: { type: String, default: '' },
})

const router = useRouter()
const projectStore = useProjectStore()

const loading = ref(false)
const pageError = ref('')
const channels = ref([])
const receivers = ref([])
const receiverLoading = ref(false)
const sending = ref(false)
const result = ref(null)

const form = reactive({
  mode: 'receiver',
  receiverId: '',
  channelCode: props.initialChannel || '',
  webhookUrl: '',
  targetAddress: '',
  title: '通知测试',
  content: '',
})

const isWebhook = computed(() => Boolean(form.channelCode) && isWebhookChannel(form.channelCode))
const isEmail = computed(() => Boolean(form.channelCode) && isEmailChannel(form.channelCode))

async function loadChannels() {
  try {
    const data = await notificationsApi.listChannels({ page_size: 100, ordering: 'id' })
    channels.value = Array.isArray(data?.results) ? data.results : []
  } catch (error) {
    channels.value = []
    pageError.value = error?.message || '渠道列表加载失败'
  }
}

async function loadReceivers() {
  receiverLoading.value = true
  try {
    const params = { page_size: 100 }
    if (projectStore.currentProjectId) params.project = projectStore.currentProjectId
    const data = await notificationsApi.listReceivers(params)
    receivers.value = Array.isArray(data?.results) ? data.results : []
  } catch (error) {
    receivers.value = []
  } finally {
    receiverLoading.value = false
  }
}

function fillTemplate() {
  form.title = form.title || '通知测试'
  form.content = [
    '## AITS 通知测试',
    '',
    '- 渠道：测试发送',
    `- 项目：${projectStore.currentProjectName || '全局'}`,
    '- 状态：发送成功',
    '',
    '> 这是一条来自通知中心的测试消息。',
  ].join('\n')
}

async function handleSend() {
  const payloadForm = {
    ...form,
    receiverId: form.mode === 'receiver' ? form.receiverId : '',
    channelCode: form.mode === 'channel' ? form.channelCode : '',
  }
  const { payload, error } = buildTestPayload(payloadForm)
  if (error) {
    ElMessage.warning(error)
    return
  }
  sending.value = true
  result.value = null
  try {
    const data = await notificationsApi.test(payload)
    result.value = {
      sent: Number(data?.sent ?? 0),
      failed: Number(data?.failed ?? 0),
      results: Array.isArray(data?.results) ? data.results : [],
    }
    if (result.value.failed) {
      ElMessage.warning('通知已提交，但存在发送失败，请查看日志')
    } else {
      ElMessage.success('测试通知发送成功')
    }
  } catch (error) {
    if (error?.response?.status === 403) {
      ElMessage.error('没有权限执行该测试发送（全局渠道仅管理员可用）')
    } else {
      ElMessage.error(error?.message || '发送失败')
    }
  } finally {
    sending.value = false
  }
}

function goLogs() {
  router.push({ name: 'notifications-logs' })
}

watch(
  () => props.initialChannel,
  (channelCode) => {
    if (!channelCode) return
    form.mode = 'channel'
    form.channelCode = channelCode
  },
)

onMounted(async () => {
  if (!projectStore.loaded) {
    try {
      await projectStore.fetchProjects()
    } catch (error) {
      // 忽略：无项目时仍可测试全局渠道
    }
  }
  await Promise.all([loadChannels(), loadReceivers()])
})
</script>

<style scoped>
.test {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.test-form {
  max-width: 760px;
}

.w-full {
  width: 100%;
}

.option-hint {
  float: right;
  margin-left: 12px;
  font-size: 12px;
  color: #94a3b8;
}

.field-hint {
  width: 100%;
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: #94a3b8;
}

.result {
  margin-top: 12px;
}

.mt-8 {
  margin-top: 8px;
}
</style>
