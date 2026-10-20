<template>
  <div v-loading="projectLoading" class="page-container">
    <PageHeader
      :title="project?.name || '项目详情'"
      :subtitle="project ? getProjectTypeText(project.project_type) : ''"
      :description="project?.description || '项目成员、环境、知识库与第三方集成配置'"
    >
      <template #actions>
        <el-button :icon="ArrowLeft" @click="router.push('/projects')">返回列表</el-button>
        <el-button :icon="Refresh" :loading="projectLoading" @click="loadProject">刷新</el-button>
      </template>
    </PageHeader>

    <el-result
      v-if="projectError && !project"
      icon="warning"
      title="项目加载失败"
      :sub-title="projectError"
    >
      <template #extra>
        <el-button @click="router.push('/projects')">返回项目列表</el-button>
        <el-button type="primary" @click="loadProject">重试</el-button>
      </template>
    </el-result>

    <template v-else>
      <div class="page-card is-flush project-tabs-card">
        <el-tabs v-model="activeTab" class="project-tabs" @tab-change="handleTabChange">
          <!-- 概览 -->
          <el-tab-pane label="概览" name="overview">
            <div class="tab-body">
              <el-alert
                v-if="tabErrors.overview"
                :title="tabErrors.overview"
                type="warning"
                show-icon
                :closable="false"
              />
              <div class="stat-grid overview-stats">
                <StatCard label="项目成员" :value="stats?.member_count ?? '—'" :icon="UserFilled" />
                <StatCard label="环境配置" :value="stats?.environment_count ?? '—'" :icon="SetUp" />
                <StatCard label="知识库文档" :value="stats?.knowledge_count ?? '—'" :icon="Document" />
                <StatCard label="上传文件" :value="stats?.file_count ?? '—'" :icon="FolderOpened" />
              </div>

              <el-descriptions :column="2" border class="overview-descriptions">
                <el-descriptions-item label="项目名称">{{ project?.name || '—' }}</el-descriptions-item>
                <el-descriptions-item label="项目类型">
                  <el-tag
                    v-if="project"
                    :type="PROJECT_TYPE_TAG_TYPE[project.project_type] || 'info'"
                    size="small"
                  >
                    {{ getProjectTypeText(project.project_type) }}
                  </el-tag>
                  <span v-else>—</span>
                </el-descriptions-item>
                <el-descriptions-item label="拥有者">{{ project?.owner_name || '—' }}</el-descriptions-item>
                <el-descriptions-item label="我的角色">
                  {{ project?.role ? getRoleText(project.role) : '—' }}
                </el-descriptions-item>
                <el-descriptions-item label="创建时间">
                  {{ formatDateTime(project?.created_at) }}
                </el-descriptions-item>
                <el-descriptions-item label="更新时间">
                  {{ formatDateTime(project?.updated_at) }}
                </el-descriptions-item>
                <el-descriptions-item label="模块统计" :span="2">
                  <div class="module-stats">
                    <span>API 规范：{{ stats?.modules?.api ?? 0 }}</span>
                    <span>Web 模块：{{ stats?.modules?.web ?? 0 }}</span>
                    <span>App 模块：{{ stats?.modules?.app ?? 0 }}</span>
                    <span>性能场景：{{ stats?.modules?.perf ?? 0 }}</span>
                  </div>
                </el-descriptions-item>
                <el-descriptions-item label="项目描述" :span="2">
                  {{ project?.description || '暂无描述' }}
                </el-descriptions-item>
              </el-descriptions>
            </div>
          </el-tab-pane>

          <!-- 成员 -->
          <el-tab-pane label="成员" name="members">
            <div class="tab-body">
              <el-alert
                v-if="tabErrors.members"
                :title="tabErrors.members"
                type="warning"
                show-icon
                :closable="false"
              />
              <div class="toolbar">
                <div class="toolbar__left">
                  <span class="text-small text-muted">共 {{ members.length }} 位成员</span>
                </div>
                <div class="toolbar__right">
                  <el-button type="primary" :icon="Plus" @click="openMemberDialog">添加成员</el-button>
                </div>
              </div>
              <el-table v-loading="membersLoading" :data="members" border stripe>
                <el-table-column prop="username" label="用户名" min-width="140" />
                <el-table-column prop="email" label="邮箱" min-width="200" show-overflow-tooltip />
                <el-table-column label="角色" width="160">
                  <template #default="{ row }">
                    <el-tag v-if="row.role === 'owner'" type="warning" size="small">
                      {{ getRoleText('owner') }}
                    </el-tag>
                    <el-select
                      v-else
                      :model-value="row.role"
                      size="small"
                      @change="(role) => handleRoleChange(row, role)"
                    >
                      <el-option
                        v-for="role in assignableRoles"
                        :key="role"
                        :label="getRoleText(role)"
                        :value="role"
                      />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="加入时间" width="170">
                  <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
                </el-table-column>
                <el-table-column label="操作" width="100" fixed="right">
                  <template #default="{ row }">
                    <ConfirmButton
                      link
                      type="danger"
                      text="移除"
                      :disabled="row.user === project?.owner"
                      :content="`确定将成员「${row.username}」移出项目吗？`"
                      @confirm="handleRemoveMember(row)"
                    />
                  </template>
                </el-table-column>
                <template #empty>
                  <EmptyState title="暂无成员" description="点击「添加成员」邀请协作者加入项目" />
                </template>
              </el-table>
            </div>
          </el-tab-pane>

          <!-- 环境 -->
          <el-tab-pane label="环境" name="environments">
            <div class="tab-body">
              <el-alert
                v-if="tabErrors.environments"
                :title="tabErrors.environments"
                type="warning"
                show-icon
                :closable="false"
              />
              <div class="toolbar">
                <div class="toolbar__left">
                  <span class="text-small text-muted">环境变量与公共请求头会注入测试执行</span>
                </div>
                <div class="toolbar__right">
                  <el-button type="primary" :icon="Plus" @click="openEnvDialog()">新建环境</el-button>
                </div>
              </div>
              <el-table v-loading="environmentsLoading" :data="environments" border stripe>
                <el-table-column prop="name" label="环境名称" min-width="140" />
                <el-table-column label="类型" width="120">
                  <template #default="{ row }">{{ getEnvironmentTypeText(row.env_type) }}</template>
                </el-table-column>
                <el-table-column prop="base_url" label="Base URL" min-width="220" show-overflow-tooltip />
                <el-table-column label="默认" width="90">
                  <template #default="{ row }">
                    <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
                    <span v-else class="text-muted">—</span>
                  </template>
                </el-table-column>
                <el-table-column prop="description" label="说明" min-width="150" show-overflow-tooltip />
                <el-table-column label="操作" width="210" fixed="right">
                  <template #default="{ row }">
                    <el-button
                      link
                      type="primary"
                      :disabled="row.is_default"
                      @click="handleSetDefaultEnv(row)"
                    >
                      设为默认
                    </el-button>
                    <el-button link type="primary" @click="openEnvDialog(row)">编辑</el-button>
                    <ConfirmButton
                      link
                      type="danger"
                      text="删除"
                      :content="`确定删除环境「${row.name}」吗？`"
                      @confirm="handleDeleteEnv(row)"
                    />
                  </template>
                </el-table-column>
                <template #empty>
                  <EmptyState title="暂无环境" description="创建环境后可在用例与套件执行时选择" />
                </template>
              </el-table>
            </div>
          </el-tab-pane>

          <!-- 知识库 -->
          <el-tab-pane label="知识库" name="knowledge">
            <div class="tab-body">
              <el-alert
                v-if="tabErrors.knowledge"
                :title="tabErrors.knowledge"
                type="warning"
                show-icon
                :closable="false"
              />
              <div class="toolbar">
                <div class="toolbar__left">
                  <span class="text-small text-muted">
                    知识库文档会进入 RAG 检索，供 AI Agent 生成用例与脚本时引用
                  </span>
                </div>
                <div class="toolbar__right">
                  <el-button type="primary" :icon="Plus" @click="openKnowledgeDialog">
                    上传文本
                  </el-button>
                </div>
              </div>
              <el-table v-loading="knowledgeLoading" :data="knowledge" border stripe>
                <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
                <el-table-column label="状态" width="100">
                  <template #default="{ row }">
                    <StatusTag :status="row.status" />
                  </template>
                </el-table-column>
                <el-table-column label="分块数" width="90" align="center">
                  <template #default="{ row }">{{ row.chunk_count ?? 0 }}</template>
                </el-table-column>
                <el-table-column prop="source_file_name" label="来源文件" min-width="150">
                  <template #default="{ row }">{{ row.source_file_name || '手动录入' }}</template>
                </el-table-column>
                <el-table-column label="更新时间" width="170">
                  <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
                </el-table-column>
                <el-table-column label="操作" width="190" fixed="right">
                  <template #default="{ row }">
                    <el-button
                      link
                      type="primary"
                      :loading="reindexingId === row.id"
                      @click="handleReindex(row)"
                    >
                      重新索引
                    </el-button>
                    <ConfirmButton
                      link
                      type="danger"
                      text="删除"
                      :content="`确定删除知识文档「${row.title}」吗？`"
                      @confirm="handleDeleteKnowledge(row)"
                    />
                  </template>
                </el-table-column>
                <template #empty>
                  <EmptyState title="暂无知识文档" description="上传项目说明、接口文档等文本，提升 AI 生成质量" />
                </template>
              </el-table>
            </div>
          </el-tab-pane>

          <!-- 第三方配置 -->
          <el-tab-pane label="第三方配置" name="settings">
            <div v-loading="thirdPartyLoading" class="tab-body third-party">
              <el-alert
                v-if="tabErrors.settings"
                :title="tabErrors.settings"
                type="warning"
                show-icon
                :closable="false"
              />
              <el-form :model="thirdParty" label-width="120px" class="third-party-form">
                <el-form-item label="钉钉 Webhook">
                  <el-input v-model="thirdParty.dingtalk_webhook" placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." />
                </el-form-item>
                <el-form-item label="企业微信 Webhook">
                  <el-input v-model="thirdParty.wecom_webhook" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." />
                </el-form-item>
                <el-form-item label="飞书 Webhook">
                  <el-input v-model="thirdParty.feishu_webhook" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." />
                </el-form-item>
                <el-form-item label="GitLab 地址">
                  <el-input v-model="thirdParty.gitlab_url" placeholder="https://gitlab.example.com" />
                </el-form-item>
                <el-form-item label="GitLab Token">
                  <el-input
                    v-model="thirdParty.gitlab_token"
                    type="password"
                    show-password
                    placeholder="用于关联提交 / 缺陷（可选）"
                  />
                </el-form-item>
                <el-form-item label="扩展配置">
                  <el-input
                    v-model="thirdParty.extraText"
                    type="textarea"
                    :rows="6"
                    placeholder='JSON 对象，例如 {"env": "staging"}'
                  />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" :loading="thirdPartySaving" @click="handleSaveThirdParty">
                    保存配置
                  </el-button>
                  <el-button @click="loadThirdParty">重置</el-button>
                </el-form-item>
              </el-form>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </template>

    <!-- 成员弹窗 -->
    <el-dialog v-model="memberDialogVisible" title="添加成员" width="460px" :close-on-click-modal="false">
      <el-form ref="memberFormRef" :model="memberForm" :rules="memberRules" label-width="80px">
        <el-form-item label="用户" prop="user">
          <el-select
            v-model="memberForm.user"
            filterable
            remote
            reserve-keyword
            placeholder="搜索用户名 / 邮箱"
            :remote-method="searchUsers"
            :loading="userSearchLoading"
            style="width: 100%"
          >
            <el-option
              v-for="user in userOptions"
              :key="user.id"
              :label="`${user.display_name || user.username}（${user.email || user.username}）`"
              :value="user.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="memberForm.role" style="width: 100%">
            <el-option
              v-for="role in assignableRoles"
              :key="role"
              :label="getRoleText(role)"
              :value="role"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="memberDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="memberSubmitting" @click="handleAddMember">添加</el-button>
      </template>
    </el-dialog>

    <!-- 环境弹窗 -->
    <el-dialog
      v-model="envDialogVisible"
      :title="envEditingId ? '编辑环境' : '新建环境'"
      width="620px"
      :close-on-click-modal="false"
    >
      <el-form ref="envFormRef" :model="envForm" :rules="envRules" label-width="100px">
        <el-form-item label="环境名称" prop="name">
          <el-input v-model="envForm.name" placeholder="例如：测试环境" maxlength="64" />
        </el-form-item>
        <el-form-item label="环境类型" prop="env_type">
          <el-select v-model="envForm.env_type" style="width: 100%">
            <el-option
              v-for="(label, value) in ENVIRONMENT_TYPE_TEXT"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL" prop="base_url">
          <el-input v-model="envForm.base_url" placeholder="https://api.example.com" />
        </el-form-item>
        <el-form-item label="环境变量">
          <el-input
            v-model="envForm.variablesText"
            type="textarea"
            :rows="4"
            placeholder='JSON 对象，例如 {"token": "abc"}'
          />
        </el-form-item>
        <el-form-item label="公共请求头">
          <el-input
            v-model="envForm.headersText"
            type="textarea"
            :rows="3"
            placeholder='JSON 对象，例如 {"X-Env": "test"}'
          />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="envForm.description" maxlength="255" placeholder="环境用途说明（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="envDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="envSubmitting" @click="handleSaveEnv">保存</el-button>
      </template>
    </el-dialog>

    <!-- 知识库上传 -->
    <el-dialog
      v-model="knowledgeDialogVisible"
      title="上传知识文本"
      width="620px"
      :close-on-click-modal="false"
    >
      <el-form ref="knowledgeFormRef" :model="knowledgeForm" :rules="knowledgeRules" label-width="80px">
        <el-form-item label="标题" prop="title">
          <el-input v-model="knowledgeForm.title" maxlength="255" placeholder="例如：订单服务接口说明" />
        </el-form-item>
        <el-form-item label="正文" prop="content">
          <el-input
            v-model="knowledgeForm.content"
            type="textarea"
            :rows="10"
            placeholder="粘贴接口文档、业务规则、测试说明等文本内容"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="knowledgeDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="knowledgeSubmitting" @click="handleCreateKnowledge">
          保存并索引
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  Document,
  FolderOpened,
  Plus,
  Refresh,
  SetUp,
  UserFilled,
} from '@element-plus/icons-vue'

