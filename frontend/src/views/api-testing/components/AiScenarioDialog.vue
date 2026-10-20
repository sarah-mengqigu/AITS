<template>
  <el-dialog
    :model-value="modelValue"
    title="AI 场景生成"
    width="760px"
    :close-on-click-modal="false"
    @update:model-value="handleVisibleChange"
    @closed="handleClosed"
  >
    <el-alert
      class="mb-16"
      type="info"
      :closable="false"
      show-icon
      title="输入自然语言需求，AI 会结合当前项目的端点生成多步骤场景用例；LLM 不可用时自动降级为规则生成。"
    />

    <el-alert
      v-if="errorMessage"
      class="mb-16"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
    />

    <el-form ref="formRef" :model="form" :rules="rules" label-width="92px">
      <el-form-item label="需求描述" prop="requirement">
        <el-input
          v-model="form.requirement"
          type="textarea"
          :rows="4"
          maxlength="2000"
          show-word-limit
          placeholder="例如：用户登录后查询订单列表，校验订单数量与字段完整性"
        />
      </el-form-item>
      <el-form-item label="保存用例">
        <el-switch v-model="form.save" active-text="生成后保存到用例库" />
      </el-form-item>
    </el-form>

    <template v-if="result">
      <el-divider content-position="left">生成结果</el-divider>
      <div class="scenario-head">
        <el-tag :type="result.source === 'ai' ? 'primary' : 'warning'" size="small">
          {{ result.source === 'ai' ? 'AI 生成' : '规则降级生成' }}
        </el-tag>
        <strong>{{ scenarioName }}</strong>
        <span class="text-small text-muted">
          步骤 {{ scenarioStepCount }} 个 · 用例 {{ result.cases?.length ?? 0 }} 条
        </span>
      </div>
      <p v-if="scenarioDescription" class="scenario-desc">{{ scenarioDescription }}</p>

      <el-table :data="result.cases || []" size="small" border class="mt-8" max-height="240">
        <el-table-column label="用例名称" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.name || '未命名用例' }}</template>
        </el-table-column>
        <el-table-column label="测试类型" width="100">
          <template #default="{ row }">
            <el-tag :type="getTestTypeTagType(row.test_type)" size="small" effect="light">
              {{ getTestTypeLabel(row.test_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="断言数" width="80" align="center">
          <template #default="{ row }">{{ Array.isArray(row.assertions) ? row.assertions.length : 0 }}</template>
        </el-table-column>
        <el-table-column label="来源" width="90">
          <template #default="{ row }">{{ getSourceLabel(row.source) }}</template>
        </el-table-column>
      </el-table>

      <el-collapse class="mt-16">
        <el-collapse-item title="查看原始返回（scenario + cases）" name="raw">
          <JsonViewer :value="result" title="AI 场景生成结果" :max-height="320" />
        </el-collapse-item>
      </el-collapse>
    </template>

    <template #footer>
      <el-button @click="handleVisibleChange(false)">关闭</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        {{ result ? '重新生成' : '生成场景' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import JsonViewer from '@/components/JsonViewer.vue'
import { apiTestingApi } from '@/api/apiTesting'
import { getSourceLabel, getTestTypeLabel, getTestTypeTagType } from '../utils'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  projectId: { type: [Number, String], default: null },
})

const emit = defineEmits(['update:modelValue', 'generated'])

const formRef = ref(null)
const submitting = ref(false)
const errorMessage = ref('')
const result = ref(null)

const form = reactive({
  requirement: '',
  save: true,
})

const rules = {
  requirement: [
    { required: true, message: '请输入需求描述', trigger: 'blur' },
    { min: 4, message: '需求描述至少 4 个字符', trigger: 'blur' },
  ],
}

const scenarioName = computed(() => result.value?.scenario?.name || form.requirement.split('\n')[0] || '未命名场景')
const scenarioDescription = computed(() => result.value?.scenario?.description || '')
const scenarioStepCount = computed(() => {
  const scenario = result.value?.scenario || {}
  if (Array.isArray(scenario.steps)) return scenario.steps.length
  return Number(scenario.step_count) || 0
})

function handleVisibleChange(value) {
  emit('update:modelValue', value)
}

function handleClosed() {
  // 保留上次结果，便于再次打开时对比；仅清空错误
  errorMessage.value = ''
}

async function handleSubmit() {
  if (!props.projectId) {
    ElMessage.warning('请先选择项目')
    return
  }
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  submitting.value = true
  errorMessage.value = ''
  try {
    const data = await apiTestingApi.generateScenario(props.projectId, form.requirement.trim(), {
      save: form.save,
    })
    result.value = data || null
    const count = data?.cases?.length ?? 0
    ElMessage.success(`场景生成完成：${count} 条用例${form.save ? '，已保存到用例库' : '（未保存）'}`)
    emit('generated', data)
  } catch (error) {
    errorMessage.value = error?.message || 'AI 场景生成失败'
    ElMessage.error(errorMessage.value)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.scenario-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 14px;
}

.scenario-desc {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--aits-text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
}

.mt-8 {
  margin-top: 8px;
}
</style>
