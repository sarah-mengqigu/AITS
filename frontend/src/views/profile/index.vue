<template>
  <div class="profile-page">
    <PageHeader title="个人中心" description="维护个人资料与账号安全">
      <template #actions>
        <el-button :loading="loading" @click="loadProfile">刷新</el-button>
      </template>
    </PageHeader>

    <el-row :gutter="16">
      <el-col :xs="24" :lg="9">
        <el-card shadow="never" class="profile-card">
          <div class="profile-avatar">
            <el-avatar :size="72" :src="user?.avatar || ''">
              {{ (user?.display_name || user?.username || '?').slice(0, 1) }}
            </el-avatar>
            <div class="profile-avatar__meta">
              <div class="profile-avatar__name">{{ user?.display_name || user?.username }}</div>
              <div class="profile-avatar__sub">{{ user?.email }}</div>
              <div class="profile-avatar__tags">
                <el-tag v-if="user?.is_superuser" type="danger" size="small" effect="plain">
                  超级管理员
                </el-tag>
                <el-tag v-else-if="user?.is_staff" type="warning" size="small" effect="plain">
                  管理员
                </el-tag>
                <el-tag v-for="role in user?.roles || []" :key="role" size="small" effect="plain">
                  {{ roleLabel(role) }}
                </el-tag>
              </div>
            </div>
          </div>

          <el-descriptions :column="1" border class="profile-desc">
            <el-descriptions-item label="用户名">{{ user?.username || '—' }}</el-descriptions-item>
            <el-descriptions-item label="部门">{{ user?.department || '—' }}</el-descriptions-item>
            <el-descriptions-item label="手机号">{{ user?.phone || '—' }}</el-descriptions-item>
            <el-descriptions-item label="最后登录">
              {{ user?.last_login ? formatDateTime(user.last_login) : '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="注册时间">
              {{ user?.date_joined ? formatDateTime(user.date_joined) : '—' }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="15">
        <el-card shadow="never" class="profile-card">
          <template #header>
            <div class="card-title">基本资料</div>
          </template>
          <el-form ref="profileFormRef" :model="profileForm" :rules="profileRules" label-width="90px">
            <el-form-item label="昵称" prop="nickname">
              <el-input v-model="profileForm.nickname" maxlength="64" placeholder="用于界面展示" />
            </el-form-item>
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="profileForm.email" placeholder="登录与通知邮箱" />
            </el-form-item>
            <el-form-item label="手机号" prop="phone">
              <el-input v-model="profileForm.phone" maxlength="32" placeholder="选填" />
            </el-form-item>
            <el-form-item label="部门" prop="department">
              <el-input v-model="profileForm.department" maxlength="128" placeholder="选填" />
            </el-form-item>
            <el-form-item label="头像地址" prop="avatar">
              <el-input v-model="profileForm.avatar" placeholder="https://...（选填）" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="submitProfile">保存资料</el-button>
              <el-button @click="resetProfile">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="never" class="profile-card mt-16">
          <template #header>
            <div class="card-title">修改密码</div>
          </template>
          <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-width="90px">
            <el-form-item label="原密码" prop="old_password">
              <el-input
                v-model="passwordForm.old_password"
                type="password"
                show-password
                autocomplete="current-password"
              />
            </el-form-item>
            <el-form-item label="新密码" prop="new_password">
              <el-input
                v-model="passwordForm.new_password"
                type="password"
                show-password
                autocomplete="new-password"
              />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirm_password">
              <el-input
                v-model="passwordForm.confirm_password"
                type="password"
                show-password
                autocomplete="new-password"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="changing" @click="submitPassword">更新密码</el-button>
              <span class="form-hint">修改后当前会话保持有效，下次登录使用新密码。</span>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import PageHeader from '@/components/PageHeader.vue'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'

const auth = useAuthStore()

const loading = ref(false)
const saving = ref(false)
const changing = ref(false)
const user = ref(null)

const profileFormRef = ref(null)
const passwordFormRef = ref(null)

const profileForm = reactive({ nickname: '', email: '', phone: '', department: '', avatar: '' })
const passwordForm = reactive({ old_password: '', new_password: '', confirm_password: '' })

const ROLE_LABELS = { owner: '拥有者', admin: '管理员', editor: '编辑', viewer: '查看者' }
const roleLabel = (role) => ROLE_LABELS[role] || role

const profileRules = {
  nickname: [{ max: 64, message: '昵称不超过 64 个字符', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  phone: [{ pattern: /^[0-9+\-\s()]{0,32}$/, message: '手机号格式不正确', trigger: 'blur' }],
  avatar: [{ type: 'url', message: '头像需为合法 URL', trigger: 'blur' }],
}

const passwordRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== passwordForm.new_password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

function applyUser(data) {
  user.value = data
  Object.assign(profileForm, {
    nickname: data.nickname || '',
    email: data.email || '',
    phone: data.phone || '',
    department: data.department || '',
    avatar: data.avatar || '',
  })
}

async function loadProfile() {
  loading.value = true
  try {
    const data = await auth.fetchMe()
    applyUser(data)
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || error?.message || '加载个人资料失败')
  } finally {
    loading.value = false
  }
}

function resetProfile() {
  if (user.value) applyUser(user.value)
}

async function submitProfile() {
  const form = profileFormRef.value
  if (!form) return
  try {
    await form.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const payload = {
      nickname: profileForm.nickname,
      email: profileForm.email,
      phone: profileForm.phone,
      department: profileForm.department,
      avatar: profileForm.avatar,
    }
    const data = await auth.updateMe(payload)
    applyUser(data || { ...(user.value || {}), ...payload })
    ElMessage.success('资料已保存')
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || error?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function submitPassword() {
  const form = passwordFormRef.value
  if (!form) return
  try {
    await form.validate()
  } catch {
    return
  }
  changing.value = true
  try {
    await auth.changePassword({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password,
    })
    ElMessage.success('密码已更新')
    passwordForm.old_password = ''
    passwordForm.new_password = ''
    passwordForm.confirm_password = ''
    form.clearValidate()
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || error?.message || '密码修改失败')
  } finally {
    changing.value = false
  }
}

onMounted(loadProfile)
</script>

<style scoped>
.profile-card {
  border-radius: 8px;
}

.profile-avatar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-bottom: 16px;
}

.profile-avatar__name {
  font-size: 18px;
  font-weight: 600;
}

.profile-avatar__sub {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin: 4px 0 8px;
}

.profile-avatar__tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.profile-desc :deep(.el-descriptions__label) {
  width: 96px;
}

.card-title {
  font-weight: 600;
}

.form-hint {
  margin-left: 12px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.mt-16 {
  margin-top: 16px;
}
</style>