import PageHeader from '@/components/PageHeader.vue'
import StatCard from '@/components/StatCard.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmButton from '@/components/ConfirmButton.vue'

import { projectsApi } from '@/api/projects'
import { usersApi } from '@/api/users'
import { useProjectStore } from '@/stores/project'
import {
  ENVIRONMENT_TYPE_TEXT,
  PROJECT_TYPE_TAG_TYPE,
  formatDateTime,
  getEnvironmentTypeText,
  getProjectTypeText,
  getRoleText,
} from '@/utils/format'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

const projectId = computed(() => route.params.id)
const assignableRoles = ['admin', 'editor', 'viewer']

const project = ref(null)
const stats = ref(null)
const projectLoading = ref(true)
const projectError = ref('')

const tabErrors = reactive({})
const activeTab = ref(typeof route.query.tab === 'string' ? route.query.tab : 'overview')

const members = ref([])
const membersLoading = ref(false)
const memberDialogVisible = ref(false)
const memberSubmitting = ref(false)
const userOptions = ref([])
const userSearchLoading = ref(false)
const memberFormRef = ref(null)
const memberForm = reactive({ user: null, role: 'editor' })
const memberRules = {
  user: [{ required: true, message: '请选择用户', trigger: 'change' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

const environments = ref([])
const environmentsLoading = ref(false)
const envDialogVisible = ref(false)
const envSubmitting = ref(false)
const envEditingId = ref(null)
const envFormRef = ref(null)
const envForm = reactive({
  name: '',
  env_type: 'test',
  base_url: '',
  variablesText: '{}',
  headersText: '{}',
  description: '',
})
const envRules = {
  name: [{ required: true, message: '请输入环境名称', trigger: 'blur' }],
  env_type: [{ required: true, message: '请选择环境类型', trigger: 'change' }],
}

const knowledge = ref([])
const knowledgeLoading = ref(false)
const knowledgeDialogVisible = ref(false)
const knowledgeSubmitting = ref(false)
const reindexingId = ref(null)
const knowledgeFormRef = ref(null)
const knowledgeForm = reactive({ title: '', content: '' })
const knowledgeRules = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  content: [{ required: true, message: '请输入正文内容', trigger: 'blur' }],
}

const thirdPartyLoading = ref(false)
const thirdPartySaving = ref(false)
const thirdParty = reactive({
  dingtalk_webhook: '',
  wecom_webhook: '',
  feishu_webhook: '',
  gitlab_url: '',
  gitlab_token: '',
  extraText: '{}',
})

function setTabError(tab, message) {
  if (message) tabErrors[tab] = message
  else delete tabErrors[tab]
}

async function loadStats() {
  try {
    stats.value = await projectsApi.stats(projectId.value)
    setTabError('overview', '')
  } catch (error) {
    setTabError('overview', error?.message || '统计数据加载失败')
  }
}

async function loadMembers() {
  membersLoading.value = true
  try {
    const data = await projectsApi.members(projectId.value)
    members.value = Array.isArray(data) ? data : data?.results || []
    setTabError('members', '')
  } catch (error) {
    members.value = []
    setTabError('members', error?.message || '成员列表加载失败')
  } finally {
    membersLoading.value = false
  }
}

async function loadEnvironments() {
  environmentsLoading.value = true
  try {
    const data = await projectsApi.listEnvironments({
      project: projectId.value,
      page_size: 100,
    })
    environments.value = Array.isArray(data?.results) ? data.results : []
    setTabError('environments', '')
  } catch (error) {
    environments.value = []
    setTabError('environments', error?.message || '环境列表加载失败')
  } finally {
    environmentsLoading.value = false
  }
}

async function loadKnowledge() {
  knowledgeLoading.value = true
  try {
    const data = await projectsApi.listKnowledge({ project: projectId.value, page_size: 100 })
    knowledge.value = Array.isArray(data?.results) ? data.results : []
    setTabError('knowledge', '')
  } catch (error) {
    knowledge.value = []
    setTabError('knowledge', error?.message || '知识库列表加载失败')
  } finally {
    knowledgeLoading.value = false
  }
}

async function loadThirdParty() {
  thirdPartyLoading.value = true
  try {
    const data = await projectsApi.thirdPartyConfig(projectId.value)
    thirdParty.dingtalk_webhook = data?.dingtalk_webhook || ''
    thirdParty.wecom_webhook = data?.wecom_webhook || ''
    thirdParty.feishu_webhook = data?.feishu_webhook || ''
    thirdParty.gitlab_url = data?.gitlab_url || ''
    thirdParty.gitlab_token = data?.gitlab_token || ''
    thirdParty.extraText = JSON.stringify(data?.extra || {}, null, 2)
    setTabError('settings', '')
  } catch (error) {
    setTabError('settings', error?.message || '第三方配置加载失败')
  } finally {
    thirdPartyLoading.value = false
  }
}

async function loadProject() {
  projectLoading.value = true
  projectError.value = ''
  try {
    const data = await projectsApi.retrieve(projectId.value)
    project.value = data
    projectStore.upsertProject(data)
    projectStore.setCurrentProject(data)
    await Promise.all([loadStats(), loadMembers(), loadEnvironments(), loadKnowledge(), loadThirdParty()])
  } catch (error) {
    project.value = null
    projectError.value = error?.message || '项目加载失败'
  } finally {
    projectLoading.value = false
  }
}

function handleTabChange(name) {
  if (route.query.tab !== name) {
    router.replace({ query: { ...route.query, tab: name } })
  }
}

// ---------------------------------------------------------------------------
// 成员
// ---------------------------------------------------------------------------

async function searchUsers(query = '') {
  userSearchLoading.value = true
  try {
    const data = await usersApi.list({ search: query || undefined, page_size: 20 })
    const existing = new Set(members.value.map((member) => member.user))
    userOptions.value = (data?.results || []).filter((user) => !existing.has(user.id))
  } catch (error) {
    userOptions.value = []
    ElMessage.error(error?.message || '用户列表加载失败')
  } finally {
    userSearchLoading.value = false
  }
}

function openMemberDialog() {
  memberForm.user = null
  memberForm.role = 'editor'
  memberDialogVisible.value = true
  memberFormRef.value?.clearValidate()
  searchUsers('')
}

async function handleAddMember() {
  if (!memberFormRef.value) return
  try {
    await memberFormRef.value.validate()
  } catch {
    return
  }
  memberSubmitting.value = true
  try {
    await projectsApi.addMember(projectId.value, {
      user: memberForm.user,
      role: memberForm.role,
    })
    ElMessage.success('成员已添加')
    memberDialogVisible.value = false
    await loadMembers()
  } catch (error) {
    ElMessage.error(error?.message || '添加成员失败')
  } finally {
    memberSubmitting.value = false
  }
}

async function handleRoleChange(member, role) {
  if (member.role === role) return
  try {
    await projectsApi.updateMember(member.id, { role })
    member.role = role
    ElMessage.success('成员角色已更新')
  } catch (error) {
    ElMessage.error(error?.message || '角色更新失败')
    await loadMembers()
  }
}

async function handleRemoveMember(member) {
  try {
    await projectsApi.removeMember(projectId.value, member.id)
    ElMessage.success('成员已移除')
    await loadMembers()
  } catch (error) {
    ElMessage.error(error?.message || '移除成员失败')
  }
}

// ---------------------------------------------------------------------------
// 环境
// ---------------------------------------------------------------------------

function openEnvDialog(row = null) {
  if (row) {
    envEditingId.value = row.id
    envForm.name = row.name || ''
    envForm.env_type = row.env_type || 'test'
    envForm.base_url = row.base_url || ''
    envForm.variablesText = JSON.stringify(row.variables || {}, null, 2)
    envForm.headersText = JSON.stringify(row.headers || {}, null, 2)
    envForm.description = row.description || ''
  } else {
    envEditingId.value = null
    envForm.name = ''
    envForm.env_type = 'test'
    envForm.base_url = ''
    envForm.variablesText = '{}'
    envForm.headersText = '{}'
    envForm.description = ''
  }
  envDialogVisible.value = true
  envFormRef.value?.clearValidate()
}

function parseJsonObject(text, label) {
  if (!text || !text.trim()) return {}
  let value
  try {
    value = JSON.parse(text)
  } catch {
    throw new Error(`${label}不是合法的 JSON`)
  }
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${label}必须是 JSON 对象`)
  }
  return value
}

async function handleSaveEnv() {
  if (!envFormRef.value) return
  try {
    await envFormRef.value.validate()
  } catch {
    return
  }
  let variables
  let headers
  try {
    variables = parseJsonObject(envForm.variablesText, '环境变量')
    headers = parseJsonObject(envForm.headersText, '公共请求头')
  } catch (error) {
    ElMessage.error(error.message)
    return
  }

  envSubmitting.value = true
  try {
    const payload = {
      project: Number(projectId.value),
      name: envForm.name.trim(),
      env_type: envForm.env_type,
      base_url: envForm.base_url.trim(),
      variables,
      headers,
      description: envForm.description.trim(),
    }
    if (envEditingId.value) {
      await projectsApi.updateEnvironment(envEditingId.value, payload)
      ElMessage.success('环境已更新')
    } else {
      await projectsApi.createEnvironment(payload)
      ElMessage.success('环境已创建')
    }
    envDialogVisible.value = false
    await loadEnvironments()
    await loadStats()
  } catch (error) {
    ElMessage.error(error?.message || '环境保存失败')
  } finally {
    envSubmitting.value = false
  }
}

async function handleSetDefaultEnv(row) {
  try {
    await projectsApi.setDefaultEnvironment(row.id)
    ElMessage.success(`已将「${row.name}」设为默认环境`)
    await loadEnvironments()
  } catch (error) {
    ElMessage.error(error?.message || '设置默认环境失败')
  }
}

async function handleDeleteEnv(row) {
  try {
    await projectsApi.removeEnvironment(row.id)
    ElMessage.success('环境已删除')
    await loadEnvironments()
    await loadStats()
  } catch (error) {
    ElMessage.error(error?.message || '删除环境失败')
  }
}

// ---------------------------------------------------------------------------
// 知识库
// ---------------------------------------------------------------------------

function openKnowledgeDialog() {
  knowledgeForm.title = ''
  knowledgeForm.content = ''
  knowledgeDialogVisible.value = true
  knowledgeFormRef.value?.clearValidate()
}

async function handleCreateKnowledge() {
  if (!knowledgeFormRef.value) return
  try {
    await knowledgeFormRef.value.validate()
  } catch {
    return
  }
  knowledgeSubmitting.value = true
  try {
    await projectsApi.createKnowledge({
      project: Number(projectId.value),
      title: knowledgeForm.title.trim(),
      content: knowledgeForm.content,
    })
    ElMessage.success('知识文档已保存，正在建立索引')
    knowledgeDialogVisible.value = false
    await loadKnowledge()
    await loadStats()
  } catch (error) {
    ElMessage.error(error?.message || '知识文档保存失败')
  } finally {
    knowledgeSubmitting.value = false
  }
}

async function handleReindex(row) {
  reindexingId.value = row.id
  try {
    const data = await projectsApi.reindexKnowledge(row.id)
    ElMessage.success(`索引完成，共 ${data?.chunk_count ?? 0} 个分块`)
    await loadKnowledge()
  } catch (error) {
    ElMessage.error(error?.message || '重新索引失败')
  } finally {
    reindexingId.value = null
  }
}

async function handleDeleteKnowledge(row) {
  try {
    await projectsApi.removeKnowledge(row.id)
    ElMessage.success('知识文档已删除')
    await loadKnowledge()
    await loadStats()
  } catch (error) {
    ElMessage.error(error?.message || '删除知识文档失败')
  }
}

// ---------------------------------------------------------------------------
// 第三方配置
// ---------------------------------------------------------------------------

async function handleSaveThirdParty() {
  let extra
  try {
    extra = parseJsonObject(thirdParty.extraText, '扩展配置')
  } catch (error) {
    ElMessage.error(error.message)
    return
  }
  thirdPartySaving.value = true
  try {
    await projectsApi.saveThirdPartyConfig(projectId.value, {
      dingtalk_webhook: thirdParty.dingtalk_webhook.trim(),
      wecom_webhook: thirdParty.wecom_webhook.trim(),
      feishu_webhook: thirdParty.feishu_webhook.trim(),
      gitlab_url: thirdParty.gitlab_url.trim(),
      gitlab_token: thirdParty.gitlab_token.trim(),
      extra,
    })
    ElMessage.success('第三方配置已保存')
    setTabError('settings', '')
  } catch (error) {
    ElMessage.error(error?.message || '第三方配置保存失败')
  } finally {
    thirdPartySaving.value = false
  }
}

watch(
  () => route.params.id,
  () => loadProject(),
)

onMounted(loadProject)
</script>

<style scoped>
.project-tabs-card {
  padding: 0 18px 18px;
}

.project-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.project-tabs :deep(.el-tabs__nav-wrap) {
  padding: 0 4px;
}

.tab-body {
  padding-top: 18px;
}

.overview-stats {
  margin-bottom: 18px;
}

.overview-descriptions {
  margin-top: 4px;
}

.module-stats {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.third-party-form {
  max-width: 780px;
}
</style>
