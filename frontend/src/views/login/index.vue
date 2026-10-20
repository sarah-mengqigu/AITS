<template>
  <div class="login-page">
    <div class="login-decoration login-decoration--one" />
    <div class="login-decoration login-decoration--two" />

    <div class="login-shell">
      <section class="login-brand">
        <div class="brand-mark">A</div>
        <h1 class="brand-title">AITS 智能测试平台</h1>
        <p class="brand-slogan">
          覆盖 API / Web / App / 性能测试的一站式智能化测试平台，内置 AI 用例生成、脚本生成与质量诊断能力。
        </p>

        <ul class="brand-features">
          <li v-for="feature in features" :key="feature.title">
            <el-icon class="feature-icon"><component :is="feature.icon" /></el-icon>
            <div>
              <strong>{{ feature.title }}</strong>
              <span>{{ feature.description }}</span>
            </div>
          </li>
        </ul>

        <div class="brand-footer">AITS v2.0 · AI Testing System</div>
      </section>

      <section class="login-panel">
        <div class="login-panel__header">
          <h2>欢迎登录</h2>
          <p>请使用平台账号访问智能测试工作台</p>
        </div>

        <el-alert
          v-if="errorMessage"
          class="login-error"
          :title="errorMessage"
          type="error"
          show-icon
          :closable="false"
        />

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          size="large"
          @keyup.enter="handleSubmit"
        >
          <el-form-item label="账号" prop="username">
            <el-input
              v-model="form.username"
              placeholder="请输入用户名或邮箱"
              :prefix-icon="User"
              autocomplete="username"
              clearable
            />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              :prefix-icon="Lock"
              autocomplete="current-password"
              show-password
            />
          </el-form-item>

          <el-button
            class="login-submit"
            type="primary"
            :loading="authStore.loading"
            @click="handleSubmit"
          >
            登 录
          </el-button>
        </el-form>

        <div class="login-tips">
          <el-icon><InfoFilled /></el-icon>
          <span>
            演示环境：<code>admin / Admin@12345</code>。首次使用请在
            <code>backend/</code> 下执行
            <code>.venv/bin/python manage.py seed_demo</code> 初始化演示数据，
            或执行 <code>createsuperuser</code> 创建管理员。
          </span>
        </div>

        <div class="login-panel__footer">
          <span>© {{ year }} AITS 智能测试平台</span>
          <span>Vue 3 · Element Plus</span>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Connection,
  InfoFilled,
  Lock,
  MagicStick,
  Monitor,
  TrendCharts,
  User,
} from '@element-plus/icons-vue'

import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const formRef = ref(null)
const errorMessage = ref('')
const year = new Date().getFullYear()

const form = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入用户名或邮箱', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const features = [
  { title: '接口与 UI 自动化', description: 'OpenAPI / Postman 导入，Playwright / MidScene 执行', icon: Connection },
  { title: 'AI 测试生成', description: '用例、场景、脚本由 7 个 Agent 协同生成', icon: MagicStick },
  { title: '性能与监控', description: 'Locust 压测、指标采集与 AI 诊断', icon: TrendCharts },
  { title: '多端覆盖', description: 'API / Web / App 全链路质量看板', icon: Monitor },
]

function resolveRedirect() {
  const redirect = route.query.redirect
  if (typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('/login')) {
    return redirect
  }
  return '/dashboard'
}

async function handleSubmit() {
  if (!formRef.value || authStore.loading) return
  errorMessage.value = ''
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  try {
    await authStore.login({ username: form.username.trim(), password: form.password })
    ElMessage.success(`欢迎回来，${authStore.displayName}`)
    await router.replace(resolveRedirect())
  } catch (error) {
    errorMessage.value = error?.message || '登录失败，请检查账号密码或后端服务是否可用'
  }
}
</script>

