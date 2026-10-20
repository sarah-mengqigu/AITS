<template>
  <div class="email">
    <el-alert
      v-if="pageError"
      type="error"
      show-icon
      :closable="false"
      :title="pageError"
      description="邮件配置加载失败，请确认后端服务已启动。"
    />

    <el-alert
      v-if="!isStaff"
      type="info"
      show-icon
      :closable="false"
      title="SMTP 邮件配置仅管理员（staff）可修改"
      description="当前账号可以查看配置状态，保存操作会返回 403。"
    />

    <div class="email__grid">
      <div class="page-card">
        <div class="card-title">
          <span>SMTP 配置</span>
          <el-tag v-if="loaded" size="small" :type="form.is_active ? 'success' : 'info'" effect="plain">
            {{ form.is_active ? '已启用' : '已停用' }}
          </el-tag>
        </div>

        <el-form v-loading="loading" label-width="110px">
          <el-form-item label="SMTP 主机" required>
            <el-input v-model="form.host" placeholder="smtp.example.com" />
          </el-form-item>
          <el-form-item label="端口">
            <el-input-number v-model="form.port" :min="1" :max="65535" :step="1" />
            <span class="field-hint inline">SSL 常用 465，STARTTLS 常用 587</span>
          </el-form-item>
          <el-form-item label="用户名">
            <el-input v-model="form.username" placeholder="登录 SMTP 的用户名 / 授权码账号" />
          </el-form-item>
          <el-form-item label="密码 / 授权码">
            <el-input
              v-model="form.password"
              type="password"
              show-password
              autocomplete="new-password"
              :placeholder="passwordPlaceholder"
            />
            <div class="field-hint">
              已保存的密码仅以掩码回显，留空保存不会修改原密码。
            </div>
          </el-form-item>
          <el-form-item label="发件人">
            <el-input v-model="form.from_email" placeholder="noreply@example.com" />
          </el-form-item>
          <el-form-item label="加密方式">
            <el-checkbox v-model="form.use_ssl">使用 SSL</el-checkbox>
            <el-checkbox v-model="form.use_tls">使用 TLS</el-checkbox>
          </el-form-item>
          <el-form-item label="启用">
            <el-switch v-model="form.is_active" />
            <span class="field-hint inline">启用后新配置将替换旧配置（单例语义）</span>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="saving" :disabled="!isStaff" @click="handleSave">
              保存配置
            </el-button>
            <el-button :disabled="!loaded" @click="load">重置</el-button>
            <el-button type="success" plain @click="$emit('test')">去测试发送</el-button>
          </el-form-item>
        </el-form>
      </div>

      <div class="page-card">
        <div class="card-title">
          <span>配置说明</span>
        </div>
        <div class="tips">
          <p><strong>单例配置：</strong>后端 `EmailConfig` 为单例语义，GET/PUT/PATCH `/api/notifications/email-config/`。</p>
          <p><strong>密码掩码：</strong>读取时 `password` 恒为 `******`，前端留空或不改动该字段时不会覆盖真实密码。</p>
          <p><strong>SSL / TLS：</strong>465 端口通常使用 SSL；587 端口通常使用 STARTTLS，请勿同时勾选。</p>
          <p><strong>邮件接收人：</strong>在「接收人」中选择「邮件」渠道并填写收件邮箱，定时任务即可勾选该接收人。</p>
        </div>

        <div v-if="loaded" class="summary">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="当前主机">
              {{ form.host || '未配置' }}:{{ form.port }}
            </el-descriptions-item>
            <el-descriptions-item label="发件人">{{ form.from_email || '未配置' }}</el-descriptions-item>
            <el-descriptions-item label="密码状态">
              {{ form.passwordMasked ? `已配置（${form.passwordMasked}）` : '未配置' }}
            </el-descriptions-item>
            <el-descriptions-item label="更新时间">{{ formatDateTime(updatedAt) }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { useAuthStore } from '@/stores/auth'
import { notificationsApi } from '@/api/notifications'
import { formatDateTime } from '@/utils/format'

import { buildEmailConfigPayload, emailRecordToForm, emptyEmailForm } from './utils'

defineEmits(['test'])

const authStore = useAuthStore()
const isStaff = computed(() => Boolean(authStore.user?.is_staff || authStore.user?.is_superuser))

const loading = ref(false)
const loaded = ref(false)
const saving = ref(false)
const pageError = ref('')
const updatedAt = ref('')
const form = reactive(emptyEmailForm())

const passwordPlaceholder = computed(() =>
  form.passwordMasked ? `已配置 ${form.passwordMasked}，留空表示不修改` : '填写 SMTP 密码或授权码',
)

async function load() {
  loading.value = true
  pageError.value = ''
  try {
    const data = await notificationsApi.emailConfig()
    Object.assign(form, emailRecordToForm(data))
    updatedAt.value = data?.updated_at || ''
    loaded.value = true
  } catch (error) {
    pageError.value = error?.message || '邮件配置加载失败'
    loaded.value = false
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  const { payload, error } = buildEmailConfigPayload(form)
  if (error) {
    ElMessage.warning(error)
    return
  }
  saving.value = true
  try {
    const data = await notificationsApi.saveEmailConfig(payload, { partial: false })
    Object.assign(form, emailRecordToForm(data))
    updatedAt.value = data?.updated_at || ''
    ElMessage.success('邮件配置已保存')
  } catch (error) {
    if (error?.response?.status === 403) {
      ElMessage.error('没有权限修改邮件配置（仅管理员可操作）')
    } else {
      ElMessage.error(error?.message || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.email {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.email__grid {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 16px;
}

.field-hint {
  width: 100%;
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: #94a3b8;
}

.field-hint.inline {
  width: auto;
  margin: 0 0 0 10px;
}

.tips {
  font-size: 12.5px;
  line-height: 1.8;
  color: var(--aits-text-secondary);
}

.tips p {
  margin: 0 0 10px;
}

.summary {
  margin-top: 12px;
}

@media (max-width: 1200px) {
  .email__grid {
    grid-template-columns: 1fr;
  }
}
</style>
