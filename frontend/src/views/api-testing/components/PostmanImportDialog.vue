<template>
  <el-dialog
    :model-value="modelValue"
    title="Postman Collection 导入"
    width="600px"
    :close-on-click-modal="false"
    @update:model-value="handleVisibleChange"
    @closed="handleClosed"
  >
    <el-alert
      class="mb-16"
      type="info"
      :closable="false"
      show-icon
      title="支持 Postman Collection v2.1 JSON，导入后自动生成接口规范、模块、端点，并尝试转换 pm.test 断言为用例。"
    />

    <el-alert
      v-if="errorMessage"
      class="mb-16"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
    />

    <el-upload
      ref="uploadRef"
      drag
      :auto-upload="false"
      :limit="1"
      accept=".json,application/json"
      :on-change="handleFileChange"
      :on-remove="handleFileRemove"
      :on-exceed="handleExceed"
    >
      <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
      <div class="el-upload__text">将 Collection 文件拖到此处，或<em>点击选择</em></div>
      <template #tip>
        <div class="el-upload__tip">仅支持单个 JSON 文件，大小不超过 10MB。</div>
      </template>
    </el-upload>

    <el-form class="mt-16" label-width="92px" @submit.prevent>
      <el-form-item label="导入名称">
        <el-input
          v-model="form.name"
          maxlength="128"
          clearable
          placeholder="可选，默认使用 Collection 名称"
        />
      </el-form-item>
      <el-form-item label="Base URL">
        <el-input
          v-model="form.base_url"
          clearable
          placeholder="可选，例如 https://api.example.com"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleVisibleChange(false)">取消</el-button>
      <el-button type="primary" :loading="submitting" :disabled="!file" @click="handleSubmit">
        开始导入
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

import { apiTestingApi } from '@/api/apiTesting'
import { isValidHttpUrl } from '../utils'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  projectId: { type: [Number, String], default: null },
})

const emit = defineEmits(['update:modelValue', 'imported'])

const uploadRef = ref(null)
const file = ref(null)
const submitting = ref(false)
const errorMessage = ref('')
const form = reactive({ name: '', base_url: '' })

function handleVisibleChange(value) {
  emit('update:modelValue', value)
}

function handleFileChange(uploadFile) {
  errorMessage.value = ''
  const raw = uploadFile?.raw || null
  if (raw && !/\.json$/i.test(raw.name || '')) {
    errorMessage.value = '请选择 JSON 格式的 Postman Collection 文件'
    file.value = null
    uploadRef.value?.clearFiles()
    return
  }
  file.value = raw
}

function handleFileRemove() {
  file.value = null
}

function handleExceed(files) {
  // 只保留最新选择的文件，避免 el-upload 静默丢弃
  uploadRef.value?.clearFiles()
  const latest = files?.[0]
  if (latest) {
    file.value = latest
    uploadRef.value?.handleStart(latest)
    errorMessage.value = ''
  }
}

function reset() {
  file.value = null
  form.name = ''
  form.base_url = ''
  errorMessage.value = ''
  uploadRef.value?.clearFiles()
}

function handleClosed() {
  reset()
}

async function handleSubmit() {
  if (!props.projectId) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!file.value) {
    errorMessage.value = '请先选择 Postman Collection 文件'
    return
  }
  if (form.base_url.trim() && !isValidHttpUrl(form.base_url)) {
    errorMessage.value = 'Base URL 必须是 http(s) 开头的完整地址'
    return
  }
  submitting.value = true
  errorMessage.value = ''
  try {
    const data = await apiTestingApi.importPostman(props.projectId, file.value, {
      name: form.name.trim() || undefined,
      base_url: form.base_url.trim() || undefined,
    })
    const endpointCount = data?.endpoint_count ?? 0
    const caseCount = data?.case_count ?? 0
    ElMessage.success(`导入成功：解析 ${endpointCount} 个端点，生成 ${caseCount} 条用例`)
    emit('imported', data)
    emit('update:modelValue', false)
  } catch (error) {
    errorMessage.value = error?.message || 'Postman 导入失败'
    ElMessage.error(errorMessage.value)
  } finally {
    submitting.value = false
  }
}
</script>