<style scoped>
.login-page {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  min-width: 1080px;
  padding: 40px;
  overflow: hidden;
  background:
    radial-gradient(circle at 15% 10%, rgba(37, 99, 235, 0.35), transparent 42%),
    radial-gradient(circle at 85% 90%, rgba(56, 189, 248, 0.22), transparent 45%),
    linear-gradient(135deg, #0b1220 0%, #111c33 55%, #0f172a 100%);
}

.login-decoration {
  position: absolute;
  border-radius: 50%;
  filter: blur(4px);
  pointer-events: none;
}

.login-decoration--one {
  top: -140px;
  right: -100px;
  width: 420px;
  height: 420px;
  background: radial-gradient(circle, rgba(37, 99, 235, 0.28), transparent 68%);
}

.login-decoration--two {
  bottom: -180px;
  left: -120px;
  width: 520px;
  height: 520px;
  background: radial-gradient(circle, rgba(14, 165, 233, 0.18), transparent 70%);
}

.login-shell {
  position: relative;
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  width: 1000px;
  max-width: 100%;
  min-height: 560px;
  border-radius: 18px;
  overflow: hidden;
  background: #fff;
  box-shadow: 0 30px 80px rgba(2, 6, 23, 0.45);
}

.login-brand {
  display: flex;
  flex-direction: column;
  padding: 52px 44px 36px;
  color: #e2e8f0;
  background:
    radial-gradient(circle at 20% 0%, rgba(37, 99, 235, 0.55), transparent 55%),
    linear-gradient(160deg, #0f172a 0%, #1e293b 100%);
}

.brand-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 46px;
  margin-bottom: 22px;
  border-radius: 12px;
  background: linear-gradient(135deg, #2563eb, #38bdf8);
  color: #fff;
  font-size: 22px;
  font-weight: 700;
}

.brand-title {
  margin: 0;
  font-size: 26px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.brand-slogan {
  margin: 14px 0 30px;
  color: #94a3b8;
  font-size: 13.5px;
  line-height: 1.8;
}

.brand-features {
  display: flex;
  flex-direction: column;
  gap: 18px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.brand-features li {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.feature-icon {
  margin-top: 2px;
  color: #60a5fa;
  font-size: 18px;
}

.brand-features strong {
  display: block;
  margin-bottom: 3px;
  color: #f1f5f9;
  font-size: 13.5px;
  font-weight: 600;
}

.brand-features span {
  color: #94a3b8;
  font-size: 12.5px;
  line-height: 1.6;
}

.brand-footer {
  margin-top: auto;
  padding-top: 30px;
  color: #64748b;
  font-size: 11.5px;
}

.login-panel {
  display: flex;
  flex-direction: column;
  padding: 48px 46px 30px;
}

.login-panel__header h2 {
  margin: 0;
  color: #0f172a;
  font-size: 24px;
  font-weight: 600;
}

.login-panel__header p {
  margin: 8px 0 26px;
  color: var(--aits-text-secondary);
  font-size: 13px;
}

.login-error {
  margin-bottom: 16px;
}

.login-submit {
  width: 100%;
  height: 44px;
  margin-top: 6px;
  font-size: 15px;
  letter-spacing: 2px;
}

.login-tips {
  display: flex;
  gap: 8px;
  margin-top: 24px;
  padding: 12px 14px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #eff6ff;
  color: #475569;
  font-size: 12px;
  line-height: 1.7;
}

.login-tips .el-icon {
  flex-shrink: 0;
  margin-top: 3px;
  color: #2563eb;
}

.login-tips code {
  padding: 1px 5px;
  border-radius: 4px;
  background: #dbeafe;
  color: #1d4ed8;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 11.5px;
}

.login-panel__footer {
  display: flex;
  justify-content: space-between;
  margin-top: auto;
  padding-top: 24px;
  border-top: 1px solid #f1f5f9;
  color: #94a3b8;
  font-size: 11.5px;
}

@media (max-width: 1100px) {
  .login-shell {
    grid-template-columns: 1fr;
    width: 520px;
  }

  .login-brand {
    display: none;
  }
}
</style>
